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
            # 返回可用工具列表
            tools = {
                "tools": [
                    {
                        "name": "send_message",
                        "description": "发送文本消息到 Web Chat",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "message": {
                                    "type": "string",
                                    "description": "要发送的消息内容"
                                },
                                "chat_id": {
                                    "type": "string",
                                    "description": "目标聊天 ID（可选，默认当前聊天）"
                                }
                            },
                            "required": ["message"]
                        }
                    },
                    {
                        "name": "send_file",
                        "description": "发送文件到 Web Chat",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "file_path": {
                                    "type": "string",
                                    "description": "要发送的文件路径"
                                },
                                "file_name": {
                                    "type": "string",
                                    "description": "显示的文件名（可选）"
                                },
                                "chat_id": {
                                    "type": "string",
                                    "description": "目标聊天 ID（可选，默认当前聊天）"
                                }
                            },
                            "required": ["file_path"]
                        }
                    },
                    {
                        "name": "notify",
                        "description": "发送通知消息（用于定时任务状态更新）",
                        "inputSchema": {
                            "type": "object",
                            "properties": {
                                "title": {
                                    "type": "string",
                                    "description": "通知标题"
                                },
                                "content": {
                                    "type": "string",
                                    "description": "通知内容"
                                },
                                "type": {
                                    "type": "string",
                                    "enum": ["info", "success", "warning", "error"],
                                    "description": "通知类型"
                                }
                            },
                            "required": ["title", "content"]
                        }
                    }
                ]
            }
            self._send_response(msg_id, tools)
            
        elif method == "tools/call":
            # 执行工具调用
            tool_name = params.get('name')
            tool_params = params.get('arguments', {})
            result = self._call_tool(tool_name, tool_params)
            # 返回标准 MCP 格式的响应
            self._send_response(msg_id, {
                "content": [
                    {
                        "type": "text",
                        "text": json.dumps(result, ensure_ascii=False)
                    }
                ]
            })
            
    def _call_tool(self, name: str, params: dict) -> dict:
        """调用工具"""
        import os
        import urllib.request
        import urllib.error
        
        # 从环境变量获取 Web Chat API 地址和 Token
        webchat_url = os.environ.get('CLAWDBOZ_WEBCHAT_URL', 'http://localhost:8080')
        token = os.environ.get('CLAWDBOZ_WEBCHAT_TOKEN', 'demo-token-123456')
        
        def broadcast_to_webchat(data: dict) -> bool:
            """通过 HTTP API 广播消息到 Web Chat"""
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
                    return response.status == 200
            except Exception as e:
                print(f"[MCP] 广播失败: {e}", file=sys.stderr)
                return False
        
        if name == "send_message":
            message = params.get('message', '')
            # 发送消息到 Web Chat
            broadcast_to_webchat({
                "type": "mcp_message",
                "content": message
            })
            return {"success": True, "message": f"消息已发送: {message[:50]}..."}
            
        elif name == "send_file":
            file_path = params.get('file_path', '')
            # 将文件复制到 uploads 目录，供下载
            file_name = os.path.basename(file_path)
            
            if os.path.exists(file_path):
                # 获取 uploads 目录路径（与 server.py 一致）
                upload_dir = os.path.join(os.path.dirname(__file__), "uploads")
                os.makedirs(upload_dir, exist_ok=True)
                
                # 生成唯一文件名
                import uuid
                file_ext = os.path.splitext(file_name)[1]
                file_id = f"{uuid.uuid4().hex}{file_ext}"
                dest_path = os.path.join(upload_dir, file_id)
                
                # 复制文件
                import shutil
                shutil.copy2(file_path, dest_path)
                file_size = os.path.getsize(file_path)
                
                # 生成下载 URL
                file_url = f"/uploads/{file_id}"
                
                broadcast_to_webchat({
                    "type": "mcp_file",
                    "file_name": file_name,
                    "file_path": file_path,
                    "file_size": file_size,
                    "file_url": file_url
                })
                return {"success": True, "file_path": file_path, "file_url": file_url, "status": "file_sent"}
            else:
                return {"success": False, "error": f"文件不存在: {file_path}"}
            
        elif name == "notify":
            title = params.get('title', '')
            content = params.get('content', '')
            notify_type = params.get('type', 'info')
            # 发送通知到 Web Chat
            broadcast_to_webchat({
                "type": "mcp_notify",
                "title": title,
                "content": content,
                "notify_type": notify_type
            })
            return {"success": True, "title": title, "status": "notification_sent"}
            
        else:
            return {"success": False, "error": f"未知工具: {name}"}
            
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
