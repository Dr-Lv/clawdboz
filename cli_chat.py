#!/usr/bin/env python3
"""
CLI 聊天工具 - 通过飞书 API 与 Bot 对话
"""

import json
import requests
import sys
import os

# 从 config.json 读取配置
CONFIG_PATH = 'config.json'

def load_config():
    with open(CONFIG_PATH, 'r') as f:
        return json.load(f)

def get_tenant_token(app_id, app_secret):
    """获取 tenant_access_token"""
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
    """发送消息到指定聊天"""
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
    # 读取配置
    config = load_config()
    app_id = config['feishu']['app_id']
    app_secret = config['feishu']['app_secret']
    
    # 从上下文文件获取 chat_id
    context_file = 'WORKPLACE/mcp_context.json'
    chat_id = None
    if os.path.exists(context_file):
        with open(context_file, 'r') as f:
            context = json.load(f)
            chat_id = context.get('chat_id')
    
    if not chat_id:
        print("❌ 未找到 chat_id，请先通过飞书与 Bot 建立会话")
        print(f"   上下文文件: {context_file}")
        sys.exit(1)
    
    print(f"🤖 连接到 Bot (App ID: {app_id[:10]}...)")
    print(f"💬 Chat ID: {chat_id}")
    print("=" * 50)
    print("输入消息并按回车发送，输入 'quit' 或 'exit' 退出")
    print("=" * 50)
    
    # 获取 token
    token = get_tenant_token(app_id, app_secret)
    if not token:
        print("❌ 获取 access token 失败")
        sys.exit(1)
    
    # 交互式输入
    while True:
        try:
            user_input = input("\n👤 You: ").strip()
            
            if not user_input:
                continue
            
            if user_input.lower() in ('quit', 'exit', 'q'):
                print("👋 再见！")
                break
            
            # 发送消息
            result = send_message(token, chat_id, user_input)
            
            if result.get("code") == 0:
                print("✅ 消息已发送")
            else:
                print(f"❌ 发送失败: {result.get('msg')}")
                
        except KeyboardInterrupt:
            print("\n👋 再见！")
            break
        except Exception as e:
            print(f"❌ 错误: {e}")

if __name__ == "__main__":
    main()
