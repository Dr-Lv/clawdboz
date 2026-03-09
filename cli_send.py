#!/usr/bin/env python3
"""
CLI 发送消息工具 - 单次发送
用法: python cli_send.py "消息内容"
"""

import json
import requests
import sys
import os

CONFIG_PATH = 'config.json'

def load_config():
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

def get_tenant_token(app_id, app_secret):
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    resp = requests.post(url, json={
        "app_id": app_id,
        "app_secret": app_secret
    }, timeout=30)
    data = resp.json()
    if data.get("code") == 0:
        return data.get("tenant_access_token")
    return None

def send_message(token, chat_id, text):
    url = "https://open.feishu.cn/open-apis/im/v1/messages"
    headers = {
        "Authorization": f"Bearer {token}",
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
    return resp.json()

def main():
    if len(sys.argv) < 2:
        print("用法: python cli_send.py '消息内容'")
        sys.exit(1)
    
    message = sys.argv[1]
    
    config = load_config()
    app_id = config['feishu']['app_id']
    app_secret = config['feishu']['app_secret']
    
    # 获取 chat_id
    context_file = 'WORKPLACE/mcp_context.json'
    chat_id = None
    if os.path.exists(context_file):
        with open(context_file, 'r') as f:
            context = json.load(f)
            chat_id = context.get('chat_id')
    
    if not chat_id:
        print("❌ 未找到 chat_id")
        sys.exit(1)
    
    token = get_tenant_token(app_id, app_secret)
    if not token:
        print("❌ 获取 token 失败")
        sys.exit(1)
    
    result = send_message(token, chat_id, message)
    
    if result.get("code") == 0:
        print(f"✅ 已发送: {message}")
    else:
        print(f"❌ 失败: {result.get('msg')}")

if __name__ == "__main__":
    main()
