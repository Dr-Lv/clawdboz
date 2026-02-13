#!/usr/bin/env python3
"""测试群聊历史记录获取功能"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from src.config import CONFIG, get_absolute_path
from src.bot import LarkBot

def test_chat_history():
    """测试获取群聊历史记录"""
    app_id = CONFIG.get('feishu', {}).get('app_id')
    app_secret = CONFIG.get('feishu', {}).get('app_secret')
    
    if not app_id or not app_secret:
        print("❌ 错误: 未配置飞书 app_id 或 app_secret")
        return
    
    print(f"✓ 飞书配置: app_id={app_id[:8]}...")
    
    # 创建 Bot 实例
    print("\n正在初始化 Bot...")
    bot = LarkBot(app_id, app_secret)
    print("✓ Bot 初始化成功")
    
    # 测试用的群聊 ID (从日志中获取的)
    test_chat_id = "oc_61431bd420df419e4282bce9e84bfeb2"
    
    print(f"\n测试获取群聊历史记录（最近7天，最近5条）...")
    print(f"Chat ID: {test_chat_id}")
    
    # 调用获取历史记录的方法（limit=5）
    history = bot._get_chat_history(test_chat_id, limit=5)
    
    # 也测试直接获取原始消息
    print(f"\n--- 测试直接获取原始消息（不过滤时间）---")
    from lark_oapi.api.im.v1 import ListMessageRequest
    request = ListMessageRequest.builder() \
        .container_id_type("chat") \
        .container_id(test_chat_id) \
        .page_size(50) \
        .build()
    response = bot.client.im.v1.message.list(request)
    if response.success() and response.data and response.data.items:
        items = response.data.items
        print(f"API 返回 {len(items)} 条原始消息")
        print("\n最近10条消息:")
        print("-" * 60)
        for i, item in enumerate(items[:10], 1):
            try:
                import json
                content = json.loads(item.body.content) if item.body else {}
                text = content.get('text', '')[:50]
                create_time = int(getattr(item, 'create_time', 0) or 0)
                from datetime import datetime
                dt = datetime.fromtimestamp(create_time / 1000)
                print(f"{i}. [{dt}] {text}...")
            except:
                print(f"{i}. [无法解析]")
    
    print(f"\n✓ 获取到 {len(history)} 条聊天记录:")
    print("-" * 60)
    for i, msg in enumerate(history[-5:], 1):  # 只显示最后5条
        print(f"{i}. {msg[:80]}..." if len(msg) > 80 else f"{i}. {msg}")
    
    if len(history) > 5:
        print(f"... 还有 {len(history) - 5} 条消息")
    
    print("-" * 60)
    
    if history:
        print("\n✅ 测试成功！群聊记录获取正常")
    else:
        print("\n⚠️  获取到 0 条记录，请检查 Bot 是否在群聊中以及是否有发送权限")

if __name__ == "__main__":
    test_chat_history()
