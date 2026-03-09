#!/usr/bin/env python3
"""
测试新机器人消息收发功能
使用 bot2.py 中的凭证：cli_a9170c8067781bce
"""

import json
import requests
import sys
import os

# 从 config.json 读取配置
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), 'config.json')

with open(CONFIG_PATH, 'r') as f:
    config = json.load(f)

APP_ID = config['feishu']['app_id']
APP_SECRET = config['feishu']['app_secret']

print(f"🤖 测试机器人")
print(f"   App ID: {APP_ID}")
print(f"   App Secret: {'*' * len(APP_SECRET)}")
print()


def get_tenant_access_token():
    """获取 tenant_access_token"""
    url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
    resp = requests.post(url, json={
        "app_id": APP_ID,
        "app_secret": APP_SECRET
    }, timeout=30)
    data = resp.json()
    if data.get("code") == 0:
        return data.get("tenant_access_token")
    else:
        print(f"❌ 获取 token 失败: {data}")
        return None


def get_bot_info(token):
    """获取机器人信息"""
    url = "https://open.feishu.cn/open-apis/bot/v3/info"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, timeout=30)
    return resp.json()


def send_test_message(token, chat_id, chat_type="group"):
    """发送测试消息"""
    url = "https://open.feishu.cn/open-apis/im/v1/messages"
    headers = {
        "Authorization": f"Bearer {token}",
        "Content-Type": "application/json"
    }
    params = {"receive_id_type": "chat_id"}
    
    content = json.dumps({
        "text": f"🎉 新机器人测试消息\n\n"
                f"✅ 身份验证成功\n"
                f"✅ 消息发送功能正常\n\n"
                f"App ID: {APP_ID}\n"
                f"时间: {__import__('datetime').datetime.now().strftime('%Y-%m-%d %H:%M:%S')}"
    })
    
    body = {
        "receive_id": chat_id,
        "msg_type": "text",
        "content": content
    }
    
    resp = requests.post(url, headers=headers, params=params, json=body, timeout=30)
    return resp.json()


def main():
    print("=" * 50)
    print("步骤 1: 获取 Access Token")
    print("=" * 50)
    
    token = get_tenant_access_token()
    if not token:
        print("❌ 测试失败：无法获取 access token")
        sys.exit(1)
    
    print("✅ Access Token 获取成功")
    print(f"   Token: {token[:20]}...")
    print()
    
    print("=" * 50)
    print("步骤 2: 获取机器人信息")
    print("=" * 50)
    
    bot_info = get_bot_info(token)
    if bot_info.get("code") == 0:
        bot_data = bot_info.get("bot", {})
        print(f"✅ 机器人信息获取成功")
        print(f"   名称: {bot_data.get('bot_name')}")
        print(f"   状态: {'激活' if bot_data.get('is_banned') == False else '禁用'}")
    else:
        print(f"⚠️ 获取机器人信息失败: {bot_info.get('msg')}")
    print()
    
    # 从上下文文件获取 chat_id
    context_file = os.path.join(os.path.dirname(__file__), 'WORKPLACE', 'mcp_context.json')
    chat_id = None
    chat_type = "group"
    
    if os.path.exists(context_file):
        with open(context_file, 'r') as f:
            context = json.load(f)
            chat_id = context.get('chat_id')
            chat_type = context.get('chat_type', 'group')
    
    if chat_id:
        print("=" * 50)
        print("步骤 3: 发送测试消息")
        print("=" * 50)
        print(f"   Chat ID: {chat_id}")
        print(f"   Chat Type: {chat_type}")
        print()
        
        result = send_test_message(token, chat_id, chat_type)
        if result.get("code") == 0:
            print("✅ 测试消息发送成功！")
            print(f"   消息 ID: {result.get('data', {}).get('message_id')}")
        else:
            print(f"❌ 消息发送失败: {result.get('msg')}")
            print(f"   错误码: {result.get('code')}")
            if result.get("code") == 230002:
                print("\n💡 提示: Bot 不在该聊天中，请先将 Bot 添加到群聊或在单聊中发送消息给 Bot")
    else:
        print("=" * 50)
        print("步骤 3: 跳过消息发送测试")
        print("=" * 50)
        print("⚠️ 未找到 chat_id，跳过消息发送测试")
        print(f"   请确保 {context_file} 存在且包含 chat_id")
    
    print()
    print("=" * 50)
    print("测试完成")
    print("=" * 50)


if __name__ == "__main__":
    main()
