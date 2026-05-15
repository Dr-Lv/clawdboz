#!/usr/bin/env python3
"""OpenClaw ACP 客户端 - 使用适配器转换为标准 ACP 接口"""
from typing import Optional, Tuple


class OpenClawACPClient:
    """OpenClaw ACP 客户端 - 标准接口实现"""

    def __init__(self, executable: str = "/opt/homebrew/bin/openclaw",
                 session: str = "agent:main:main",
                 log_callback=None):
        """初始化 OpenClaw ACP 客户端"""
        self.executable = executable
        self.session = session
        self.log_callback = log_callback or self._default_log
        self.session_id = None
        self._adapter = None

    def _default_log(self, message: str):
        """默认日志输出"""
        print(f"[OpenClaw-ACP] {message}")

    def _log(self, message: str):
        """记录日志"""
        self.log_callback(message)

    def initialize(self, protocol_version: int = 1) -> bool:
        """初始化 ACP 协议"""
        try:
            from .openclaw_adapter import OpenClawToACPAdapter

            self._log("使用 OpenClaw 适配器初始化...")

            self._adapter = OpenClawToACPAdapter(
                executable=self.executable,
                session=self.session,
                log_callback=self._log
            )

            result = self._adapter.initialize(protocol_version)

            if result:
                self._log("✅ 初始化成功")
            else:
                self._log("❌ 初始化失败")

            return result

        except Exception as e:
            self._log(f"初始化失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def create_session(self, cwd: str, mcp_servers: list = None,
                      skills: list = None, system_prompt: str = None) -> bool:
        """创建 ACP 会话"""
        if not self._adapter:
            self._log("适配器未初始化")
            return False

        try:
            result = self._adapter.create_session(
                cwd=cwd,
                mcp_servers=mcp_servers,
                skills=skills,
                system_prompt=system_prompt
            )

            if result:
                self.session_id = self._adapter.session_id

            return result

        except Exception as e:
            self._log(f"创建会话失败: {e}")
            return False

    def call_method(self, method: str, params: dict = None,
                    timeout: float = 180.0) -> Tuple[Optional[dict], Optional[str]]:
        """调用 ACP 方法"""
        if not self._adapter:
            return None, "适配器未初始化"

        try:
            if method == 'chat':
                message = params.get('message', '')
                result = self.chat(message, timeout)
                return result, None
            else:
                return None, f"不支持的方法: {method}"

        except Exception as e:
            return None, f"调用失败: {e}"

    def chat(self, message: str, on_thinking=None, timeout: float = 180.0) -> str:
        """发送聊天消息

        Args:
            message: 用户消息
            on_thinking: 思考过程回调函数
            timeout: 超时时间
        """
        if not self._adapter:
            return "错误: 适配器未初始化"

        try:
            self._log(f"发送消息: {message[:50]}...")
            result = self._adapter.chat(message, on_thinking=on_thinking, timeout=timeout)

            if result:
                self._log(f"✅ 响应成功: {len(result)} 字符")
            else:
                self._log("⚠️  响应为空")

            return result

        except Exception as e:
            self._log(f"聊天失败: {e}")
            import traceback
            traceback.print_exc()
            return f"错误: {e}"

    def close(self):
        """关闭连接"""
        if self._adapter:
            self._adapter.close()
            self._log("✅ 连接已关闭")
