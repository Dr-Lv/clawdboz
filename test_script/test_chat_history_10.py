#!/usr/bin/env python3
"""测试获取最近10条群聊记录"""

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
    
    # 从 mcp_context.json 获取的群聊 ID
    test_chat_id = "oc_b11866b977f271aa524f6558dd6cfedb"
    
    print(f"\n测试获取群聊历史记录（最近7天，最近10条）...")
    print(f"Chat ID: {test_chat_id}")
    
    # 调用获取历史记录的方法（limit=10）
    history = bot._get_chat_history(test_chat_id, limit=10)
    
    print(f"\n✓ 获取到 {len(history)} 条聊天记录:")
    print("-" * 80)
    for i, msg in enumerate(history, 1):
        print(f"{i}. {msg[:100]}..." if len(msg) > 100 else f"{i}. {msg}")
    
    print("-" * 80)
    
    if history:
        print(f"\n✅ 测试成功！成功获取 {len(history)} 条群聊记录")
    else:
        print("\n⚠️  获取到 0 条记录，请检查 Bot 是否在群聊中以及是否有发送权限")

if __name__ == "__main__":
    test_chat_history()
