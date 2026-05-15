#!/usr/bin/env python3
"""
Web Chat MCP Server - 同步版本
为本地 Web Chat 提供 MCP 工具支持
"""

import json
import sys
from typing import Dict, Any, Optional


class WebChatMCPServer:
    """
    Web Chat MCP 服务器
    通过标准输入输出与 ACP 客户端通信
    """
    
    def __init__(self):
        self.request_id_counter = 0
        self.web_chat_server = None
        
    def set_web_chat_server(self, server):
        """设置 WebChatServer 引用"""
        self.web_chat_server = server
        
    def run(self):
        """运行 MCP 服务器"""
        # 注意：不发送 server/initialized，与飞书 MCP 保持一致
        
        # 读取 stdin 处理请求
        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    break
                    
                message = json.loads(line.strip())
                self._handle_message(message)
            except json.JSONDecodeError:
                continue
            except Exception as e:
                print(f"Error handling message: {e}", file=sys.stderr)
                
    def _handle_message(self, message: dict):
        """处理收到的消息"""
        msg_id = message.get('id')
        method = message.get('method')
        params = message.get('params', {})
        
        if method == "initialize":
            # 必须响应 initialize 请求，否则 kimi acp 会卡住
            self._send_response(msg_id, {
                "protocolVersion": "2024-11-05",
                "capabilities": {
                    "tools": {}
                },
                "serverInfo": {
                    "name": "webchat-mcp-server",
                    "version": "1.0.0"
                }
            })
            # 不发送 server/initialized 通知，保持与飞书 MCP 一致
        
        elif method == "tools/list":
            # 返回空工具列表（使用 skill 模式替代 MCP 工具）
            # Web Chat 模式下，发送消息/文件通过 webchat-sender skill 实现
            tools = {"tools": []}
            self._send_response(msg_id, tools)
            
        elif method == "tools/call":
            # MCP 工具已禁用，返回错误提示使用 skill 模式
            self._send_response(msg_id, {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps({
                            "success": False,
                            "error": "MCP 工具已禁用，请使用 webchat-sender skill 发送消息和文件"
                        }, ensure_ascii=False)
                    }
                ]
            })
            
    def _broadcast_via_api(self, data: dict) -> dict:
        """
        通过 HTTP API 广播消息到 Web Chat
        供 skill 调用使用
        """
        import urllib.request
        
        webchat_url = os.environ.get('CLAWDBOZ_WEBCHAT_URL', 'http://localhost:8080')
        token = os.environ.get('CLAWDBOZ_WEBCHAT_TOKEN', 'demo-token-123456')
        
        try:
            url = f"{webchat_url}/api/mcp/broadcast"
            data['_token'] = token
            json_data = json.dumps(data).encode('utf-8')
            
            req = urllib.request.Request(
                url,
                data=json_data,
                headers={'Content-Type': 'application/json'},
                method='POST'
            )
            
            with urllib.request.urlopen(req, timeout=5) as response:
                if response.status == 200:
                    return {"success": True}
                else:
                    return {"success": False, "error": f"HTTP {response.status}"}
        except Exception as e:
            return {"success": False, "error": str(e)}
            
    def _send_response(self, msg_id: Any, result: dict):
        """发送响应"""
        response = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "result": result
        }
        print(json.dumps(response), flush=True)
        
    def _send_notification(self, method: str, params: dict):
        """发送通知"""
        notification = {
            "jsonrpc": "2.0",
            "method": method,
            "params": params
        }
        print(json.dumps(notification), flush=True)


def main():
    """主入口"""
    server = WebChatMCPServer()
    server.run()


if __name__ == "__main__":
    main()
