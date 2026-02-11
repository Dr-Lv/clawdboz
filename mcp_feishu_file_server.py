#!/usr/bin/env python3
"""
MCP Server: Feishu File Sender
让 Kimi 能够通过 MCP 协议发送文件到飞书消息
自动获取当前聊天的 chat_id
"""

import json
import sys
import os
import requests
from typing import Optional

# 上下文文件路径，存储当前聊天的 chat_id
CONTEXT_FILE = os.path.join(os.path.dirname(__file__), 'WORKPLACE', 'mcp_context.json')


class FeishuFileMCP:
    """飞书文件发送 MCP Server"""
    
    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self.tenant_token = None
        
    def _log(self, message: str):
        """输出日志到 stderr"""
        print(message, file=sys.stderr, flush=True)
        
    def _get_current_chat_id(self) -> Optional[str]:
        """从上下文文件获取当前聊天的 chat_id"""
        try:
            if os.path.exists(CONTEXT_FILE):
                with open(CONTEXT_FILE, 'r') as f:
                    context = json.load(f)
                    chat_id = context.get('chat_id')
                    self._log(f"获取到当前 chat_id: {chat_id}")
                    return chat_id
            else:
                self._log(f"上下文文件不存在: {CONTEXT_FILE}")
                return None
        except Exception as e:
            self._log(f"读取上下文文件失败: {e}")
            return None
        
    def _get_tenant_access_token(self) -> Optional[str]:
        """获取 tenant_access_token"""
        try:
            url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
            resp = requests.post(url, json={
                "app_id": self.app_id,
                "app_secret": self.app_secret
            }, timeout=30)
            data = resp.json()
            if data.get("code") == 0:
                self.tenant_token = data.get("tenant_access_token")
                return self.tenant_token
            else:
                self._log(f"获取 token 失败: {data}")
                return None
        except Exception as e:
            self._log(f"获取 token 异常: {e}")
            return None
    
    def _upload_file(self, file_path: str) -> Optional[str]:
        """上传文件到飞书，返回 file_key"""
        try:
            if not os.path.exists(file_path):
                self._log(f"文件不存在: {file_path}")
                return None
            
            # 确保有 token
            if not self.tenant_token:
                self._get_tenant_access_token()
            
            if not self.tenant_token:
                return None
            
            url = "https://open.feishu.cn/open-apis/im/v1/files"
            headers = {"Authorization": f"Bearer {self.tenant_token}"}
            
            file_name = os.path.basename(file_path)
            
            with open(file_path, 'rb') as f:
                files = {'file': (file_name, f)}
                data = {'file_type': 'stream', 'file_name': file_name}
                resp = requests.post(url, headers=headers, files=files, data=data, timeout=60)
            
            result = resp.json()
            if result.get("code") == 0:
                file_key = result.get("data", {}).get("file_key")
                self._log(f"文件上传成功: {file_key}")
                return file_key
            else:
                self._log(f"文件上传失败: {result}")
                return None
                
        except Exception as e:
            self._log(f"上传文件异常: {e}")
            return None
    
    def _send_file_message(self, chat_id: str, file_key: str) -> bool:
        """发送文件消息"""
        try:
            if not self.tenant_token:
                self._get_tenant_access_token()
            
            if not self.tenant_token:
                return False
            
            url = "https://open.feishu.cn/open-apis/im/v1/messages"
            headers = {
                "Authorization": f"Bearer {self.tenant_token}",
                "Content-Type": "application/json"
            }
            params = {"receive_id_type": "chat_id"}
            
            # 文件消息内容
            content = json.dumps({
                "file_key": file_key
            })
            
            body = {
                "receive_id": chat_id,
                "msg_type": "file",
                "content": content
            }
            
            resp = requests.post(url, headers=headers, params=params, json=body, timeout=30)
            result = resp.json()
            
            if result.get("code") == 0:
                self._log(f"文件消息发送成功")
                return True
            else:
                self._log(f"文件消息发送失败: {result}")
                return False
                
        except Exception as e:
            self._log(f"发送消息异常: {e}")
            return False
    
    def handle_send_file(self, params: dict) -> dict:
        """处理发送文件请求"""
        file_path = params.get("file_path", "")
        
        if not file_path:
            return {
                "success": False,
                "error": "缺少参数: file_path"
            }
        
        # 自动获取当前 chat_id
        chat_id = self._get_current_chat_id()
        if not chat_id:
            return {
                "success": False,
                "error": "无法获取当前聊天 ID，请确保是在飞书群聊中使用"
            }
        
        # 上传文件
        file_key = self._upload_file(file_path)
        if not file_key:
            return {
                "success": False,
                "error": f"文件上传失败: {file_path}"
            }
        
        # 发送文件消息
        success = self._send_file_message(chat_id, file_key)
        
        if success:
            return {
                "success": True,
                "message": f"文件已成功发送到飞书",
                "chat_id": chat_id,
                "file_name": os.path.basename(file_path)
            }
        else:
            return {
                "success": False,
                "error": "文件消息发送失败"
            }
    
    def run(self):
        """运行 MCP Server (stdio 模式)"""
        self._log("Feishu File MCP Server 启动...")
        self._log(f"上下文文件: {CONTEXT_FILE}")
        
        while True:
            try:
                line = sys.stdin.readline()
                if not line:
                    break
                
                line = line.strip()
                if not line:
                    continue
                
                request = json.loads(line)
                self._handle_request(request)
                
            except json.JSONDecodeError as e:
                self._log(f"JSON 解析错误: {e}")
            except Exception as e:
                self._log(f"处理请求异常: {e}")
    
    def _handle_request(self, request: dict):
        """处理请求"""
        method = request.get("method", "")
        req_id = request.get("id")
        params = request.get("params", {})
        
        if method == "initialize":
            self._send_response({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "protocolVersion": "2024-11-05",
                    "capabilities": {
                        "tools": {}
                    },
                    "serverInfo": {
                        "name": "feishu-file-sender",
                        "version": "1.0.0"
                    }
                }
            })
        
        elif method == "tools/list":
            self._send_response({
                "jsonrpc": "2.0",
                "id": req_id,
                "result": {
                    "tools": [
                        {
                            "name": "send_feishu_file",
                            "description": "发送文件到当前飞书聊天",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "file_path": {
                                        "type": "string",
                                        "description": "本地文件路径"
                                    }
                                },
                                "required": ["file_path"]
                            }
                        }
                    ]
                }
            })
        
        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_params = params.get("arguments", {})
            
            if tool_name == "send_feishu_file":
                result = self.handle_send_file(tool_params)
                self._send_response({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [
                            {
                                "type": "text",
                                "text": json.dumps(result, ensure_ascii=False, indent=2)
                            }
                        ]
                    }
                })
            else:
                self._send_response({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {
                        "code": -32601,
                        "message": f"未知工具: {tool_name}"
                    }
                })
    
    def _send_response(self, response: dict):
        """发送响应"""
        print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    # 硬编码配置（避免环境变量传递问题）
    app_id = "cli_a90ded6b63f89cd6"
    app_secret = "3WDKvIVUHPYVXbEVYjRgRg2wORBDb5z3"
    
    server = FeishuFileMCP(app_id, app_secret)
    server.run()
