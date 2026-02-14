#!/usr/bin/env python3
"""飞书 Bot 连接诊断工具"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import CONFIG
import lark_oapi as lark
from lark_oapi.api.im.v1 import ListMessageRequest, GetChatRequest
from lark_oapi.api.auth.v3 import InternalTenantAccessTokenRequest, InternalTenantAccessTokenRequestBody
import json

def diagnose():
    print("=" * 60)
    print("飞书 Bot 连接诊断")
    print("=" * 60)
    
    app_id = CONFIG.get('feishu', {}).get('app_id')
    app_secret = CONFIG.get('feishu', {}).get('app_secret')
    
    print(f"\n1. 应用配置")
    print(f"   App ID: {app_id[:20]}..." if app_id else "   ❌ App ID 未设置")
    print(f"   App Secret: {'已设置' if app_secret else '❌ 未设置'}")
    
    client = lark.Client.builder() \
        .app_id(app_id) \
        .app_secret(app_secret) \
        .build()
    
    print(f"\n2. API 连接测试")
    try:
        request = ListMessageRequest.builder() \
            .container_id_type("chat") \
            .container_id("oc_61431bd420df419e4282bce9e84bfeb2") \
            .page_size(1) \
            .build()
        response = client.im.v1.message.list(request)
        
        if response.success():
            print("   ✅ API 连接正常")
        else:
            print(f"   ❌ API 错误: {response.code} - {response.msg}")
    except Exception as e:
        print(f"   ❌ 异常: {e}")
    
    print(f"\n3. 群聊信息")
    try:
        request = GetChatRequest.builder() \
            .chat_id("oc_61431bd420df419e4282bce9e84bfeb2") \
            .build()
        response = client.im.v1.chat.get(request)
        
        if response.success():
            chat = response.data
            print(f"   ✅ 群聊存在")
            print(f"   群名: {chat.name if hasattr(chat, 'name') else 'N/A'}")
        else:
            print(f"   ❌ 获取群聊失败: {response.code}")
    except Exception as e:
        print(f"   ❌ 异常: {e}")
    
    print(f"\n4. 可能的连接问题")
    print("   如果 WebSocket 已连接但收不到消息，请检查:")
    print("   1. 飞书开放平台 → 事件与回调 → 事件配置方式")
    print("      必须选择: '使用长连接接收事件'")
    print("   2. 飞书开放平台 → 事件与回调 → 事件订阅")
    print("      必须添加: im.message.receive_v1")
    print("   3. 飞书开放平台 → 版本管理与发布")
    print("      必须发布应用（至少测试版本）")
    print("   4. 飞书开放平台 → 权限管理")
    print("      权限必须审核通过")
    print("   5. 群聊中必须添加 Bot 为成员")
    
    print("\n" + "=" * 60)

if __name__ == "__main__":
    diagnose()
