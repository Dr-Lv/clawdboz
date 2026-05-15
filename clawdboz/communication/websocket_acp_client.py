#!/usr/bin/env python3
"""WebSocket ACP 客户端模块 - 支持 WebSocket 协议的 ACP 客户端"""
import asyncio
import json
import uuid
from typing import Optional, Dict, Any, Tuple


class WebSocketACPClient:
    """WebSocket ACP 客户端 - 用于连接 OpenClaw 等 WebSocket-based ACP 服务器"""

    def __init__(self, ws_url: str, log_callback=None):
        """初始化 WebSocket ACP 客户端

        Args:
            ws_url: WebSocket 服务器 URL (e.g., ws://localhost:19001/acp)
            log_callback: 日志回调函数
        """
        self.ws_url = ws_url
        self.log_callback = log_callback or self._default_log
        self.session_id = None
        self.system_prompt = None
        self._websocket = None
        self._response_map = {}
        self._notification_handlers = []
        self._loop = None
        self._reader_task = None

    def _default_log(self, message: str):
        """默认日志输出"""
        print(f"[WS-ACP] {message}")

    def _log(self, message: str):
        """记录日志"""
        self.log_callback(message)

    async def _connect(self):
        """建立 WebSocket 连接"""
        import websockets.client
        try:
            self._log(f"连接到 WebSocket ACP 服务器: {self.ws_url}")

            # WebSocket 连接 - ws:// URI 不使用 SSL
            self._websocket = await websockets.client.connect(
                self.ws_url,
                close_timeout=1.0
            )
            self._log("WebSocket 连接成功")

            # 启动消息接收任务
            self._reader_task = asyncio.create_task(self._read_messages())

            return True
        except Exception as e:
            self._log(f"WebSocket 连接失败: {e}")
            return False

    async def _read_messages(self):
        """持续读取 WebSocket 消息"""
        try:
            async for message in self._websocket:
                try:
                    data = json.loads(message)
                    await self._handle_message(data)
                except json.JSONDecodeError as e:
                    self._log(f"JSON 解析错误: {e}, 消息: {message[:100]}")
                except Exception as e:
                    self._log(f"处理消息错误: {e}")
        except Exception as e:
            self._log(f"读取消息错误: {e}")

    async def _handle_message(self, data: dict):
        """处理接收到的消息"""
        if 'id' in data:
            # 这是一个响应消息
            request_id = data['id']
            if request_id in self._response_map:
                future = self._response_map.pop(request_id)
                future.set_result(data)
        else:
            # 这是一个通知消息
            for handler in self._notification_handlers:
                try:
                    await handler(data)
                except Exception as e:
                    self._log(f"通知处理器错误: {e}")

    async def call_method(self, method: str, params: dict = None, timeout: float = 30.0) -> Tuple[dict, Optional[str]]:
        """调用 ACP 方法

        Args:
            method: 方法名
            params: 参数
            timeout: 超时时间（秒）

        Returns:
            (result, error) 元组
        """
        if not self._websocket:
            await self._connect()

        request_id = str(uuid.uuid4())
        request = {
            "jsonrpc": "2.0",
            "id": request_id,
            "method": method,
            "params": params or {}
        }

        # 创建 Future 用于等待响应
        future = asyncio.Future()
        self._response_map[request_id] = future

        try:
            # 发送请求
            await self._websocket.send(json.dumps(request))
            self._log(f"发送请求: {method}")

            # 等待响应
            response = await asyncio.wait_for(future, timeout=timeout)

            if 'error' in response:
                return None, response['error'].get('message', str(response['error']))

            return response.get('result'), None

        except asyncio.TimeoutError:
            self._response_map.pop(request_id, None)
            return None, f"请求超时: {method}"
        except Exception as e:
            self._response_map.pop(request_id, None)
            return None, f"请求失败: {e}"

    async def initialize(self, protocol_version: int = 1) -> bool:
        """初始化 ACP 协议

        Args:
            protocol_version: 协议版本号

        Returns:
            是否成功
        """
        result, error = await self.call_method('initialize', {'protocolVersion': protocol_version})
        if error:
            self._log(f"初始化失败: {error}")
            return False

        self._log(f"初始化成功: {result}")
        return True

    async def create_session(self, cwd: str, mcp_servers: list = None,
                           skills: list = None, system_prompt: str = None) -> bool:
        """创建 ACP 会话

        Args:
            cwd: 工作目录
            mcp_servers: MCP 服务器列表
            skills: Skills 列表
            system_prompt: 系统提示词

        Returns:
            是否成功
        """
        params = {'cwd': cwd}

        if mcp_servers:
            params['mcpServers'] = mcp_servers
        if skills:
            params['skills'] = skills
        if system_prompt:
            params['systemPrompt'] = system_prompt

        result, error = await self.call_method('session/new', params)
        if error:
            self._log(f"创建会话失败: {error}")
            return False

        self.session_id = result.get('sessionId')
        self.system_prompt = system_prompt
        self._log(f"会话创建成功: {self.session_id}")
        return True

    async def chat(self, message: str, timeout: float = 180.0) -> str:
        """发送聊天消息

        Args:
            message: 消息内容
            timeout: 超时时间（秒）

        Returns:
            响应内容
        """
        if not self.session_id:
            return "错误: 会话未创建"

        result, error = await self.call_method('chat', {
            'sessionId': self.session_id,
            'message': message
        }, timeout=timeout)

        if error:
            return f"错误: {error}"

        # ACP chat 响应通常包含 content 字段
        if isinstance(result, dict):
            return result.get('content', str(result))
        return str(result)

    async def close(self):
        """关闭连接"""
        if self._reader_task:
            self._reader_task.cancel()
            try:
                await self._reader_task
            except asyncio.CancelledError:
                pass

        if self._websocket:
            await self._websocket.close()
            self._log("WebSocket 连接已关闭")

    def add_notification_handler(self, handler):
        """添加通知处理器

        Args:
            handler: 异步通知处理函数
        """
        self._notification_handlers.append(handler)


class WebSocketACPClientSync:
    """WebSocket ACP 客户端的同步封装 - 用于与现有的同步 ACPClient 接口兼容"""

    def __init__(self, ws_url: str, log_callback=None):
        """初始化同步 WebSocket ACP 客户端

        Args:
            ws_url: WebSocket 服务器 URL
            log_callback: 日志回调函数
        """
        self.ws_url = ws_url
        self.log_callback = log_callback
        self._async_client = WebSocketACPClient(ws_url, log_callback)
        self._loop = None
        self.session_id = None
        self.system_prompt = None

    def _get_or_create_loop(self):
        """获取或创建事件循环"""
        try:
            loop = asyncio.get_event_loop()
            if loop.is_closed():
                raise RuntimeError("Loop is closed")
            return loop
        except RuntimeError:
            loop = asyncio.new_event_loop()
            asyncio.set_event_loop(loop)
            return loop

    def _run_async(self, coro):
        """在事件循环中运行异步协程"""
        if self._loop is None:
            self._loop = self._get_or_create_loop()
        return self._loop.run_until_complete(coro)

    def initialize(self, protocol_version: int = 1) -> bool:
        """初始化 ACP 协议"""
        return self._run_async(self._async_client.initialize(protocol_version))

    def call_method(self, method: str, params: dict = None, timeout: float = 30.0) -> Tuple[dict, Optional[str]]:
        """调用 ACP 方法"""
        return self._run_async(self._async_client.call_method(method, params, timeout))

    def create_session(self, cwd: str, mcp_servers: list = None,
                      skills: list = None, system_prompt: str = None) -> bool:
        """创建 ACP 会话"""
        result = self._run_async(self._async_client.create_session(
            cwd, mcp_servers, skills, system_prompt
        ))
        if result:
            self.session_id = self._async_client.session_id
            self.system_prompt = self._async_client.system_prompt
        return result

    def chat(self, message: str, timeout: float = 180.0) -> str:
        """发送聊天消息"""
        return self._run_async(self._async_client.chat(message, timeout))

    def close(self):
        """关闭连接"""
        if self._async_client:
            self._run_async(self._async_client.close())
