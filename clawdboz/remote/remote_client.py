"""
远程 Bot 调用客户端
通过 WebSocket 连接远程实例并调用 Bot
"""
import asyncio
import json
import uuid
import time
from enum import Enum
from typing import Dict, Optional, Callable, Any
from dataclasses import dataclass, field
from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, ConnectionClosedError, ConnectionClosedOK

from clawdboz.remote.message import RemoteMessage, MessageType
from clawdboz.remote.instance import RemoteInstance


class ConnectionState(str, Enum):
    """连接状态"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


@dataclass
class PendingRequest:
    """待处理的请求"""
    message_id: str
    bot_id: str
    method: str
    params: dict
    created_at: float = field(default_factory=time.time)
    timeout: int = 30  # 超时时间（秒）

    def is_expired(self) -> bool:
        """检查请求是否超时"""
        return (time.time() - self.created_at) > self.timeout


class RemoteBotClient:
    """远程 Bot 调用客户端"""

    def __init__(
        self,
        instance_id: str,
        on_message_callback: Optional[Callable] = None,
        auto_reconnect: bool = True,
        reconnect_interval: int = 5,
        connection_timeout: int = 10,
        connection_mode: str = "p2p",  # NEW: "p2p" 或 "center"
        registry_ws_client = None,  # NEW: RegistryWebSocketClient 实例
        local_token: str = ""  # NEW: 本地认证令牌
    ):
        """
        初始化远程 Bot 客户端

        Args:
            instance_id: 当前实例 ID
            on_message_callback: 消息回调函数
            auto_reconnect: 是否自动重连
            reconnect_interval: 重连间隔（秒）
            connection_timeout: 连接超时（秒）
            connection_mode: 连接模式 - "p2p"（直连）或 "center"（中心转发）
            registry_ws_client: 中心转发模式下的注册服务器 WebSocket 客户端
            local_token: 本地认证令牌（用于连接到远程实例）
        """
        self.instance_id = instance_id
        self.on_message_callback = on_message_callback
        self.auto_reconnect = auto_reconnect
        self.reconnect_interval = reconnect_interval
        self.connection_timeout = connection_timeout
        self.connection_mode = connection_mode  # NEW
        self._registry_ws_client = registry_ws_client  # NEW
        self._local_token = local_token  # NEW

        # WebSocket 连接
        self._websocket: Optional[websockets.WebSocketClientProtocol] = None
        self._connection_state = ConnectionState.DISCONNECTED

        # 远程实例信息
        self._remote_instances: Dict[str, RemoteInstance] = {}

        # 待处理的请求 {message_id: PendingRequest}
        self._pending_requests: Dict[str, PendingRequest] = {}

        # 响应等待器 {message_id: asyncio.Future}
        self._response_waiters: Dict[str, asyncio.Future] = {}

        # 后台任务
        self._receive_task: Optional[asyncio.Task] = None
        self._reconnect_task: Optional[asyncio.Task] = None
        self._cleanup_task: Optional[asyncio.Task] = None
        self._running = False

    @property
    def connection_state(self) -> ConnectionState:
        """获取连接状态"""
        return self._connection_state

    def is_connected(self) -> bool:
        """检查是否已连接"""
        return self._connection_state == ConnectionState.CONNECTED

    async def connect_to_instance(
        self,
        instance: RemoteInstance
    ) -> bool:
        """
        连接到远程实例

        Args:
            instance: 远程实例信息

        Returns:
            是否连接成功
        """
        # 根据连接模式选择连接方式
        if self.connection_mode == "center":
            return await self._connect_via_center(instance)
        else:
            return await self._connect_direct(instance)

    async def _connect_direct(
        self,
        instance: RemoteInstance
    ) -> bool:
        """
        直连模式：直接连接到远程实例（P2P）

        Args:
            instance: 远程实例信息

        Returns:
            是否连接成功
        """
        if self._connection_state == ConnectionState.CONNECTED:
            print(f"[RemoteClient] 已连接（直连模式），跳过重复连接")
            return True

        self._connection_state = ConnectionState.CONNECTING

        try:
            # 构建 WebSocket URL
            ws_url = instance.ws_url
            # Use local token if remote instance doesn't provide one
            # In production, instances should exchange tokens during friend setup
            token = instance.token or self._local_token
            token_param = f"token={token}" if token else ""
            url = f"{ws_url}?{token_param}"

            print(f"[RemoteClient] 直连模式: 连接到 {instance.instance_id} @ {url}")
            print(f"[RemoteClient] Using token: {token[:20]}..." if token else "[RemoteClient] No token!")
            print(f"[RemoteClient] timeout = {self.connection_timeout}")

            # 连接 WebSocket
            try:
                print(f"[RemoteClient] 开始连接...")
                self._websocket = await asyncio.wait_for(
                    connect(url, open_timeout=self.connection_timeout),
                    timeout=self.connection_timeout
                )
                print(f"[RemoteClient] WebSocket 连接已建立")
            except asyncio.TimeoutError:
                print(f"[RemoteClient] 连接超时")
                raise
            except Exception as e:
                print(f"[RemoteClient] 连接失败: {type(e).__name__}: {e}")
                raise

            self._connection_state = ConnectionState.CONNECTED
            self._remote_instances[instance.instance_id] = instance

            print(f"[RemoteClient] 直连成功")

            # 启动接收消息任务
            self._running = True
            self._receive_task = asyncio.create_task(self._receive_messages())
            self._cleanup_task = asyncio.create_task(self._cleanup_expired_requests())

            return True

        except asyncio.TimeoutError:
            print(f"[RemoteClient] 连接超时")
            self._connection_state = ConnectionState.ERROR
            return False

        except Exception as e:
            print(f"[RemoteClient] 连接失败: {e}")
            self._connection_state = ConnectionState.ERROR
            return False

    async def _connect_via_center(
        self,
        instance: RemoteInstance
    ) -> bool:
        """
        中心转发模式：通过注册服务器转发消息

        Args:
            instance: 远程实例信息

        Returns:
            是否连接成功（中心模式下总是返回 True，因为不需要直接连接）
        """
        # 中心模式下，不需要建立直接的 WebSocket 连接
        # 消息将通过注册服务器转发
        self._connection_state = ConnectionState.CONNECTED
        self._remote_instances[instance.instance_id] = instance

        print(f"[RemoteClient] 中心转发模式: 已注册 {instance.instance_id}（通过注册服务器转发）")

        # 启动清理任务
        self._running = True
        self._cleanup_task = asyncio.create_task(self._cleanup_expired_requests())

        return True

    async def disconnect(self):
        """断开连接并清理资源"""
        print(f"[RemoteClient] 断开连接")
        self._running = False
        self._connection_state = ConnectionState.DISCONNECTED

        # 取消接收任务
        if self._receive_task and not self._receive_task.done():
            self._receive_task.cancel()
            try:
                await self._receive_task
            except asyncio.CancelledError:
                pass

        # 取消清理任务
        if self._cleanup_task and not self._cleanup_task.done():
            self._cleanup_task.cancel()
            try:
                await self._cleanup_task
            except asyncio.CancelledError:
                pass

        # 取消重连任务
        if self._reconnect_task and not self._reconnect_task.done():
            self._reconnect_task.cancel()
            try:
                await self._reconnect_task
            except asyncio.CancelledError:
                pass

        # 关闭 WebSocket
        if self._websocket:
            await self._websocket.close()
            self._websocket = None

        # 清理待处理请求
        for msg_id, future in list(self._response_waiters.items()):
            if future and not future.done():
                future.set_exception(ConnectionError("Remote client disconnected"))
        self._response_waiters.clear()
        self._pending_requests.clear()
        self._remote_instances.clear()

    async def call_remote_bot(
        self,
        bot_id: str,
        method: str,
        params: dict,
        fs_api_url: str = "",
        chat_token: str = "",
        chat_id: str = "",
        timeout: int = 30
    ) -> Optional[dict]:
        """
        调用远程 Bot

        Args:
            bot_id: Bot ID (格式: instance_id:bot_id)
            method: 调用方法
            params: 参数
            fs_api_url: 文件访问 API URL
            chat_token: 会话 Token
            chat_id: 会话 ID
            timeout: 超时时间（秒）

        Returns:
            Bot 响应结果或 None
        """
        # 根据连接模式选择调用方式
        if self.connection_mode == "center":
            return await self._call_via_center(bot_id, method, params, fs_api_url, chat_token, chat_id, timeout)
        else:
            return await self._call_direct(bot_id, method, params, fs_api_url, chat_token, chat_id, timeout)

    async def _call_direct(
        self,
        bot_id: str,
        method: str,
        params: dict,
        fs_api_url: str = "",
        chat_token: str = "",
        chat_id: str = "",
        timeout: int = 30
    ) -> Optional[dict]:
        """
        调用远程 Bot

        Args:
            bot_id: Bot ID (格式: instance_id:bot_id)
            method: 调用方法
            params: 参数
            fs_api_url: 文件访问 API URL
            chat_token: 会话 Token
            chat_id: 会话 ID
            timeout: 超时时间（秒）

        Returns:
            Bot 响应结果或 None
        """
        if not self.is_connected():
            print(f"[RemoteClient] 未连接，无法调用 Bot")
            return None

        # 解析 bot_id (格式: instance_id:bot_id)
        parts = bot_id.split(":", 1)
        if len(parts) != 2:
            print(f"[RemoteClient] 无效的 bot_id 格式: {bot_id}")
            return None

        target_instance_id, target_bot_id = parts

        # 创建消息
        message_id = str(uuid.uuid4())
        # 注释掉 fs_api_url，让远程 bot 直接使用本地文件系统（docker 映射的 workplace）
        message = RemoteMessage(
            message_id=message_id,
            msg_type=MessageType.BOT_CALL,
            from_instance=self.instance_id,
            to_instance=target_instance_id,
            bot_id=target_bot_id,
            method=method,
            params=params,
            fs_api_url="",  # 不使用 fs api 代理
            chat_token=chat_token,
            chat_id=chat_id
        )

        # 创建响应等待器
        response_future = asyncio.Future()
        self._response_waiters[message_id] = response_future

        # 添加到待处理请求
        self._pending_requests[message_id] = PendingRequest(
            message_id=message_id,
            bot_id=bot_id,
            method=method,
            params=params,
            timeout=timeout
        )

        try:
            # 发送消息
            await self._send_message(message)
            print(f"[RemoteClient] 调用 Bot: {bot_id}.{method} (message_id={message_id})")

            # 等待响应
            response = await asyncio.wait_for(response_future, timeout=timeout)

            return response

        except asyncio.TimeoutError:
            print(f"[RemoteClient] Bot 调用超时: {bot_id}.{method}")
            return None

        except Exception as e:
            print(f"[RemoteClient] Bot 调用失败: {e}")
            return None

        finally:
            # 清理等待器
            self._response_waiters.pop(message_id, None)
            self._pending_requests.pop(message_id, None)

    async def _call_via_center(
        self,
        bot_id: str,
        method: str,
        params: dict,
        fs_api_url: str = "",
        chat_token: str = "",
        chat_id: str = "",
        timeout: int = 30
    ) -> Optional[dict]:
        """中心转发模式：通过注册服务器调用远程 Bot"""
        import json
        
        # 解析 bot_id (格式: instance_id:bot_id)
        parts = bot_id.split(":", 1)
        if len(parts) != 2:
            print(f"[RemoteClient] 无效的 bot_id 格式: {bot_id}")
            return None

        target_instance_id, target_bot_id = parts

        # 创建消息
        message_id = str(uuid.uuid4())
        # 注释掉 fs_api_url，让远程 bot 直接使用本地文件系统（docker 映射的 workplace）
        message = RemoteMessage(
            message_id=message_id,
            msg_type=MessageType.BOT_CALL,
            from_instance=self.instance_id,
            to_instance=target_instance_id,
            bot_id=target_bot_id,
            method=method,
            params=params,
            fs_api_url="",  # 不使用 fs api 代理
            chat_token=chat_token,
            chat_id=chat_id
        )

        # 创建响应等待器
        response_future = asyncio.Future()
        self._response_waiters[message_id] = response_future

        # 添加到待处理请求
        self._pending_requests[message_id] = PendingRequest(
            message_id=message_id,
            bot_id=bot_id,
            method=method,
            params=params,
            timeout=timeout
        )

        try:
            # 通过注册服务器发送消息
            if not self._registry_ws_client or not self._registry_ws_client.is_connected:
                print(f"[RemoteClient] 注册服务器未连接，无法调用 Bot")
                return None

            await self._registry_ws_client.send_to_instance(
                target_instance=target_instance_id,
                message=message.to_dict()
            )
            print(f"[RemoteClient] 中心转发模式调用 Bot: {bot_id}.{method} (message_id={message_id})")

            # 等待响应
            response = await asyncio.wait_for(response_future, timeout=timeout)
            return response

        except asyncio.TimeoutError:
            print(f"[RemoteClient] Bot 调用超时: {bot_id}.{method}")
            return None

        except Exception as e:
            print(f"[RemoteClient] Bot 调用失败: {e}")
            return None

        finally:
            # 清理等待器
            self._response_waiters.pop(message_id, None)
            self._pending_requests.pop(message_id, None)


    async def _send_message(self, message: RemoteMessage):
        """发送消息"""
        if not self._websocket:
            raise ConnectionError("WebSocket 未连接")

        data = message.to_dict()
        await self._websocket.send(json.dumps(data))

    async def _receive_messages(self):
        """接收消息循环"""
        try:
            async for message in self._websocket:
                try:
                    data = json.loads(message)
                    await self._handle_message(data)
                except json.JSONDecodeError as e:
                    print(f"[RemoteClient] 消息解析失败: {e}")
                except Exception as e:
                    print(f"[RemoteClient] 消息处理失败: {e}")

        except ConnectionClosed:
            print(f"[RemoteClient] 连接已关闭")
            self._connection_state = ConnectionState.DISCONNECTED

            if self.auto_reconnect:
                # 尝试重连所有已连接的实例
                for instance in self._remote_instances.values():
                    await self._schedule_reconnect(instance)

        except Exception as e:
            print(f"[RemoteClient] 接收消息错误: {e}")
            self._connection_state = ConnectionState.ERROR

    async def _handle_message(self, data: dict):
        """处理接收到的消息"""
        msg_type = data.get("type")
        message_id = data.get("message_id")

        if msg_type == MessageType.BOT_RESPONSE.value:
            # Bot 响应 - unwrap the nested result from the transport wrapper
            future = self._response_waiters.get(message_id)
            if future and not future.done():
                future.set_result(data.get("result", data))
            else:
                # 没有对应的等待器，调用回调
                if self.on_message_callback:
                    await self.on_message_callback(data)

        elif msg_type == MessageType.HEARTBEAT.value:
            # 心跳消息，忽略
            pass

        elif msg_type == MessageType.ERROR.value:
            # 错误消息
            future = self._response_waiters.get(message_id)
            if future and not future.done():
                future.set_exception(Exception(data.get("error", "Unknown error")))

        else:
            # 其他消息，调用回调
            if self.on_message_callback:
                await self.on_message_callback(data)

    async def _schedule_reconnect(self, instance: RemoteInstance):
        """安排重连"""
        if self._reconnect_task and not self._reconnect_task.done():
            return  # 已经在重连

        self._connection_state = ConnectionState.RECONNECTING
        self._reconnect_task = asyncio.create_task(self._reconnect_loop(instance))

    async def _reconnect_loop(self, instance: RemoteInstance):
        """重连循环"""
        while self._connection_state == ConnectionState.RECONNECTING and self.auto_reconnect:
            try:
                print(f"[RemoteClient] {self.reconnect_interval} 秒后重连...")
                await asyncio.sleep(self.reconnect_interval)

                success = await self.connect_to_instance(instance)
                if success:
                    print(f"[RemoteClient] 重连成功")
                    break

            except Exception as e:
                print(f"[RemoteClient] 重连失败: {e}")

        self._reconnect_task = None

    async def _cleanup_expired_requests(self):
        """清理超时的请求"""
        while self._running:
            try:
                await asyncio.sleep(5)  # 每 5 秒清理一次

                now = time.time()
                expired = [
                    msg_id
                    for msg_id, req in self._pending_requests.items()
                    if req.is_expired()
                ]

                for msg_id in expired:
                    # 取消等待器
                    future = self._response_waiters.get(msg_id)
                    if future and not future.done():
                        future.set_exception(asyncio.TimeoutError("Request expired"))

                    # 清理
                    self._response_waiters.pop(msg_id, None)
                    self._pending_requests.pop(msg_id, None)

                    print(f"[RemoteClient] 清理超时请求: {msg_id}")

            except Exception as e:
                print(f"[RemoteClient] 清理请求失败: {e}")

    def get_pending_request_count(self) -> int:
        """获取待处理请求数量"""
        return len(self._pending_requests)
