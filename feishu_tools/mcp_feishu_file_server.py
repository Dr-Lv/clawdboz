#!/usr/bin/env python3
"""
MCP Server: Feishu File Sender
让 Kimi 能够通过 MCP 协议发送文件到飞书消息
自动获取当前聊天的 chat_id，支持群聊和单聊
"""

import json
import sys
import os
import time
import requests
from typing import Optional, Tuple

# 导入 src 中的配置模块
# 添加项目根目录到路径
script_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(script_dir)  # feishu_tools/ 的父目录是项目根目录
sys.path.insert(0, project_root)
from src.config import PROJECT_ROOT, CONFIG, get_absolute_path

# 上下文文件路径，存储当前聊天的 chat_id
paths_config = CONFIG.get('paths', {})
CONTEXT_FILE = get_absolute_path(paths_config.get('context_file', 'WORKPLACE/mcp_context.json'))


class FeishuFileMCP:
    """飞书文件发送 MCP Server"""
    
    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self.tenant_token = None
        
    def _log(self, message: str):
        """输出日志到 stderr"""
        print(message, file=sys.stderr, flush=True)
    
    def _get_chat_type_display(self, chat_type: str) -> str:
        """获取聊天类型的显示名称"""
        return "群聊" if chat_type == "group" else "单聊"
        
    def _get_current_chat_id(self) -> Tuple[Optional[str], Optional[str], str]:
        """从上下文文件获取当前聊天的 chat_id 和类型
        
        Returns:
            tuple: (chat_id, chat_type, error_message)
            chat_id: 获取到的 chat_id，失败时为 None
            chat_type: 聊天类型 ('group' 或 'p2p')，失败时为 None
            error_message: 错误信息，成功时为空字符串
        """
        try:
            if not os.path.exists(CONTEXT_FILE):
                error_msg = f"上下文文件不存在: {CONTEXT_FILE}"
                self._log(error_msg)
                return None, None, "无法获取当前聊天。请先 @Bot 发送任意消息激活会话。"
            
            with open(CONTEXT_FILE, 'r') as f:
                context = json.load(f)
                chat_id = context.get('chat_id')
                chat_type = context.get('chat_type', 'group')  # 默认为群聊
                timestamp = context.get('timestamp', 0)
                
                # 检查上下文时效性（30天内有效）
                if time.time() - timestamp > 2592000:
                    self._log(f"上下文已过期，chat_id: {chat_id}, chat_type: {chat_type}")
                    return None, None, "会话已过期。请重新 @Bot 发送消息以激活当前聊天。"
                
                if not chat_id:
                    return None, None, "上下文中没有 chat_id"
                
                chat_type_display = self._get_chat_type_display(chat_type)
                self._log(f"获取到当前 {chat_type_display}: chat_id={chat_id} (更新时间: {time.strftime('%H:%M:%S', time.localtime(timestamp))})")
                return chat_id, chat_type, ""
                
        except json.JSONDecodeError as e:
            error_msg = f"上下文文件格式错误: {e}"
            self._log(error_msg)
            return None, None, "上下文文件损坏，请重新 @Bot 发送消息。"
        except Exception as e:
            error_msg = f"读取上下文文件失败: {e}"
            self._log(error_msg)
            return None, None, f"读取上下文失败: {e}"
        
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
    
    def _send_file_message(self, chat_id: str, chat_type: str, file_key: str) -> Tuple[bool, str]:
        """发送文件消息
        
        Args:
            chat_id: 聊天 ID
            chat_type: 聊天类型 ('group' 或 'p2p')
            file_key: 文件 key
            
        Returns:
            tuple: (success, error_message)
        """
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
            
            # 飞书 API：群聊和单聊都使用 chat_id 作为 receive_id_type
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
                return True, ""
            else:
                error_code = result.get("code")
                error_msg = result.get("msg", "未知错误")
                chat_type_display = self._get_chat_type_display(chat_type)
                
                # 针对特定错误码给出友好提示
                if error_code == 230002:
                    if chat_type == "p2p":
                        error_detail = f"Bot 无法向该用户发送消息。请确保在单聊中先发送任意消息给 Bot 以建立会话。"
                    else:
                        error_detail = f"Bot 不在该群聊中。请先将 Bot 添加到群聊，或在群聊中 @Bot 发送消息。"
                elif error_code == 40001:
                    error_detail = "身份验证失败，请检查 App ID 和 App Secret。"
                elif error_code == 40002:
                    error_detail = "tenant_access_token 无效或已过期。"
                elif error_code == 112:
                    error_detail = "频率限制，请稍后再试。"
                elif error_code == 10002:
                    error_detail = f"找不到该{chat_type_display}，请检查 chat_id 是否正确。"
                elif error_code == 230001:
                    error_detail = f"没有权限向该{chat_type_display}发送消息。"
                else:
                    error_detail = f"飞书 API 错误: {error_msg} (code: {error_code})"
                
                self._log(f"文件消息发送失败: {result}")
                return False, error_detail
                
        except Exception as e:
            error_msg = f"发送消息异常: {e}"
            self._log(error_msg)
            return False, error_msg
    
    def handle_send_file(self, params: dict) -> dict:
        """处理发送文件请求"""
        file_path = params.get("file_path", "")
        
        if not file_path:
            return {
                "success": False,
                "error": "缺少参数: file_path"
            }
        
        # 自动获取当前 chat_id 和 chat_type
        chat_id, chat_type, error_msg = self._get_current_chat_id()
        if not chat_id:
            return {
                "success": False,
                "error": error_msg or "无法获取当前聊天 ID"
            }
        
        # 上传文件
        file_key = self._upload_file(file_path)
        if not file_key:
            return {
                "success": False,
                "error": f"文件上传失败: {file_path}"
            }
        
        # 发送文件消息
        success, send_error = self._send_file_message(chat_id, chat_type or "group", file_key)
        
        if success:
            chat_type_display = self._get_chat_type_display(chat_type or "group")
            return {
                "success": True,
                "message": f"文件已成功发送到飞书{chat_type_display}",
                "chat_id": chat_id,
                "chat_type": chat_type or "group",
                "file_name": os.path.basename(file_path)
            }
        else:
            return {
                "success": False,
                "error": send_error or "文件消息发送失败"
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
                        "version": "1.1.0"
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
                            "description": "发送文件到当前飞书聊天（支持群聊和单聊）",
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
    # 从配置文件读取
    feishu_config = CONFIG.get('feishu', {})
    app_id = feishu_config.get('app_id')
    app_secret = feishu_config.get('app_secret')
    
    if not app_id or not app_secret:
        print("[ERROR] 缺少飞书应用配置 (app_id 或 app_secret)", file=sys.stderr)
        sys.exit(1)
    
    server = FeishuFileMCP(app_id, app_secret)
    server.run()
