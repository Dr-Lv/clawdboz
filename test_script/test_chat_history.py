#!/usr/bin/env python3
"""测试群聊历史记录获取功能"""
import sys
sys.path.insert(0, '/project/larkbot')

import lark_oapi as lark
from lark_oapi.api.im.v1 import ListMessageRequest
import json

# Bot 配置
APP_ID = 'cli_a907c9018f7a9cc5'
APP_SECRET = '5VDY7pUnBmQpT1MOiVjQEgRYXjhjdCA7'
# 测试群聊 ID
CHAT_ID = 'oc_61431bd420df419e4282bce9e84bfeb2'

def test_get_chat_history():
    """测试获取群聊历史记录"""
    
    # 创建客户端
    client = lark.Client.builder() \
        .app_id(APP_ID) \
        .app_secret(APP_SECRET) \
        .log_level(lark.LogLevel.INFO) \
        .build()
    
    print(f"=== 测试获取群聊历史记录 ===")
    print(f"群聊 ID: {CHAT_ID}")
    print()
    
    try:
        # 构建请求
        request = ListMessageRequest.builder() \
            .container_id_type("chat") \
            .container_id(CHAT_ID) \
            .page_size(50) \
            .build()
        
        print("发送 API 请求...")
        response = client.im.v1.message.list(request)
        
        if response.success():
            items = response.data.items if response.data else []
            print(f"✅ API 调用成功，返回 {len(items)} 条消息\n")
            
            print("=" * 60)
            print("原始消息列表（按 API 返回顺序，最新的在前）：")
            print("=" * 60)
            
            for i, item in enumerate(items):
                print(f"\n--- 消息 {i+1} ---")
                print(f"  message_id: {getattr(item, 'message_id', 'N/A')}")
                print(f"  msg_type: {getattr(item, 'msg_type', 'N/A')}")
                print(f"  create_time: {getattr(item, 'create_time', 'N/A')}")
                print(f"  update_time: {getattr(item, 'update_time', 'N/A')}")
                
                # 获取 sender 信息
                sender_info = "unknown"
                if hasattr(item, 'sender') and item.sender:
                    sender = item.sender
                    print(f"  sender 类型: {type(sender)}")
                    print(f"  sender 属性: {dir(sender)}")
                    
                    # 尝试获取 sender_id
                    sender_id_obj = getattr(sender, 'sender_id', None) or getattr(sender, 'id', None)
                    if sender_id_obj:
                        print(f"  sender_id 类型: {type(sender_id_obj)}")
                        print(f"  sender_id 属性: {dir(sender_id_obj)}")
                        
                        # 尝试获取 user_id 或 open_id
                        user_id = getattr(sender_id_obj, 'user_id', None)
                        open_id = getattr(sender_id_obj, 'open_id', None)
                        sender_info = user_id or open_id or str(sender_id_obj)
                
                print(f"  sender: {sender_info}")
                
                # 获取消息内容
                if hasattr(item, 'body') and item.body:
                    body_content = getattr(item.body, 'content', None)
                    print(f"  body.content: {body_content}")
                    
                    # 尝试解析 JSON
                    try:
                        content_dict = json.loads(body_content) if body_content else {}
                        text = content_dict.get('text', '')
                        print(f"  解析后的 text: {text[:100] if text else '(empty)'}")
                    except Exception as e:
                        print(f"  解析 JSON 失败: {e}")
                else:
                    print(f"  body: None")
            
            print("\n" + "=" * 60)
            print("处理后的聊天记录（最新的 10 条，按时间顺序）：")
            print("=" * 60)
            
            history = []
            skipped = 0
            recent_items = items[:10]  # 最新的 10 条
            
            for item in reversed(recent_items):  # 反转回时间顺序
                try:
                    # 获取 sender
                    sender = "unknown"
                    if hasattr(item, 'sender') and item.sender:
                        sender_id_obj = getattr(item.sender, 'sender_id', None) or getattr(item.sender, 'id', None)
                        if sender_id_obj:
                            user_id = getattr(sender_id_obj, 'user_id', None)
                            open_id = getattr(sender_id_obj, 'open_id', None)
                            sender = user_id or open_id or str(sender_id_obj)[:20]
                    
                    # 获取内容
                    if not item.body:
                        skipped += 1
                        continue
                    
                    body_content = getattr(item.body, 'content', '{}')
                    content_dict = json.loads(body_content)
                    text = content_dict.get('text', '')
                    
                    if text:
                        history.append(f"{sender}: {text[:100]}")
                    else:
                        skipped += 1
                        
                except Exception as e:
                    skipped += 1
                    continue
            
            for msg in history:
                print(f"  {msg}")
            
            print(f"\n统计: 成功={len(history)}, 跳过={skipped}")
            
        else:
            print(f"❌ API 调用失败: {response.code} - {response.msg}")
            print(f"响应详情: {response}")
            
    except Exception as e:
        print(f"❌ 异常: {e}")
        import traceback
        traceback.print_exc()

if __name__ == "__main__":
    test_get_chat_history()
