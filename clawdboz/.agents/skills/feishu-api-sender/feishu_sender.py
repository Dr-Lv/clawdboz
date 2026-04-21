#!/usr/bin/env python3
"""
飞书 API 直接发送工具（绕过有问题的 MCP）
直接调用飞书开放平台的 HTTP API
"""
import requests
import json
import os
import sys

def _load_config():
    """从 bot 项目的 config.json 加载配置
    
    向上级目录搜索 config.json（通常位于 bot 项目根目录）
    """
    # 优先从环境变量获取项目目录
    if 'CLAWDBOZ_WORKPLACE' in os.environ:
        workplace = os.environ['CLAWDBOZ_WORKPLACE']
        candidate = os.path.join(os.path.dirname(workplace), 'config.json')
        if os.path.exists(candidate):
            try:
                with open(candidate, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
    
    # 从当前文件位置向上搜索 config.json
    current_dir = os.path.dirname(os.path.abspath(__file__))
    for _ in range(10):
        candidate = os.path.join(current_dir, 'config.json')
        if os.path.exists(candidate):
            try:
                with open(candidate, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception:
                pass
        parent = os.path.dirname(current_dir)
        if parent == current_dir:
            break
        current_dir = parent
    
    return {}


def _get_config_value(key_path, default=None):
    """从 config.json 获取配置值，支持嵌套路径如 'feishu.app_id'"""
    config = _load_config()
    keys = key_path.split('.')
    value = config
    for key in keys:
        if isinstance(value, dict) and key in value:
            value = value[key]
        else:
            return default
    return value


def _get_mcp_context_chat_id():
    """从 WORKPLACE/mcp_context.json 中读取 chat_id"""
    current_dir = os.path.dirname(os.path.abspath(__file__))
    for _ in range(10):
        candidate = os.path.join(current_dir, 'WORKPLACE', 'mcp_context.json')
        if os.path.exists(candidate):
            try:
                with open(candidate, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                return data.get('chat_id')
            except Exception:
                pass
        parent = os.path.dirname(current_dir)
        if parent == current_dir:
            break
        current_dir = parent
    return None


class FeishuSender:
    """飞书消息发送器"""
    
    def __init__(self, app_id=None, app_secret=None, chat_id=None):
        # 仅从 config.json 读取配置，传入参数仅用于覆盖
        config_app_id = _get_config_value('feishu.app_id')
        config_app_secret = _get_config_value('feishu.app_secret')
        config_chat_id = _get_config_value('feishu.chat_id')
        mcp_chat_id = _get_mcp_context_chat_id()
        
        self.app_id = app_id if app_id is not None else config_app_id
        self.app_secret = app_secret if app_secret is not None else config_app_secret
        self.chat_id = chat_id if chat_id is not None else (mcp_chat_id or config_chat_id)
        
        if not self.app_id or not self.app_secret or not self.chat_id:
            raise ValueError("缺少飞书配置，请确保上级目录的 config.json 中包含 feishu.app_id、feishu.app_secret，或在 WORKPLACE/mcp_context.json 中提供 chat_id")
        
        self._token = None
    
    def _get_access_token(self) -> str:
        """获取 tenant_access_token"""
        if self._token:
            return self._token
            
        url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
        headers = {"Content-Type": "application/json"}
        data = {
            "app_id": self.app_id,
            "app_secret": self.app_secret
        }
        
        try:
            response = requests.post(url, headers=headers, json=data, timeout=10)
            result = response.json()
            
            if result.get("code") == 0:
                self._token = result["tenant_access_token"]
                return self._token
            else:
                raise Exception(f"获取 token 失败: {result.get('msg')}")
        except Exception as e:
            raise Exception(f"请求 token 失败: {e}")
    
    def send_text(self, text: str, chat_id: str = None) -> dict:
        """
        发送文本消息
        
        Args:
            text: 消息内容
            chat_id: 可选，指定聊天 ID
            
        Returns:
            {"success": True/False, "message": "...", "data": {...}}
        """
        try:
            token = self._get_access_token()
            target_chat = chat_id or self.chat_id
            
            url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            data = {
                "receive_id": target_chat,
                "msg_type": "text",
                "content": json.dumps({"text": text})
            }
            
            response = requests.post(url, headers=headers, json=data, timeout=10)
            result = response.json()
            
            if result.get("code") == 0:
                return {
                    "success": True,
                    "message": "文本消息发送成功",
                    "data": result.get("data", {})
                }
            else:
                return {
                    "success": False,
                    "message": f"发送失败: {result.get('msg')}",
                    "data": result
                }
                
        except Exception as e:
            return {
                "success": False,
                "message": f"发送异常: {e}",
                "data": {}
            }
    
    def send_image(self, image_path: str, chat_id: str = None) -> dict:
        """
        发送图片消息
        
        Args:
            image_path: 图片文件路径
            chat_id: 可选，指定聊天 ID
            
        Returns:
            {"success": True/False, "message": "...", "data": {...}}
        """
        try:
            if not os.path.exists(image_path):
                return {
                    "success": False,
                    "message": f"图片不存在: {image_path}",
                    "data": {}
                }
            
            token = self._get_access_token()
            target_chat = chat_id or self.chat_id
            
            # 1. 上传图片
            upload_url = "https://open.feishu.cn/open-apis/im/v1/images"
            headers = {"Authorization": f"Bearer {token}"}
            
            with open(image_path, 'rb') as f:
                files = {'image': f}
                data = {'image_type': 'message'}
                response = requests.post(upload_url, headers=headers, files=files, data=data, timeout=30)
            
            result = response.json()
            if result.get("code") != 0:
                return {
                    "success": False,
                    "message": f"图片上传失败: {result.get('msg')}",
                    "data": result
                }
            
            image_key = result["data"]["image_key"]
            
            # 2. 发送图片消息
            url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            data = {
                "receive_id": target_chat,
                "msg_type": "image",
                "content": json.dumps({"image_key": image_key})
            }
            
            response = requests.post(url, headers=headers, json=data, timeout=10)
            result = response.json()
            
            if result.get("code") == 0:
                return {
                    "success": True,
                    "message": "图片发送成功",
                    "data": result.get("data", {})
                }
            else:
                return {
                    "success": False,
                    "message": f"图片消息发送失败: {result.get('msg')}",
                    "data": result
                }
                
        except Exception as e:
            return {
                "success": False,
                "message": f"发送异常: {e}",
                "data": {}
            }
    
    def send_file(self, file_path: str, file_name: str = None, chat_id: str = None) -> dict:
        """
        发送文件
        
        Args:
            file_path: 文件路径
            file_name: 可选，自定义文件名
            chat_id: 可选，指定聊天 ID
            
        Returns:
            {"success": True/False, "message": "...", "data": {...}}
        """
        try:
            if not os.path.exists(file_path):
                return {
                    "success": False,
                    "message": f"文件不存在: {file_path}",
                    "data": {}
                }
            
            token = self._get_access_token()
            target_chat = chat_id or self.chat_id
            
            if file_name is None:
                file_name = os.path.basename(file_path)
            
            # 1. 上传文件
            upload_url = "https://open.feishu.cn/open-apis/im/v1/files"
            headers = {"Authorization": f"Bearer {token}"}
            
            with open(file_path, 'rb') as f:
                files = {'file': (file_name, f)}
                data = {
                    'file_type': 'stream',
                    'file_name': file_name
                }
                response = requests.post(upload_url, headers=headers, files=files, data=data, timeout=30)
            
            result = response.json()
            if result.get("code") != 0:
                return {
                    "success": False,
                    "message": f"文件上传失败: {result.get('msg')}",
                    "data": result
                }
            
            file_key = result["data"]["file_key"]
            
            # 2. 发送文件消息
            url = "https://open.feishu.cn/open-apis/im/v1/messages?receive_id_type=chat_id"
            headers = {
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json"
            }
            data = {
                "receive_id": target_chat,
                "msg_type": "file",
                "content": json.dumps({"file_key": file_key})
            }
            
            response = requests.post(url, headers=headers, json=data, timeout=10)
            result = response.json()
            
            if result.get("code") == 0:
                return {
                    "success": True,
                    "message": "文件发送成功",
                    "data": result.get("data", {})
                }
            else:
                return {
                    "success": False,
                    "message": f"文件消息发送失败: {result.get('msg')}",
                    "data": result
                }
                
        except Exception as e:
            return {
                "success": False,
                "message": f"发送异常: {e}",
                "data": {}
            }


# 便捷函数（默认实例）
_default_sender = None

def _get_default_sender():
    global _default_sender
    if _default_sender is None:
        _default_sender = FeishuSender()
    return _default_sender

def send_text(text: str, chat_id: str = None) -> dict:
    """发送文本消息"""
    return _get_default_sender().send_text(text, chat_id)

def send_image(image_path: str, chat_id: str = None) -> dict:
    """发送图片"""
    return _get_default_sender().send_image(image_path, chat_id)

def send_file(file_path: str, file_name: str = None, chat_id: str = None) -> dict:
    """发送文件"""
    return _get_default_sender().send_file(file_path, file_name, chat_id)


# 命令行入口
if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: python feishu_sender.py <text|image|file> <content> [chat_id]")
        print("")
        print("Examples:")
        print('  python feishu_sender.py text "Hello World"')
        print('  python feishu_sender.py image "screenshots/qr.png"')
        print('  python feishu_sender.py file "document.pdf" "custom_name.pdf"')
        sys.exit(1)
    
    cmd = sys.argv[1]
    sender = FeishuSender()
    
    if cmd == "text":
        text = sys.argv[2] if len(sys.argv) > 2 else "测试消息"
        chat_id = sys.argv[3] if len(sys.argv) > 3 else None
        result = sender.send_text(text, chat_id)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    elif cmd == "image":
        image_path = sys.argv[2] if len(sys.argv) > 2 else "screenshots/wechat_qr.png"
        chat_id = sys.argv[3] if len(sys.argv) > 3 else None
        result = sender.send_image(image_path, chat_id)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    elif cmd == "file":
        file_path = sys.argv[2]
        file_name = sys.argv[3] if len(sys.argv) > 3 else None
        chat_id = sys.argv[4] if len(sys.argv) > 4 else None
        result = sender.send_file(file_path, file_name, chat_id)
        print(json.dumps(result, indent=2, ensure_ascii=False))
    
    else:
        print(f"Unknown command: {cmd}")
        print("Available commands: text, image, file")
        sys.exit(1)
