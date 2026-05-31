#!/usr/bin/env python3
"""
Claude Code 轻量级 ACP stdio 适配器
不依赖 claude-agent-sdk 和 claude-code-acp
直接与 Claude CLI 的 --print --output-format stream-json 通信
"""

import json
import os
import subprocess
import sys
import uuid


class ClaudeAcpStdio:
    def __init__(self):
        self.sessions = {}

    def run(self):
        """主循环：从 stdin 读取 ACP JSON-RPC 请求"""
        for line in sys.stdin:
            line = line.strip()
            if not line:
                continue
            try:
                req = json.loads(line)
                self._handle_request(req)
            except Exception as e:
                self._send_error(
                    req.get("id") if isinstance(req, dict) else None, str(e)
                )

    def _handle_request(self, req):
        method = req.get("method")
        req_id = req.get("id")
        params = req.get("params", {})

        if method == "initialize":
            self._on_initialize(req_id, params)
        elif method == "session/new":
            self._on_new_session(req_id, params)
        elif method == "session/prompt":
            self._on_prompt(req_id, params)
        elif method == "session/request_permission":
            self._send_response(
                req_id,
                {"outcome": {"outcome": "selected", "optionId": "approve"}},
            )
        else:
            # 其他方法返回空结果
            self._send_response(req_id, {})

    def _on_initialize(self, req_id, params):
        self._send_response(
            req_id,
            {
                "protocolVersion": 1,
                "agentCapabilities": {
                    "prompt": {"text": True, "image": False},
                    "session": {"fork": {}, "list": {}, "resume": {}},
                },
            },
        )

    def _on_new_session(self, req_id, params):
        session_id = str(uuid.uuid4())
        cwd = params.get("cwd", os.getcwd())
        self.sessions[session_id] = {"cwd": cwd}
        self._send_response(req_id, {"sessionId": session_id})

    def _on_prompt(self, req_id, params):
        session_id = params.get("sessionId")
        prompt_blocks = params.get("prompt", [])
        message = self._extract_text(prompt_blocks)

        session = self.sessions.get(session_id, {})
        cwd = session.get("cwd", os.getcwd())

        # 构建 Claude CLI 命令
        cmd = [
            "claude",
            "--print",
            "--output-format", "stream-json",
            "--verbose",
            "--permission-mode", "dontAsk",
            "--no-session-persistence",
            message,
        ]

        result_text = []

        proc = subprocess.Popen(
            cmd,
            cwd=cwd,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
        )

        for line in proc.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                data = json.loads(line)
            except json.JSONDecodeError:
                continue

            t = data.get("type")
            if t == "assistant":
                msg = data.get("message", {})
                for block in msg.get("content", []):
                    bt = block.get("type")
                    if bt == "text":
                        text = block.get("text", "")
                        result_text.append(text)
                        self._emit_message_chunk(text)
                    elif bt == "thinking":
                        self._emit_thinking_chunk(block.get("thinking", ""))
            elif t == "result":
                text = data.get("result", "")
                if text and text not in result_text:
                    result_text.append(text)
                    self._emit_message_chunk(text)

        proc.wait()

        # 发送 end_turn 通知
        self._send_notification(
            "session/update",
            {"update": {"sessionUpdate": "end_turn"}},
        )

        result = "".join(result_text)
        self._send_response(
            req_id,
            {"stopReason": "end_turn", "result": result},
        )

    def _extract_text(self, blocks):
        parts = []
        for block in blocks:
            if isinstance(block, dict):
                if block.get("type") == "text":
                    parts.append(block.get("text", ""))
            elif hasattr(block, "text"):
                parts.append(block.text)
        return "\n".join(parts)

    def _emit_message_chunk(self, text):
        self._send_notification(
            "session/update",
            {
                "update": {
                    "sessionUpdate": "agent_message_chunk",
                    "content": {"type": "text", "text": text},
                }
            },
        )

    def _emit_thinking_chunk(self, text):
        self._send_notification(
            "session/update",
            {
                "update": {
                    "sessionUpdate": "agent_thought_chunk",
                    "content": {"type": "text", "text": text},
                }
            },
        )

    def _send_response(self, req_id, result):
        resp = {"jsonrpc": "2.0", "id": req_id, "result": result}
        print(json.dumps(resp, ensure_ascii=False))
        sys.stdout.flush()

    def _send_error(self, req_id, error):
        resp = {"jsonrpc": "2.0", "id": req_id, "error": {"message": error}}
        print(json.dumps(resp, ensure_ascii=False))
        sys.stdout.flush()

    def _send_notification(self, method, params):
        resp = {"jsonrpc": "2.0", "method": method, "params": params}
        print(json.dumps(resp, ensure_ascii=False))
        sys.stdout.flush()


if __name__ == "__main__":
    adapter = ClaudeAcpStdio()
    adapter.run()
