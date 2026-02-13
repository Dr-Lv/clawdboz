#!/usr/bin/env python3
"""测试群聊判断逻辑"""
import json

def test_group_logic():
    """测试群聊和 @ 检测逻辑"""
    
    # 模拟不同的消息场景
    test_cases = [
        {
            "name": "群聊文本消息（无@）",
            "chat_type": "group",
            "chat_id": "oc_d24a689f16656bb78b5a6b75c5a2b552",
            "msg_content": '{"text": "大家好"}',
            "expected_reply": False
        },
        {
            "name": "群聊文本消息（有@）",
            "chat_type": "group",
            "chat_id": "oc_d24a689f16656bb78b5a6b75c5a2b552",
            "msg_content": '{"text": "<at id=\\"ou_xxx\\"></at> 你好"}',
            "expected_reply": True
        },
        {
            "name": "单聊消息",
            "chat_type": "p2p",
            "chat_id": "oc_d24a689f16656bb78b5a6b75c5a2b552",
            "msg_content": '{"text": "你好"}',
            "expected_reply": True
        },
        {
            "name": "群聊（chat_type=None，chat_id是oc_开头）",
            "chat_type": None,
            "chat_id": "oc_d24a689f16656bb78b5a6b75c5a2b552",
            "msg_content": '{"text": "测试"}',
            "expected_reply": False
        },
        {
            "name": "群聊（chat_type=unknown，chat_id是oc_开头）",
            "chat_type": "unknown",
            "chat_id": "oc_d24a689f16656bb78b5a6b75c5a2b552",
            "msg_content": '{"text": "测试"}',
            "expected_reply": False
        }
    ]
    
    print("=" * 80)
    print("测试群聊判断逻辑")
    print("=" * 80)
    
    for case in test_cases:
        chat_type = case["chat_type"]
        chat_id = case["chat_id"]
        msg_content = case["msg_content"]
        
        # 模拟代码逻辑
        chat_id_looks_like_group = chat_id.startswith('oc_') if chat_id else False
        
        if chat_type is None:
            if chat_id_looks_like_group:
                chat_type = 'group'
            else:
                chat_type = 'p2p'
        
        if chat_type not in ['group', 'p2p'] and chat_id_looks_like_group:
            chat_type = 'group'
        
        is_group = chat_type == 'group'
        
        # 检查 @
        is_mentioned = False
        try:
            content_dict = json.loads(msg_content)
            current_text = content_dict.get('text', '')
            if '<at' in current_text and '</at>' in current_text:
                is_mentioned = True
        except:
            pass
        
        # 判断是否应该回复
        should_reply = not (is_group and not is_mentioned)
        
        # 检查结果
        status = "✅ 通过" if should_reply == case["expected_reply"] else "❌ 失败"
        
        print(f"\n{status} {case['name']}")
        print(f"   chat_type={chat_type}, is_group={is_group}, is_mentioned={is_mentioned}")
        print(f"   应该回复: {case['expected_reply']}, 实际: {should_reply}")
    
    print("\n" + "=" * 80)

if __name__ == "__main__":
    test_group_logic()
