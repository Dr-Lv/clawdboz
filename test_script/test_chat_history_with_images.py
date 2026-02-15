#!/usr/bin/env python3
"""测试获取群聊记录（包含图片下载）"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from src.config import CONFIG, get_absolute_path
from src.bot import LarkBot

def test_chat_history():
    """测试获取群聊历史记录（含图片/文件下载）"""
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
    
    print(f"\n测试获取群聊历史记录（最近10条，自动下载图片/文件）...")
    print(f"Chat ID: {test_chat_id}")
    print("-" * 80)
    
    # 调用获取历史记录的方法
    history = bot._get_chat_history(test_chat_id, limit=10)
    
    print("\n✓ 获取到的聊天记录（新格式）:")
    print("=" * 80)
    
    for i, msg in enumerate(history, 1):
        if isinstance(msg, dict):
            msg_type = msg.get('type', 'text')
            sender = msg.get('sender', 'unknown')
            content = msg.get('content', '')
            
            if msg_type == 'image':
                print(f"{i}. [{sender}] [图片] 📷")
                print(f"   路径: {content}")
                # 检查文件是否存在
                if os.path.exists(content):
                    size = os.path.getsize(content)
                    print(f"   状态: ✅ 已下载 ({size/1024:.1f} KB)")
                else:
                    print(f"   状态: ❌ 文件不存在")
            elif msg_type == 'file':
                file_name = msg.get('file_name', 'unknown')
                print(f"{i}. [{sender}] [文件] 📎 {file_name}")
                print(f"   路径: {content}")
                if os.path.exists(content):
                    size = os.path.getsize(content)
                    print(f"   状态: ✅ 已下载 ({size/1024:.1f} KB)")
                else:
                    print(f"   状态: ❌ 文件不存在")
            else:
                print(f"{i}. [{sender}] {content[:100]}..." if len(content) > 100 else f"{i}. [{sender}] {content}")
        else:
            # 兼容旧格式
            print(f"{i}. {msg[:100]}..." if len(msg) > 100 else f"{i}. {msg}")
        print()
    
    print("=" * 80)
    
    # 测试构建 prompt
    print("\n测试构建 ACP Prompt:")
    print("-" * 80)
    
    context_parts = ["以下是最近聊天记录上下文：\n"]
    for msg in history:
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
    
    final_prompt = context_prompt + "用户当前消息：测试消息\n\n请基于上下文回复用户的消息。"
    
    print(final_prompt[:2000])
    if len(final_prompt) > 2000:
        print(f"\n... (省略 {len(final_prompt) - 2000} 字符)")
    
    print("-" * 80)
    print(f"\n✅ 测试完成！共 {len(history)} 条记录，其中:")
    
    image_count = sum(1 for msg in history if isinstance(msg, dict) and msg.get('type') == 'image')
    file_count = sum(1 for msg in history if isinstance(msg, dict) and msg.get('type') == 'file')
    text_count = len(history) - image_count - file_count
    
    print(f"   - 文本消息: {text_count}")
    print(f"   - 图片消息: {image_count}")
    print(f"   - 文件消息: {file_count}")
    
    # 列出下载的文件
    print(f"\n下载的文件:")
    img_dir = get_absolute_path('WORKPLACE/user_images')
    file_dir = get_absolute_path('WORKPLACE/user_files')
    
    if os.path.exists(img_dir):
        img_files = [f for f in os.listdir(img_dir) if f.startswith('chat_')]
        print(f"   图片: {len(img_files)} 个")
        for f in img_files[:5]:
            size = os.path.getsize(os.path.join(img_dir, f))
            print(f"      - {f} ({size/1024:.1f} KB)")
    
    if os.path.exists(file_dir):
        file_files = [f for f in os.listdir(file_dir) if f.startswith('chat_')]
        print(f"   文件: {len(file_files)} 个")
        for f in file_files[:5]:
            size = os.path.getsize(os.path.join(file_dir, f))
            print(f"      - {f} ({size/1024:.1f} KB)")

if __name__ == "__main__":
    test_chat_history()
