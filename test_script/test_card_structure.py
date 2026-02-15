#!/usr/bin/env python3
"""测试卡片消息结构"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from src.config import CONFIG
from src.bot import LarkBot

def test_card():
    app_id = CONFIG.get('feishu', {}).get('app_id')
    app_secret = CONFIG.get('feishu', {}).get('app_secret')
    
    bot = LarkBot(app_id, app_secret)
    
    from lark_oapi.api.im.v1 import ListMessageRequest
    
    chat_id = "oc_b11866b977f271aa524f6558dd6cfedb"
    
    request = ListMessageRequest.builder() \
        .container_id_type("chat") \
        .container_id(chat_id) \
        .page_size(50) \
        .build()
    
    response = bot.client.im.v1.message.list(request)
    
    if response.success() and response.data:
        items = response.data.items[:10]  # 只看前10条
        
        for i, item in enumerate(items):
            msg_type = getattr(item, 'msg_type', 'unknown')
            sender = item.sender.id if item.sender and hasattr(item.sender, 'id') else "unknown"
            
            if msg_type == 'interactive':
                content = json.loads(item.body.content) if item.body else {}
                print(f"\n消息 {i}: type={msg_type}, sender={sender[:20]}")
                print(f"Content keys: {content.keys()}")
                
                if 'elements' in content:
                    print(f"Elements: {json.dumps(content['elements'], indent=2, ensure_ascii=False)[:500]}")
                elif 'config' in content:
                    print(f"Config: {content.get('config', {})}")
                    print(f"Body: {content.get('body', {})}")

if __name__ == "__main__":
    test_card()
