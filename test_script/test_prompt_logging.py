#!/usr/bin/env python3
"""测试发送给 ACP 的 prompt 日志输出"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from src.config import CONFIG, get_absolute_path
from src.bot import LarkBot

def test_prompt_logging():
    """测试 prompt 日志输出"""
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
    
    # 模拟群聊场景
    chat_id = "oc_b11866b977f271aa524f6558dd6cfedb"
    chat_type = "group"
    is_group = True
    
    # 获取聊天记录
    print(f"\n获取群聊记录...")
    chat_history = bot._get_chat_history(chat_id, limit=10)
    
    # 模拟用户消息
    text = "帮我分析一下 Excel 文件"
    
    # 构建上下文提示
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
    
    # 构建最终提示词
    final_prompt = context_prompt + f"用户当前消息：{text}\n\n请基于上下文回复用户的消息。"
    
    # 模拟日志输出（和实际代码一致）
    print("\n" + "=" * 80)
    print("模拟日志输出（和实际代码一致）:")
    print("=" * 80)
    
    bot._log(f"[DEBUG] ===== 发送给 ACP 的 Prompt =====")
    bot._log(f"[DEBUG] Chat ID: {chat_id}, Chat Type: {chat_type}")
    bot._log(f"[DEBUG] Prompt 长度: {len(final_prompt)} 字符")
    bot._log(f"[DEBUG] 完整 Prompt:\n{final_prompt}")
    bot._log(f"[DEBUG] ===== Prompt 结束 =====")
    
    print("\n✅ 日志输出完成！")
    print(f"\n实际日志文件位置: {bot.log_file}")
    
    # 显示日志文件内容
    print("\n日志文件内容（最后 100 行）:")
    print("-" * 80)
    os.system(f"tail -50 {bot.log_file}")

if __name__ == "__main__":
    test_prompt_logging()
