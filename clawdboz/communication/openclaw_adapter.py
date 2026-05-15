#!/usr/bin/env python3
"""OpenClaw ACP 适配器 - 将 OpenClaw 转换为标准 ACP 接口"""
import asyncio
import threading
from typing import Optional, Dict, Any
from pathlib import Path


class OpenClawToACPAdapter:
    """OpenClaw ACP 适配器 - 转换 OpenClaw 协议为标准 ACP 格式"""

    def __init__(self, executable: str = "/opt/homebrew/bin/openclaw",
                 session: str = "agent:main:main",
                 log_callback=None):
        """初始化 OpenClaw 适配器"""
        self.executable = executable
        self.session = session
        self.log_callback = log_callback or self._default_log
        self.session_id = None
        self._loop = None
        self._thread = None
        self._conn = None
        self._acp_handler = None
        self._ready = threading.Event()
        self._initialized = False

    def _default_log(self, message: str):
        """默认日志输出"""
        print(f"[OpenClaw-Adapter] {message}")

    def _log(self, message: str):
        """记录日志"""
        self.log_callback(message)

    class ACPClientHandler:
        """ACP 客户端处理器 - 实现 OpenClaw 需要的回调接口"""

        def __init__(self, log_callback):
            self.log_callback = log_callback
            self.message_chunks = []
            self.thought_chunks = []
            self.tool_calls = []
            self.complete = False

        async def session_update(self, session_id: str, update, **kwargs):
            """处理会话更新（流式消息）"""
            kind = update.session_update
            self.log_callback(f"[session_update] kind={kind}")

            if kind == "agent_message_chunk":
                # 收集消息块
                text = update.content.text
                self.message_chunks.append(text)
                self.log_callback(f"[消息块] {text[:50]}...")
                self.log_callback(f"[调试] 当前收集到的消息长度: {len(self.message_chunks)} 块")

            elif kind == "agent_thought_chunk":
                # 收集思考过程
                thought = getattr(update, "thought", "")
                if thought:
                    self.thought_chunks.append(thought)
                    self.log_callback(f"[思考] {thought[:50]}...")

            elif kind == "tool_call_progress":
                # 收集工具调用
                tc = update.toolCall
                self.tool_calls.append({
                    'name': tc.name,
                    'status': tc.status
                })
                self.log_callback(f"[工具] {tc.name} - {tc.status}")

            elif kind == "end_turn":
                # 对话结束
                self.complete = True
                self.log_callback(f"[完成] 原因: {update.stopReason}")
                self.log_callback(f"[调试] 总共收集了 {len(self.message_chunks)} 个消息块")

        async def request_permission(self, options, session_id, tool_call, **kwargs):
            """处理权限请求 - 自动放行"""
            from acp.schema import RequestPermissionResponse, SelectedPermissionOutcome

            opt = options[0].optionId if options else "allow-once"
            self.log_callback(f"[权限] 自动放行: {opt}")

            return RequestPermissionResponse(
                outcome=SelectedPermissionOutcome(outcome="selected", optionId=opt)
            )

        async def read_text_file(self, path, session_id, **kwargs):
            """读取文本文件"""
            from acp.schema import ReadTextFileResponse

            p = Path(path)
            content = p.read_text(encoding="utf-8") if p.exists() else ""
            self.log_callback(f"[读文件] {path} ({len(content)} 字符)")
            return ReadTextFileResponse(content=content)

        async def write_text_file(self, content, path, session_id, **kwargs):
            """写入文本文件"""
            from acp.schema import WriteTextFileResponse

            Path(path).write_text(content, encoding="utf-8")
            self.log_callback(f"[写文件] {path} ({len(content)} 字符)")
            return WriteTextFileResponse()

        def get_message(self) -> str:
            """获取完整的消息内容"""
            return ''.join(self.message_chunks).strip()

        def get_thinking(self) -> str:
            """获取完整的思考过程"""
            return '\n'.join(self.thought_chunks)

        def clear(self):
            """清空缓存"""
            self.message_chunks = []
            self.thought_chunks = []
            self.tool_calls = []
            self.complete = False

    def _run_event_loop(self):
        """在独立线程中运行事件循环"""
        asyncio.set_event_loop(self._loop)
        self._loop.run_forever()

    def _run_async(self, coro):
        """在事件循环中运行异步协程"""
        if not self._loop or not self._loop.is_running():
            raise RuntimeError("事件循环未运行")

        future = asyncio.run_coroutine_threadsafe(coro, self._loop)
        return future.result()

    def initialize(self, protocol_version: int = 1) -> bool:
        """初始化 OpenClaw 连接"""
        try:
            from acp import spawn_agent_process, PROTOCOL_VERSION
            from acp.schema import InitializeRequest

            # 创建事件循环
            self._loop = asyncio.new_event_loop()
            self._thread = threading.Thread(target=self._run_event_loop, daemon=True)
            self._thread.start()

            args = ["acp", "--session", self.session]
            self._log(f"启动 OpenClaw: {self.executable} {' '.join(args)}")

            async def _init():
                try:
                    # 创建 handler 实例
                    handler = self.ACPClientHandler(self._log)

                    async with spawn_agent_process(
                        lambda _agent: handler,
                        self.executable,
                        *args,
                        transport_kwargs={"stderr": None}
                    ) as (conn, proc):
                        self._conn = conn
                        self._acp_handler = handler

                        # 初始化协议
                        init_res = await conn.initialize(
                            InitializeRequest(
                                protocolVersion=PROTOCOL_VERSION,
                                clientCapabilities={
                                    "fs": {
                                        "readTextFile": True,
                                        "writeTextFile": True,
                                    }
                                },
                            )
                        )

                        self._log(f"初始化成功: protocolVersion={init_res.protocolVersion}")
                        self._ready.set()
                        self._initialized = True

                        # 保持连接活跃
                        await asyncio.Future()

                except Exception as e:
                    self._log(f"异步初始化失败: {e}")
                    import traceback
                    traceback.print_exc()

            # 在事件循环中运行初始化
            asyncio.run_coroutine_threadsafe(_init(), self._loop)

            # 等待初始化完成
            if not self._ready.wait(timeout=30):
                raise Exception("初始化超时")

            return True

        except Exception as e:
            self._log(f"初始化失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def create_session(self, cwd: str, mcp_servers: list = None,
                      skills: list = None, system_prompt: str = None) -> bool:
        """创建 ACP 会话"""
        try:
            from acp.schema import NewSessionRequest

            async def _create_session():
                session = await self._conn.newSession(
                    NewSessionRequest(cwd=cwd, mcpServers=mcp_servers or [])
                )
                return session.sessionId

            session_id = self._run_async(_create_session())

            if session_id:
                self.session_id = session_id
                self._log(f"会话创建成功: {self.session_id}")

                # 尝试启用扩展思考模式
                try:
                    async def _set_thinking_mode():
                        # 尝试设置会话模式为扩展思考
                        await self._conn.call(
                            method="session/set_mode",
                            params={
                                "sessionId": self.session_id,
                                "mode": "extended_thinking"
                            }
                        )

                    self._run_async(_set_thinking_mode())
                    self._log("✅ 已启用扩展思考模式")
                except Exception as mode_error:
                    # 如果设置模式失败，继续执行（可能不支持）
                    self._log(f"⚠️ 设置扩展思考模式失败（可能不支持）: {mode_error}")

                return True

            return False

        except Exception as e:
            self._log(f"创建会话失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def chat(self, message: str, on_thinking=None, timeout: float = 180.0) -> str:
        """发送聊天消息（标准 ACP 接口）

        Args:
            message: 用户消息
            on_thinking: 思考过程回调函数
            timeout: 超时时间
        """
        try:
            from acp.schema import PromptRequest
            from acp import text_block

            async def _chat():
                # 清空之前的响应
                if self._acp_handler:
                    self._acp_handler.clear()

                # 发送 prompt - 使用 text_block 函数
                self._log(f"发送消息: {message[:50]}...")
                resp = await self._conn.prompt(
                    PromptRequest(
                        sessionId=self.session_id,
                        prompt=[text_block(message)]
                    )
                )

                # 等待响应完成，同时实时传递 thinking
                wait_time = 0
                last_thinking_length = 0

                while wait_time < timeout:
                    await asyncio.sleep(0.3)  # 更频繁的检查，以便实时传递 thinking
                    wait_time += 0.3

                    # 实时传递 thinking（如果启用）
                    if on_thinking and self._acp_handler and self._acp_handler.thought_chunks:
                        current_thinking = self._acp_handler.get_thinking()
                        # 只在 thinking 有新内容时调用回调
                        if len(current_thinking) > last_thinking_length:
                            new_content = current_thinking[last_thinking_length:]
                            on_thinking(new_content)
                            last_thinking_length = len(current_thinking)

                    if self._acp_handler and self._acp_handler.complete:
                        break

                # 获取响应
                if self._acp_handler:
                    response = self._acp_handler.get_message()

                    # 记录思考过程（如果没有回调）
                    if not on_thinking and self._acp_handler.thought_chunks:
                        thinking = self._acp_handler.get_thinking()
                        self._log(f"思考: {thinking[:100]}...")

                    # 记录工具调用
                    if self._acp_handler.tool_calls:
                        self._log(f"工具调用: {len(self._acp_handler.tool_calls)} 个")

                    self._log(f"响应完成: {len(response)} 字符, 原因: {resp.stopReason}")
                    return response
                else:
                    return ""

            result = self._run_async(_chat())
            return result if result else "（无响应）"

        except Exception as e:
            self._log(f"聊天失败: {e}")
            import traceback
            traceback.print_exc()
            return f"错误: {e}"

    def close(self):
        """关闭连接"""
        if self._loop and self._loop.is_running():
            self._loop.call_soon_threadsafe(self._loop.stop)

        if self._thread and self._thread.is_alive():
            self._thread.join(timeout=2)

        self._log("连接已关闭")
