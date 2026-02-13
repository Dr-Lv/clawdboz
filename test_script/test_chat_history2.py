#!/usr/bin/env python3
"""测试群聊历史记录获取功能 - 显示所有 text 消息"""
import sys
sys.path.insert(0, '/project/larkbot')

import lark_oapi as lark
from lark_oapi.api.im.v1 import ListMessageRequest
import json

APP_ID = 'cli_a907c9018f7a9cc5'
APP_SECRET = '5VDY7pUnBmQpT1MOiVjQEgRYXjhjdCA7'
CHAT_ID = 'oc_61431bd420df419e4282bce9e84bfeb2'

def test():
    client = lark.Client.builder().app_id(APP_ID).app_secret(APP_SECRET).log_level(lark.LogLevel.INFO).build()
    
    request = ListMessageRequest.builder().container_id_type("chat").container_id(CHAT_ID).page_size(50).build()
    response = client.im.v1.message.list(request)
    
    if response.success():
        items = response.data.items if response.data else []
        print(f"API 返回 {len(items)} 条消息\n")
        
        # 收集所有 text 类型的消息
        text_messages = []
        for i, item in enumerate(items):
            try:
                if item.msg_type != 'text':
                    continue
                if not item.body:
                    continue
                    
                sender_id = getattr(item.sender, 'id', 'unknown') if item.sender else 'unknown'
                content = json.loads(item.body.content)
                text = content.get('text', '')
                
                if text:
                    text_messages.append({
                        'index': i,
                        'sender': str(sender_id)[:20],
                        'text': text,
                        'time': item.create_time
                    })
            except:
                continue
        
        print(f"找到 {len(text_messages)} 条 text 类型消息（按时间倒序，最新在前）：\n")
        print("=" * 70)
        
        for msg in text_messages[:20]:  # 显示前 20 条
            print(f"[{msg['index']:2d}] {msg['sender']}: {msg['text'][:60]}")
        
        print("=" * 70)
        print(f"\n取最新 10 条 text 消息（按时间顺序，最早在前）：\n")
        print("=" * 70)
        
        for msg in reversed(text_messages[:10]):
            print(f"  {msg['sender']}: {msg['text'][:60]}")
        
        print("=" * 70)

if __name__ == "__main__":
    test()
