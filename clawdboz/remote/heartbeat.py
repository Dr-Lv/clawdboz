"""
心跳管理器
监控远程实例健康状态，处理离线事件和自动重连
"""
import asyncio
import time
from enum import Enum
from typing import Dict, Callable, Optional, List
from dataclasses import dataclass, field


class InstanceHealth(str, Enum):
    """实例健康状态"""
    ONLINE = "online"
    OFFLINE = "offline"
    DEGRADED = "degraded"  # 服务降级（如高延迟）
    UNKNOWN = "unknown"


@dataclass
class InstanceHealthStatus:
    """实例健康状态"""
    instance_id: str
    health: InstanceHealth
    last_seen: float  # 最后心跳时间戳
    last_check: float  # 最后检查时间戳
    consecutive_failures: int = 0  # 连续失败次数
    avg_latency_ms: float = 0.0  # 平均延迟
    error_message: str = ""  # 错误信息


class HeartbeatManager:
    """心跳管理器"""

    def __init__(
        self,
        health_check_interval: int = 30,
        offline_threshold: int = 90,
        degraded_threshold: int = 500
    ):
        """
        初始化心跳管理器

        Args:
            health_check_interval: 健康检查间隔（秒）
            offline_threshold: 离线阈值（秒），超过此时间未心跳视为离线
            degraded_threshold: 降级阈值（毫秒），延迟超过此值视为降级
        """
        self.health_check_interval = health_check_interval
        self.offline_threshold = offline_threshold
        self.degraded_threshold = degraded_threshold

        # 实例健康状态 {instance_id: InstanceHealthStatus}
        self._instance_health: Dict[str, InstanceHealthStatus] = {}

        # 健康状态变化回调
        self._on_status_change: Optional[Callable] = None

        # 后台任务
        self._health_check_task: Optional[asyncio.Task] = None
        self._running = False

    def set_status_change_callback(self, callback: Callable):
        """
        设置状态变化回调

        Args:
            callback: 回调函数 (instance_id, old_health, new_health)
        """
        self._on_status_change = callback

    def start_heartbeat_thread(self):
        """启动心跳检查线程"""
        if self._running:
            return

        self._running = True
        self._health_check_task = asyncio.create_task(self._health_check_loop())
        print(f"[Heartbeat] 心跳检查线程已启动 (间隔={self.health_check_interval}s)")

    async def stop_heartbeat_thread(self):
        """停止心跳检查线程"""
        self._running = False

        if self._health_check_task:
            self._health_check_task.cancel()
            try:
                await self._health_check_task
            except asyncio.CancelledError:
                pass
            self._health_check_task = None

        print(f"[Heartbeat] 心跳检查线程已停止")

    async def _health_check_loop(self):
        """健康检查循环"""
        while self._running:
            try:
                await self._check_all_instances()
                await asyncio.sleep(self.health_check_interval)
            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[Heartbeat] 健康检查失败: {e}")
                await asyncio.sleep(self.health_check_interval)

    async def _check_all_instances(self):
        """检查所有实例的健康状态"""
        now = time.time()

        for instance_id, status in list(self._instance_health.items()):
            # 检查是否离线
            time_since_last_seen = now - status.last_seen

            old_health = status.health

            if time_since_last_seen > self.offline_threshold:
                # 超过阈值，视为离线
                new_health = InstanceHealth.OFFLINE
                status.health = new_health
                status.error_message = f"No heartbeat for {int(time_since_last_seen)}s"

                # 尝试自动重连
                await self._auto_reconnect(instance_id)

            elif time_since_last_seen > (self.offline_threshold * 0.7):
                # 接近离线阈值，视为降级
                if status.health != InstanceHealth.DEGRADED:
                    new_health = InstanceHealth.DEGRADED
                    status.health = new_health
                    status.error_message = f"Infrequent heartbeat ({int(time_since_last_seen)}s)"

            else:
                # 正常
                if status.health != InstanceHealth.ONLINE:
                    new_health = InstanceHealth.ONLINE
                    status.health = new_health
                    status.error_message = ""

            # 状态变化通知
            if old_health != new_health:
                print(f"[Heartbeat] 实例 {instance_id} 状态变化: {old_health} -> {new_health}")

                if self._on_status_change:
                    try:
                        if asyncio.iscoroutinefunction(self._on_status_change):
                            await self._on_status_change(instance_id, old_health, new_health)
                        else:
                            self._on_status_change(instance_id, old_health, new_health)
                    except Exception as e:
                        print(f"[Heartbeat] 状态变化回调失败: {e}")

    async def _auto_reconnect(self, instance_id: str):
        """
        自动重连

        Args:
            instance_id: 实例 ID
        """
        print(f"[Heartbeat] 尝试自动重连: {instance_id}")

        # 这里应该调用 RemoteBotManager 的重连方法
        # 由于循环依赖，我们通过回调处理
        # 实际重连逻辑在 RemoteBotManager 中实现

    def update_heartbeat(
        self,
        instance_id: str,
        latency_ms: float = 0.0
    ):
        """
        更新实例心跳

        Args:
            instance_id: 实例 ID
            latency_ms: 心跳延迟（毫秒）
        """
        now = time.time()

        if instance_id not in self._instance_health:
            self._instance_health[instance_id] = InstanceHealthStatus(
                instance_id=instance_id,
                health=InstanceHealth.UNKNOWN,
                last_seen=now,
                last_check=now
            )

        status = self._instance_health[instance_id]
        status.last_seen = now
        status.last_check = now
        status.consecutive_failures = 0

        # 更新延迟（移动平均）
        if status.avg_latency_ms > 0:
            status.avg_latency_ms = (status.avg_latency_ms * 0.8) + (latency_ms * 0.2)
        else:
            status.avg_latency_ms = latency_ms

        # 检查是否降级
        if latency_ms > self.degraded_threshold:
            if status.health != InstanceHealth.DEGRADED:
                old_health = status.health
                status.health = InstanceHealth.DEGRADED
                print(f"[Heartbeat] 实例 {instance_id} 延迟过高: {latency_ms}ms")

                if self._on_status_change:
                    try:
                        self._on_status_change(instance_id, old_health, status.health)
                    except Exception as e:
                        print(f"[Heartbeat] 状态变化回调失败: {e}")

        elif status.health == InstanceHealth.DEGRADED:
            # 从降级恢复
            old_health = status.health
            status.health = InstanceHealth.ONLINE
            print(f"[Heartbeat] 实例 {instance_id} 从降级恢复")

            if self._on_status_change:
                try:
                    self._on_status_change(instance_id, old_health, status.health)
                except Exception as e:
                    print(f"[Heartbeat] 状态变化回调失败: {e}")

    def check_instance_health(self, instance_id: str) -> InstanceHealth:
        """
        检查实例健康状态

        Args:
            instance_id: 实例 ID

        Returns:
            健康状态
        """
        status = self._instance_health.get(instance_id)
        if not status:
            return InstanceHealth.UNKNOWN

        return status.health

    def handle_instance_offline(self, instance_id: str):
        """
        处理实例离线事件

        Args:
            instance_id: 实例 ID
        """
        print(f"[Heartbeat] 处理实例离线: {instance_id}")

        # 更新状态
        if instance_id in self._instance_health:
            self._instance_health[instance_id].health = InstanceHealth.OFFLINE

        # 通知状态变化
        if self._on_status_change:
            try:
                self._on_status_change(instance_id, InstanceHealth.ONLINE, InstanceHealth.OFFLINE)
            except Exception as e:
                print(f"[Heartbeat] 状态变化回调失败: {e}")

    def get_all_health_status(self) -> Dict[str, InstanceHealthStatus]:
        """
        获取所有实例的健康状态

        Returns:
            健康状态字典
        """
        return self._instance_health.copy()

    def get_online_instances(self) -> List[str]:
        """
        获取在线实例列表

        Returns:
            在线实例 ID 列表
        """
        return [
            instance_id
            for instance_id, status in self._instance_health.items()
            if status.health == InstanceHealth.ONLINE
        ]

    def get_offline_instances(self) -> List[str]:
        """
        获取离线实例列表

        Returns:
            离线实例 ID 列表
        """
        return [
            instance_id
            for instance_id, status in self._instance_health.items()
            if status.health == InstanceHealth.OFFLINE
        ]

    def get_degraded_instances(self) -> List[str]:
        """
        获取降级实例列表

        Returns:
            降级实例 ID 列表
        """
        return [
            instance_id
            for instance_id, status in self._instance_health.items()
            if status.health == InstanceHealth.DEGRADED
        ]
