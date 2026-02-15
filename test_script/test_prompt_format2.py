#!/usr/bin/env python3
"""测试发送给 ACP 的 prompt 格式 - 包含文件消息"""

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
    
    print(f"\n测试获取群聊历史记录（最近30条，自动下载图片/文件）...")
    print(f"Chat ID: {test_chat_id}")
    print("=" * 80)
    
    # 获取更多记录
    chat_history = bot._get_chat_history(test_chat_id, limit=30)
    
    print(f"\n✓ 获取到 {len(chat_history)} 条记录")
    print("\n记录详情:")
    print("-" * 80)
    
    for i, msg in enumerate(chat_history, 1):
        if isinstance(msg, dict):
            sender = msg.get('sender', 'unknown')[:20]
            msg_type = msg.get('type', 'text')
            content = msg.get('content', '')
            
            if msg_type == 'image':
                print(f"{i}. [{sender}] [图片] 📷")
                print(f"   路径: {content}")
            elif msg_type == 'file':
                file_name = msg.get('file_name', 'unknown')
                print(f"{i}. [{sender}] [文件] 📎 {file_name}")
                print(f"   路径: {content}")
            else:
                content_display = content[:60] + "..." if len(content) > 60 else content
                print(f"{i}. [{sender}] {content_display}")
        else:
            print(f"{i}. [旧格式] {str(msg)[:80]}")
    
    # 构建 context prompt
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
    user_message = "帮我分析一下 Excel 文件的内容"
    
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

if __name__ == "__main__":
    test_prompt_format()
