#!/usr/bin/env python3
"""测试发送给 ACP 的 prompt 格式（模拟群聊场景）"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from src.config import CONFIG, get_absolute_path
from src.bot import LarkBot

def test_prompt_format():
    """测试 prompt 格式"""
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
    
    print(f"\n测试获取群聊历史记录（最近5条，自动下载图片/文件）...")
    print(f"Chat ID: {test_chat_id}")
    print("=" * 80)
    
    # 获取聊天记录
    chat_history = bot._get_chat_history(test_chat_id, limit=5)
    
    print(f"\n✓ 获取到 {len(chat_history)} 条记录")
    
    # 构建 context prompt（和实际代码一致）
    context_prompt = ""
    if chat_history:
        context_parts = ["以下是最近聊天记录上下文：\n"]
        for msg in chat_history:
            if isinstance(msg, dict):
                sender = msg.get('sender', 'unknown')
                msg_type = msg.get('type', 'text')
                content = msg.get('content', '')
                
                if msg_type == 'image':
                    context_parts.append(f"{sender}: [图片] {content}")
                elif msg_type == 'file':
                    file_name = msg.get('file_name', 'unknown')
                    context_parts.append(f"{sender}: [文件: {file_name}] {content}")
                else:
                    context_parts.append(f"{sender}: {content}")
            else:
                context_parts.append(msg)
        
        context_prompt = "\n".join(context_parts) + "\n\n"
    
    # 模拟用户消息
    user_message = "分析一下上面的文件"
    
    # 构建最终 prompt
    final_prompt = context_prompt + f"用户当前消息：{user_message}\n\n请基于上下文回复用户的消息。"
    
    print("\n" + "=" * 80)
    print("发送给 ACP 的完整 Prompt:")
    print("=" * 80)
    print(final_prompt)
    print("=" * 80)
    print(f"\nPrompt 总长度: {len(final_prompt)} 字符")
    
    # 统计信息
    image_count = sum(1 for msg in chat_history if isinstance(msg, dict) and msg.get('type') == 'image')
    file_count = sum(1 for msg in chat_history if isinstance(msg, dict) and msg.get('type') == 'file')
    text_count = len(chat_history) - image_count - file_count
    
    print(f"\n消息统计:")
    print(f"  - 文本: {text_count}")
    print(f"  - 图片: {image_count}")
    print(f"  - 文件: {file_count}")
    
    # 检查下载的文件是否存在
    print(f"\n下载的文件检查:")
    for msg in chat_history:
        if isinstance(msg, dict) and msg.get('type') in ('image', 'file'):
            path = msg.get('content', '')
            exists = os.path.exists(path)
            size = os.path.getsize(path) if exists else 0
            status = "✅" if exists else "❌"
            print(f"  {status} {path}")
            if exists:
                print(f"     大小: {size/1024:.1f} KB")

if __name__ == "__main__":
    test_prompt_format()
