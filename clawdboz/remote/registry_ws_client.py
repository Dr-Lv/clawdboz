"""
注册服务器 WebSocket 客户端
用于连接到注册服务器的 WebSocket 端点，实现中心转发模式
"""
import asyncio
import json
import logging
import ssl
from typing import Optional, Callable, Dict, Any
from enum import Enum

from websockets.asyncio.client import connect
from websockets.exceptions import ConnectionClosed, ConnectionClosedError

logger = logging.getLogger(__name__)


class RegistryConnectionState(str, Enum):
    """注册服务器连接状态"""
    DISCONNECTED = "disconnected"
    CONNECTING = "connecting"
    CONNECTED = "connected"
    RECONNECTING = "reconnecting"
    ERROR = "error"


class RegistryWebSocketClient:
    """
    注册服务器 WebSocket 客户端

    在中心转发模式下，实例通过此类连接到注册服务器的 WebSocket 端点。
    注册服务器会转发消息到其他实例。
    """

    def __init__(
        self,
        registry_ws_url: str,
        instance_id: str,
        token: str,
        auto_reconnect: bool = True,
        reconnect_interval: int = 5,
        connection_timeout: int = 10
    ):
        """
        初始化注册服务器 WebSocket 客户端

        Args:
            registry_ws_url: 注册服务器 WebSocket URL (如 "ws://localhost:9000/ws/registry")
            instance_id: 当前实例 ID
            token: 实例认证令牌
            auto_reconnect: 是否自动重连
            reconnect_interval: 重连间隔（秒）
            connection_timeout: 连接超时（秒）
        """
        self.registry_ws_url = registry_ws_url
        self.instance_id = instance_id
        self.token = token
        self.auto_reconnect = auto_reconnect
        self.reconnect_interval = reconnect_interval
        self.connection_timeout = connection_timeout

        # WebSocket 连接
        self._websocket = None
        self._connection_state = RegistryConnectionState.DISCONNECTED

        # 消息回调函数
        self._message_callback = None

        # 监听任务
        self._listen_task = None

        # 重连任务
        self._reconnect_task = None

        # 断开连接标志（防止重连循环在 disconnect() 后继续运行）
        self._disconnecting = False

    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._connection_state == RegistryConnectionState.CONNECTED

    async def connect(self) -> bool:
        """
        连接到注册服务器 WebSocket

        Returns:
            bool: 连接是否成功
        """
        import traceback
        caller = ''.join(traceback.format_stack(limit=4)[:-1])
        logger.warning(f"[RegistryWS-DEBUG] connect() CALLED from:\n{caller}")
        if self._connection_state == RegistryConnectionState.CONNECTED:
            logger.warning(f"[RegistryWS] 已经连接到注册服务器")
            return True

        self._connection_state = RegistryConnectionState.CONNECTING
        self._disconnecting = False
        logger.info(f"[RegistryWS] 正在连接到注册服务器: {self.registry_ws_url}")

        try:
            # 构建 WebSocket URL，附带查询参数
            url = f"{self.registry_ws_url}?instance_id={self.instance_id}&token={self.token}"

            # 连接（带超时），启用 WebSocket ping/pong 保活防止 NAT 静默断开
            # 对 wss:// 使用自签证书（跳过验证）
            ws_ssl = ssl._create_unverified_context() if self.registry_ws_url.startswith('wss://') else None
            self._websocket = await asyncio.wait_for(
                connect(url, ping_interval=5, ping_timeout=5, ssl=ws_ssl),
                timeout=self.connection_timeout
            )

            self._connection_state = RegistryConnectionState.CONNECTED
            logger.info(f"[RegistryWS] 已连接到注册服务器: {self.instance_id}")

            # 启动监听任务
            if self._message_callback:
                self._listen_task = asyncio.create_task(self._listen_loop())

            return True

        except asyncio.TimeoutError:
            logger.error(f"[RegistryWS] 连接超时: {self.registry_ws_url}")
            self._connection_state = RegistryConnectionState.ERROR
            return False
        except Exception as e:
            logger.error(f"[RegistryWS] 连接失败: {e}")
            self._connection_state = RegistryConnectionState.ERROR
            return False

    async def disconnect(self):
        """断开连接"""
        self._disconnecting = True
        self.auto_reconnect = False  # 防止重连循环继续运行
        logger.info(f"[RegistryWS] 断开连接")

        # 停止监听任务
        if self._listen_task and not self._listen_task.done():
            self._listen_task.cancel()
            try:
                await self._listen_task
            except asyncio.CancelledError:
                pass

        # 停止重连任务
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

        self._connection_state = RegistryConnectionState.DISCONNECTED

    async def send_to_instance(self, target_instance: str, message: dict) -> bool:
        """
        通过注册服务器发送消息到目标实例

        Args:
            target_instance: 目标实例 ID
            message: 消息内容（字典）

        Returns:
            bool: 发送是否成功
        """
        if not self.is_connected:
            logger.error(f"[RegistryWS] 未连接，无法发送消息到 {target_instance}")
            return False

        try:
            # 构建转发消息格式
            forward_message = {
                "type": "forward",
                "from_instance": self.instance_id,
                "to_instance": target_instance,
                "timestamp": asyncio.get_event_loop().time(),
                "payload": message
            }

            # 发送
            await self._websocket.send(json.dumps(forward_message))
            logger.debug(f"[RegistryWS] 发送消息到 {target_instance}: {message.get('type', 'unknown')}")
            return True

        except Exception as e:
            logger.error(f"[RegistryWS] 发送消息失败: {e}")
            return False

    async def listen_for_messages(self, callback: Callable[[Dict[str, Any]], None]):
        """
        监听来自注册服务器的消息

        Args:
            callback: 消息回调函数，接收字典格式的消息
        """
        self._message_callback = callback

        # 如果已连接，启动监听任务
        if self.is_connected and (not self._listen_task or self._listen_task.done()):
            self._listen_task = asyncio.create_task(self._listen_loop())

    async def _listen_loop(self):
        """监听循环"""
        logger.info(f"[RegistryWS] 开始监听消息")

        try:
            async for message in self._websocket:
                try:
                    data = json.loads(message)
                    logger.debug(f"[RegistryWS] 收到消息: {data.get('type', 'unknown')}")

                    # 调用回调函数
                    if self._message_callback:
                        await self._message_callback(data)

                except json.JSONDecodeError as e:
                    logger.error(f"[RegistryWS] JSON 解析失败: {e}")
                except Exception as e:
                    logger.error(f"[RegistryWS] 处理消息异常: {e}")

        except ConnectionClosed as e:
            close_code = getattr(e, 'code', None)
            logger.warning(f"[RegistryWS] 连接已关闭, code={close_code}")
            self._connection_state = RegistryConnectionState.DISCONNECTED

            # 被服务器替换 (code=4009) 或主动断开，不重连
            if close_code == 4009:
                logger.info(f"[RegistryWS] 连接被服务器替换 (code=4009)，停止重连")
                self.auto_reconnect = False
            elif self._disconnecting:
                logger.info(f"[RegistryWS] 主动断开，停止重连")
            elif self.auto_reconnect:
                logger.info(f"[RegistryWS] 将在 {self.reconnect_interval} 秒后重连...")
                self._reconnect_task = asyncio.create_task(self._reconnect_loop())

        except asyncio.CancelledError:
            logger.warning(f"[RegistryWS] 监听任务被取消")
            self._connection_state = RegistryConnectionState.DISCONNECTED

            # 自动重连（如果未被 disconnect() 调用）
            if self.auto_reconnect and not self._disconnecting:
                logger.info(f"[RegistryWS] 监听中断，将自动重连...")
                self._reconnect_task = asyncio.create_task(self._reconnect_loop())

        except Exception as e:
            logger.error(f"[RegistryWS] 监听异常: {e}")
            self._connection_state = RegistryConnectionState.ERROR

    async def _reconnect_loop(self):
        """重连循环"""
        while self.auto_reconnect and self._connection_state != RegistryConnectionState.CONNECTED:
            if self._disconnecting:
                logger.info(f"[RegistryWS] 正在断开连接，停止重连")
                break

            self._connection_state = RegistryConnectionState.RECONNECTING
            logger.info(f"[RegistryWS] 尝试重连...")

            success = await self.connect()
            if success:
                logger.info(f"[RegistryWS] 重连成功")
                break

            # 等待后重试
            await asyncio.sleep(self.reconnect_interval)
