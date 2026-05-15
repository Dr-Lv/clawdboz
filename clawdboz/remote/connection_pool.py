"""
连接池管理器
管理到远程实例的 WebSocket 连接池，支持连接复用和健康检查
"""
import asyncio
import time
from typing import Dict, Optional, List
from dataclasses import dataclass, field

from clawdboz.remote.remote_client import RemoteBotClient, ConnectionState
from clawdboz.remote.instance import RemoteInstance


@dataclass
class PooledConnection:
    """池化连接"""
    instance_id: str
    client: RemoteBotClient
    created_at: float = field(default_factory=time.time)
    last_used_at: float = field(default_factory=time.time)
    is_active: bool = True
    use_count: int = 0  # 使用次数


class ConnectionPool:
    """连接池管理器"""

    def __init__(
        self,
        max_connections_per_instance: int = 3,
        idle_timeout: int = 300,
        health_check_interval: int = 60
    ):
        """
        初始化连接池

        Args:
            max_connections_per_instance: 每个实例的最大连接数
            idle_timeout: 空闲超时（秒），超过此时间的连接将被关闭
            health_check_interval: 健康检查间隔（秒）
        """
        self.max_connections_per_instance = max_connections_per_instance
        self.idle_timeout = idle_timeout
        self.health_check_interval = health_check_interval

        # 连接池 {instance_id: List[PooledConnection]}
        self._pools: Dict[str, List[PooledConnection]] = {}

        # 实例信息缓存 {instance_id: RemoteInstance}
        self._instances: Dict[str, RemoteInstance] = {}

        # 后台任务
        self._health_check_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False

        # 统计信息
        self._total_connections_created = 0
        self._total_connections_closed = 0

    def start(self):
        """启动连接池管理器"""
        if self._running:
            return

        self._running = True

        # 启动健康检查任务
        self._health_check_task = asyncio.create_task(self._health_check_loop())

        # 启动清理任务
        self._cleanup_task = asyncio.create_task(self._cleanup_loop())

        print(f"[ConnectionPool] 连接池已启动 (每实例最大连接={self.max_connections_per_instance})")

    async def stop(self):
        """停止连接池管理器"""
        self._running = False

        # 关闭所有连接
        for instance_id in list(self._pools.keys()):
            await self._close_instance_connections(instance_id)

        # 取消后台任务
        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None

        if self._cleanup_task:
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass
            self._cleanup_task = None

        print(f"[ConnectionPool] 连接池已停止")

    async def get_connection(self, instance_id: str, instance: RemoteInstance) -> Optional[RemoteBotClient]:
        """
        获取连接（优先复用空闲连接）

        Args:
            instance_id: 实例 ID
            instance: 实例信息

        Returns:
            RemoteBotClient 或 None
        """
        # 缓存实例信息
        self._instances[instance_id] = instance

        # 初始化连接池
        if instance_id not in self._pools:
            self._pools[instance_id] = []

        pool = self._pools[instance_id]

        # 查找可用的连接
        for pooled in pool:
            if pooled.is_active and pooled.client.is_connected():
                # 复用连接
                pooled.last_used_at = time.time()
                pooled.use_count += 1
                print(f"[ConnectionPool] 复用连接: {instance_id} (使用次数={pooled.use_count})")
                return pooled.client

        # 检查连接数限制
        active_count = sum(1 for p in pool if p.is_active)
        if active_count >= self.max_connections_per_instance:
            print(f"[ConnectionPool] 连接池已满: {instance_id} ({active_count}/{self.max_connections_per_instance})")
            # 尝试关闭最久未用的连接
            await self._close_idle_connection(instance_id)

        # 创建新连接
        print(f"[ConnectionPool] 创建新连接: {instance_id}")
        return await self._create_connection(instance_id, instance)

    async def _create_connection(self, instance_id: str, instance: RemoteInstance) -> Optional[RemoteBotClient]:
        """
        创建新连接

        Args:
            instance_id: 实例 ID
            instance: 实例信息

        Returns:
            RemoteBotClient 或 None
        """
        try:
            client = RemoteBotClient(
                instance_id=self._get_local_instance_id(),
                auto_reconnect=True
            )

            # 连接到实例
            success = await client.connect_to_instance(instance)

            if success and client.is_connected():
                # 添加到连接池
                pooled = PooledConnection(
                    instance_id=instance_id,
                    client=client
                )

                self._pools[instance_id].append(pooled)
                self._total_connections_created += 1

                return client
            else:
                print(f"[ConnectionPool] 连接失败: {instance_id}")
                return None

        except Exception as e:
            print(f"[ConnectionPool] 创建连接失败: {e}")
            return None

    async def release_connection(self, instance_id: str, client: RemoteBotClient):
        """
        释放连接（标记为可复用）

        Args:
            instance_id: 实例 ID
            client: 客户端连接
        """
        pool = self._pools.get(instance_id)
        if not pool:
            return

        for pooled in pool:
            if pooled.client is client:
                pooled.last_used_at = time.time()
                print(f"[ConnectionPool] 释放连接: {instance_id}")
                return

        print(f"[ConnectionPool] 未找到连接: {instance_id}")

    async def close_idle_connections(self):
        """关闭所有空闲连接"""
        now = time.time()

        for instance_id, pool in list(self._pools.items()):
            idle_connections = [
                pooled for pooled in pool
                if pooled.is_active and (now - pooled.last_used_at) > self.idle_timeout
            ]

            for pooled in idle_connections:
                await self._close_pooled_connection(pooled)

    async def _close_idle_connection(self, instance_id: str):
        """
        关闭最久未用的连接

        Args:
            instance_id: 实例 ID
        """
        pool = self._pools.get(instance_id)
        if not pool:
            return

        # 找到最久未用的活跃连接
        oldest = None
        oldest_time = float('inf')

        for pooled in pool:
            if pooled.is_active and pooled.last_used_at < oldest_time:
                oldest = pooled
                oldest_time = pooled.last_used_at

        if oldest:
            await self._close_pooled_connection(oldest)

    async def _close_pooled_connection(self, pooled: PooledConnection):
        """
        关闭池化连接

        Args:
            pooled: 池化连接
        """
        print(f"[ConnectionPool] 关闭连接: {pooled.instance_id}")

        pooled.is_active = False
        await pooled.client.disconnect()
        self._total_connections_closed += 1

    async def _close_instance_connections(self, instance_id: str):
        """
        关闭实例的所有连接

        Args:
            instance_id: 实例 ID
        """
        pool = self._pools.get(instance_id)
        if not pool:
            return

        for pooled in pool:
            if pooled.is_active:
                await self._close_pooled_connection(pooled)

        # 清空连接池
        self._pools[instance_id].clear()

    async def _health_check_loop(self):
        """健康检查循环"""
        while self._running:
            try:
                await self._health_check_connections()
                await asyncio.sleep(self.health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[ConnectionPool] 健康检查失败: {e}")
                await asyncio.sleep(self.health_check_interval)

    async def _health_check_connections(self):
        """检查所有连接的健康状态"""
        for instance_id, pool in list(self._pools.items()):
            for pooled in pool:
                if pooled.is_active:
                    # 检查连接状态
                    if not pooled.client.is_connected():
                        print(f"[ConnectionPool] 检测到断开连接: {instance_id}")
                        pooled.is_active = False

    async def _cleanup_loop(self):
        """清理循环"""
        while self._running:
            try:
                await self.close_idle_connections()
                await asyncio.sleep(60)  # 每分钟清理一次
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[ConnectionPool] 清理失败: {e}")
                await asyncio.sleep(60)

    def get_pool_statistics(self) -> dict:
        """
        获取连接池统计信息

        Returns:
            统计信息字典
        """
        total_connections = 0
        active_connections = 0
        idle_connections = 0

        now = time.time()

        for pool in self._pools.values():
            for pooled in pool:
                total_connections += 1
                if pooled.is_active:
                    active_connections += 1
                    if (now - pooled.last_used_at) > self.idle_timeout:
                        idle_connections += 1

        return {
            "total_instances": len(self._pools),
            "total_connections": total_connections,
            "active_connections": active_connections,
            "idle_connections": idle_connections,
            "connections_created": self._total_connections_created,
            "connections_closed": self._total_connections_closed
        }

    def _get_local_instance_id(self) -> str:
        """获取本地实例 ID"""
        # TODO: 从配置获取
        import socket
        return f"local-{socket.gethostname()}"
