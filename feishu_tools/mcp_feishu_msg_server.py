#!/usr/bin/env python3
"""
MCP Server: Feishu Message Sender
让 Kimi 能够通过 MCP 协议发送文本/富文本消息到飞书
自动获取当前聊天的 chat_id，支持群聊和单聊
"""

import json
import sys
import os
import time
import requests
from typing import Optional, Tuple

# 尝试导入配置（兼容开发模式和安装模式）
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)
sys.path.insert(0, project_root)

try:
    from src.config import PROJECT_ROOT, CONFIG, get_absolute_path
except ImportError:
    try:
        from clawdboz.config import PROJECT_ROOT, CONFIG, get_absolute_path
    except ImportError:
        PROJECT_ROOT = project_root
        CONFIG = {}
        def get_absolute_path(relative_path, project_root=None):
            root = project_root or PROJECT_ROOT
            if os.path.isabs(relative_path):
                return relative_path
            return os.path.join(root, relative_path)

paths_config = CONFIG.get('paths', {}) if CONFIG else {}
CONTEXT_FILE = get_absolute_path(paths_config.get('context_file', 'WORKPLACE/mcp_context.json'))


class FeishuMsgMCP:
    """飞书消息发送 MCP Server"""
    
    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self.tenant_token = None
        
    def _log(self, message: str):
        print(message, file=sys.stderr, flush=True)
    
    def _get_chat_type_display(self, chat_type: str) -> str:
        return "群聊" if chat_type == "group" else "单聊"
        
    def _get_current_chat_id(self) -> Tuple[Optional[str], Optional[str], str]:
        try:
            if not os.path.exists(CONTEXT_FILE):
                error_msg = f"上下文文件不存在: {CONTEXT_FILE}"
                self._log(error_msg)
                return None, None, "无法获取当前聊天。请先 @Bot 发送任意消息激活会话。"
            
            with open(CONTEXT_FILE, 'r') as f:
                context = json.load(f)
                chat_id = context.get('chat_id')
                chat_type = context.get('chat_type', 'group')
                timestamp = context.get('timestamp', 0)
                
                if time.time() - timestamp > 2592000:
                    self._log(f"上下文已过期，chat_id: {chat_id}")
                    return None, None, "会话已过期。请重新 @Bot 发送消息以激活当前聊天。"
                
                if not chat_id:
                    return None, None, "上下文中没有 chat_id"
                
                chat_type_display = self._get_chat_type_display(chat_type)
                self._log(f"获取到当前 {chat_type_display}: chat_id={chat_id}")
                return chat_id, chat_type, ""
                
        except json.JSONDecodeError as e:
            self._log(f"上下文文件格式错误: {e}")
            return None, None, "上下文文件损坏，请重新 @Bot 发送消息。"
        except Exception as e:
            self._log(f"读取上下文文件失败: {e}")
            return None, None, f"读取上下文失败: {e}"
        
    def _get_tenant_access_token(self) -> Optional[str]:
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
    
    def _send_text_message(self, chat_id: str, chat_type: str, text: str) -> Tuple[bool, str]:
        """发送文本消息"""
        try:
            if not self.tenant_token:
                self._get_tenant_access_token()
            
            if not self.tenant_token:
                return False, "获取 access token 失败"
            
            url = "https://open.feishu.cn/open-apis/im/v1/messages"
            headers = {
                "Authorization": f"Bearer {self.tenant_token}",
                "Content-Type": "application/json"
            }
            
            params = {"receive_id_type": "chat_id"}
            
            content = json.dumps({"text": text})
            
            body = {
                "receive_id": chat_id,
                "msg_type": "text",
                "content": content
            }
            
            resp = requests.post(url, headers=headers, params=params, json=body, timeout=30)
            result = resp.json()
            
            if result.get("code") == 0:
                self._log(f"文本消息发送成功")
                return True, ""
            else:
                error_code = result.get("code")
                error_msg = result.get("msg", "未知错误")
                chat_type_display = self._get_chat_type_display(chat_type)
                
                if error_code == 230002:
                    if chat_type == "p2p":
                        error_detail = "Bot 无法向该用户发送消息。请确保在单聊中先发送任意消息给 Bot 以建立会话。"
                    else:
                        error_detail = "Bot 不在该群聊中。请先将 Bot 添加到群聊，或在群聊中 @Bot 发送消息。"
                elif error_code == 40001:
                    error_detail = "身份验证失败，请检查 App ID 和 App Secret。"
                elif error_code == 230001:
                    error_detail = f"没有权限向该{chat_type_display}发送消息。"
                else:
                    error_detail = f"飞书 API 错误: {error_msg} (code: {error_code})"
                
                self._log(f"文本消息发送失败: {result}")
                return False, error_detail
                
        except Exception as e:
            error_msg = f"发送消息异常: {e}"
            self._log(error_msg)
            return False, error_msg
    
    def _send_rich_text_message(self, chat_id: str, chat_type: str, title: str, content: list) -> Tuple[bool, str]:
        """发送富文本消息（post 类型）"""
        try:
            if not self.tenant_token:
                self._get_tenant_access_token()
            
            if not self.tenant_token:
                return False, "获取 access token 失败"
            
            url = "https://open.feishu.cn/open-apis/im/v1/messages"
            headers = {
                "Authorization": f"Bearer {self.tenant_token}",
                "Content-Type": "application/json"
            }
            
            params = {"receive_id_type": "chat_id"}
            
            post_content = {
                "zh_cn": {
                    "title": title,
                    "content": content
                }
            }
            
            body = {
                "receive_id": chat_id,
                "msg_type": "post",
                "content": json.dumps(post_content)
            }
            
            resp = requests.post(url, headers=headers, params=params, json=body, timeout=30)
            result = resp.json()
            
            if result.get("code") == 0:
                self._log(f"富文本消息发送成功")
                return True, ""
            else:
                error_code = result.get("code")
                error_msg = result.get("msg", "未知错误")
                chat_type_display = self._get_chat_type_display(chat_type)
                
                if error_code == 230002:
                    error_detail = f"Bot 不在该{chat_type_display}中或无法发送消息。"
                elif error_code == 40001:
                    error_detail = "身份验证失败"
                else:
                    error_detail = f"飞书 API 错误: {error_msg}"
                
                self._log(f"富文本消息发送失败: {result}")
                return False, error_detail
                
        except Exception as e:
            return False, f"发送富文本消息异常: {e}"
    
    def handle_send_text(self, params: dict) -> dict:
        """处理发送文本消息请求"""
        text = params.get("text", "")
        
        if not text:
            return {"success": False, "error": "缺少参数: text"}
        
        chat_id, chat_type, error_msg = self._get_current_chat_id()
        if not chat_id:
            return {"success": False, "error": error_msg or "无法获取当前聊天 ID"}
        
        success, send_error = self._send_text_message(chat_id, chat_type or "group", text)
        
        if success:
            chat_type_display = self._get_chat_type_display(chat_type or "group")
            return {
                "success": True,
                "message": f"消息已成功发送到飞书{chat_type_display}",
                "chat_id": chat_id,
                "chat_type": chat_type or "group"
            }
        else:
            return {"success": False, "error": send_error or "消息发送失败"}
    
    def handle_send_rich_text(self, params: dict) -> dict:
        """处理发送富文本消息请求"""
        title = params.get("title", "")
        content = params.get("content", [])
        
        if not title or not content:
            return {"success": False, "error": "缺少参数: title 或 content"}
        
        chat_id, chat_type, error_msg = self._get_current_chat_id()
        if not chat_id:
            return {"success": False, "error": error_msg or "无法获取当前聊天 ID"}
        
        success, send_error = self._send_rich_text_message(chat_id, chat_type or "group", title, content)
        
        if success:
            return {
                "success": True,
                "message": f"富文本消息已成功发送到飞书",
                "chat_id": chat_id,
                "chat_type": chat_type or "group"
            }
        else:
            return {"success": False, "error": send_error or "富文本消息发送失败"}
    
    def run(self):
        """运行 MCP Server (stdio 模式)"""
        self._log("Feishu Message MCP Server 启动...")
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
                    "capabilities": {"tools": {}},
                    "serverInfo": {
                        "name": "feishu-message-sender",
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
                            "name": "send_feishu_text",
                            "description": "发送纯文本消息到当前飞书聊天（支持群聊和单聊）",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "text": {
                                        "type": "string",
                                        "description": "要发送的文本内容"
                                    }
                                },
                                "required": ["text"]
                            }
                        },
                        {
                            "name": "send_feishu_rich_text",
                            "description": "发送富文本消息（支持标题、多段落、格式化）到当前飞书聊天",
                            "inputSchema": {
                                "type": "object",
                                "properties": {
                                    "title": {
                                        "type": "string",
                                        "description": "消息标题"
                                    },
                                    "content": {
                                        "type": "array",
                                        "description": "内容段落列表，每个段落是一个 tag 数组",
                                        "items": {
                                            "type": "array",
                                            "items": {
                                                "type": "object",
                                                "properties": {
                                                    "tag": {"type": "string", "enum": ["text", "a", "at"]},
                                                    "text": {"type": "string"},
                                                    "href": {"type": "string"},
                                                    "user_id": {"type": "string"}
                                                }
                                            }
                                        }
                                    }
                                },
                                "required": ["title", "content"]
                            }
                        }
                    ]
                }
            })
        
        elif method == "tools/call":
            tool_name = params.get("name", "")
            tool_params = params.get("arguments", {})
            
            if tool_name == "send_feishu_text":
                result = self.handle_send_text(tool_params)
                self._send_response({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]
                    }
                })
            elif tool_name == "send_feishu_rich_text":
                result = self.handle_send_rich_text(tool_params)
                self._send_response({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "result": {
                        "content": [{"type": "text", "text": json.dumps(result, ensure_ascii=False, indent=2)}]
                    }
                })
            else:
                self._send_response({
                    "jsonrpc": "2.0",
                    "id": req_id,
                    "error": {"code": -32601, "message": f"未知工具: {tool_name}"}
                })
    
    def _send_response(self, response: dict):
        """发送响应"""
        print(json.dumps(response, ensure_ascii=False), flush=True)


if __name__ == "__main__":
    feishu_config = CONFIG.get('feishu', {}) if CONFIG else {}
    app_id = feishu_config.get('app_id') or os.environ.get('FEISHU_APP_ID')
    app_secret = feishu_config.get('app_secret') or os.environ.get('FEISHU_APP_SECRET')
    
    if not app_id or not app_secret:
        print("[ERROR] 缺少飞书应用配置", file=sys.stderr)
        sys.exit(1)
    
    server = FeishuMsgMCP(app_id, app_secret)
    server.run()
