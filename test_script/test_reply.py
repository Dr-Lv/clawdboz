#!/usr/bin/env python3
"""直接测试飞书bot的回复功能"""
import sys
sys.path.insert(0, '/project/larkbot')

from clawdboz import LarkBot
import time

# 使用 bot 的 credentials
appid = 'cli_a907c9018f7a9cc5'
app_secret = '5VDY7pUnBmQpT1MOiVjQEgRYXjhjdCA7'

# 创建 bot 实例
bot = LarkBot(appid, app_secret)

# 测试用的 chat_id (从之前的消息中获取)
# 用户需要自己提供正确的 chat_id
CHAT_ID = "oc_d24a689f16656bb78b5a6b75c5a2b552"  # 请替换为实际的 chat_id

def test_simple_reply():
    """测试简单回复"""
    print("测试发送简单文本消息...")
    message_id = bot.reply_text(CHAT_ID, "这是一条测试消息，时间：" + time.strftime('%H:%M:%S'), streaming=False)
    print(f"发送结果: {message_id}")
    return message_id

def test_acp_reply():
    """测试 ACP 回复"""
    print("测试 ACP 回复...")
    bot.run_msg_script_streaming(CHAT_ID, "ls")

if __name__ == "__main__":
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument('--chat-id', default=CHAT_ID, help='飞书 chat_id')
    parser.add_argument('--test', choices=['simple', 'acp'], default='simple', help='测试类型')
    args = parser.parse_args()
    
    CHAT_ID = args.chat_id
    
    if args.test == 'simple':
        test_simple_reply()
    else:
        test_acp_reply()
