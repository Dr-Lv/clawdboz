#!/usr/bin/env python3
"""
诊断脚本：测试 Bot 连接和事件订阅状态
"""

import json
import requests
import sys

# 从 config.json 读取配置
CONFIG_PATH = 'config.json'

with open(CONFIG_PATH, 'r') as f:
    config = json.load(f)

APP_ID = config['feishu']['app_id']
APP_SECRET = config['feishu']['app_secret']

print("=" * 60)
print("🤖 Bot 连接诊断工具")
print("=" * 60)
print(f"App ID: {APP_ID}")
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
    return None


def get_bot_info(token):
    """获取机器人信息"""
    url = "https://open.feishu.cn/open-apis/bot/v3/info"
    headers = {"Authorization": f"Bearer {token}"}
    resp = requests.get(url, headers=headers, timeout=30)
    return resp.json()


def main():
    print("=" * 60)
    print("步骤 1: 验证身份")
    print("=" * 60)
    
    token = get_tenant_access_token()
    if not token:
        print("❌ 获取 Access Token 失败")
        print("   请检查 App ID 和 App Secret 是否正确")
        sys.exit(1)
    
    print("✅ Access Token 获取成功")
    print()
    
    print("=" * 60)
    print("步骤 2: 获取机器人信息")
    print("=" * 60)
    
    bot_info = get_bot_info(token)
    if bot_info.get("code") == 0:
        bot_data = bot_info.get("bot", {})
        activate_status = bot_data.get('activate_status', 1)
        is_banned = bot_data.get('is_banned', True)
        
        print(f"✅ 机器人信息获取成功")
        print(f"   名称: {bot_data.get('bot_name', 'N/A')}")
        print(f"   状态码: {activate_status} ({'✅ 正常' if activate_status == 0 else '❌ 禁用'})")
        print(f"   是否被禁: {'❌ 是' if is_banned else '✅ 否'}")
        print(f"   Open ID: {bot_data.get('open_id', 'N/A')[:30]}...")
        
        if activate_status != 0 or is_banned:
            print()
            print("⚠️ ⚠️ ⚠️ 警告：机器人当前处于禁用状态！")
            print()
    else:
        print(f"⚠️ 获取机器人信息失败: {bot_info.get('msg')}")
    print()
    
    print("=" * 60)
    print("📋 诊断总结与解决方案")
    print("=" * 60)
    print("""
如果机器人没有回复消息，请按以下步骤检查：

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
🔴 关键问题：机器人可能被禁用
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

【原因】
飞书开放平台对机器人有以下限制：
1. 企业自建应用需要管理员审核才能使用
2. 应用发布后可能需要重新激活
3. 部分权限变更后需要重新授权

【解决方案】

1️⃣ 检查应用状态
   飞书开放平台 → 应用详情 → 版本管理与发布
   - 确保应用状态为「已发布」
   - 如果有新版本，需要重新发布

2️⃣ 检查机器人启用状态
   飞书开放平台 → 机器人 → 设置
   - 确保「启用机器人」开关已打开
   - 检查是否有禁用提示

3️⃣ 重新激活应用（关键！）
   由于这是新创建的机器人 (cli_a9170c8067781bce)，
   需要在飞书开放平台：
   
   a) 进入应用管理后台
   b) 点击「版本管理与发布」
   c) 创建新版本并发布
   d) 或者点击「申请发布」重新提交审核

4️⃣ 检查事件订阅配置
   飞书开放平台 → 事件订阅
   - 订阅方式：选择「WebSocket (长连接)」
   - 订阅事件：添加「im.message.receive_v1」

5️⃣ 检查权限配置
   飞书开放平台 → 权限管理
   需要申请以下权限：
   ✅ im:chat:readonly (读取群聊信息)
   ✅ im:message:send (发送消息)
   ✅ im:message.group_msg (接收群消息)
   ✅ im:message.p2p_msg (接收单聊消息)

6️⃣ 企业管理员授权
   如果是企业自建应用：
   - 需要企业管理员在「应用管理」中启用该应用
   - 或者访问应用安装链接进行授权

━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━
💡 快速排查步骤
━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━━

1. 在飞书客户端中搜索机器人名称
   - 如果能搜到但无法发送消息 → 权限问题
   - 如果搜不到 → 应用未发布或被禁用

2. 检查应用可见范围
   飞书开放平台 → 应用详情 → 可用范围
   - 确保包含你要测试的用户

3. 查看飞书开放平台「监控与报警」
   - 检查是否有事件推送失败的记录
""")


if __name__ == "__main__":
    main()
