#!/usr/bin/env python3
"""测试飞书 Markdown 渲染"""
import json
import lark_oapi as lark
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

# 飞书应用凭证
app_id = 'cli_a907c9018f7a9cc5'
app_secret = '5VDY7pUnBmQpT1MOiVjQEgRYXjhjdCA7'

# 测试群聊 ID（从日志中获取）
chat_id = 'oc_d24a689f16656bb78b5a6b75c5a2b552'

# 创建客户端
client = lark.Client.builder() \
    .app_id(app_id) \
    .app_secret(app_secret) \
    .log_level(lark.LogLevel.INFO) \
    .build()

# 测试 Markdown 内容
test_content = """💭 **思考过程**
```
用户只是简单地输入了"ls"，想看看当前目录的内容。
```

🔧 **工具调用**
- ✅ Shell

**当前目录的文件列表：**
```
drwxr-xr-x   4 suntom  staff    128  2月 10 15:16 __pycache__
drwxr-xr-x  17 suntom  staff    544  2月 10 14:55 .
drwxr-xr-x  25 suntom  staff    800  2月  9 14:00 ..
```

**主要文件：**
- `clawdboz.py` - 主程序文件
- `bot_manager.sh` - 机器人管理脚本
- `README_OPS.md` - 运维说明文档
- `WORKPLACE/` - 工作目录（用于存放临时文件）

*斜体文本* 和 ~~删除线~~ 测试

[链接测试](https://open.feishu.cn)
"""

def send_old_card():
    """发送旧版消息卡片 (interactive)"""
    print("=" * 60)
    print("测试1: 旧版消息卡片 (interactive)")
    print("=" * 60)
    
    # 使用 lark_md
    card_content = {
        "config": {"wide_screen_mode": True},
        "elements": [
            {
                "tag": "div",
                "text": {
                    "tag": "lark_md",
                    "content": test_content
                }
            }
        ]
    }
    
    request = CreateMessageRequest.builder() \
        .receive_id_type("chat_id") \
        .request_body(CreateMessageRequestBody.builder()
            .receive_id(chat_id)
            .msg_type("interactive")
            .content(json.dumps(card_content))
            .build()) \
        .build()
    
    response = client.im.v1.message.create(request)
    
    if response.success():
        print(f"✅ 发送成功! message_id: {response.data.message_id}")
        return response.data.message_id
    else:
        print(f"❌ 发送失败: {response.code} - {response.msg}")
        return None

def send_new_card():
    """发送新版消息卡片 (V2)"""
    print("\n" + "=" * 60)
    print("测试2: 新版消息卡片 (V2)")
    print("=" * 60)
    
    card_content = {
        "schema": "2.0",
        "config": {"width_mode": "fill"},
        "body": {
            "elements": [
                {
                    "tag": "markdown",
                    "content": test_content
                }
            ]
        }
    }
    
    request = CreateMessageRequest.builder() \
        .receive_id_type("chat_id") \
        .request_body(CreateMessageRequestBody.builder()
            .receive_id(chat_id)
            .msg_type("interactive")
            .content(json.dumps(card_content))
            .build()) \
        .build()
    
    response = client.im.v1.message.create(request)
    
    if response.success():
        print(f"✅ 发送成功! message_id: {response.data.message_id}")
        return response.data.message_id
    else:
        print(f"❌ 发送失败: {response.code} - {response.msg}")
        return None

def send_post_message():
    """发送富文本消息 (post)"""
    print("\n" + "=" * 60)
    print("测试3: 富文本消息 (post)")
    print("=" * 60)
    
    # 构建 post 内容
    post_content = {
        "zh_cn": {
            "title": "Markdown 测试",
            "content": [
                [{"tag": "text", "text": "💭 ", "style": {}}, {"tag": "text", "text": "思考过程", "style": {"bold": True}}],
                [{"tag": "text", "text": "用户只是简单地输入了\"ls\"，想看看当前目录的内容。", "style": {"code": True}}],
                [{"tag": "text", "text": ""}],
                [{"tag": "text", "text": "🔧 ", "style": {}}, {"tag": "text", "text": "工具调用", "style": {"bold": True}}],
                [{"tag": "text", "text": "✅ Shell", "style": {}}],
                [{"tag": "text", "text": ""}],
                [{"tag": "text", "text": "当前目录的文件列表：", "style": {"bold": True}}],
                [{"tag": "text", "text": "drwxr-xr-x   4 suntom  staff    128  2月 10 15:16 __pycache__", "style": {"code": True}}],
            ]
        }
    }
    
    request = CreateMessageRequest.builder() \
        .receive_id_type("chat_id") \
        .request_body(CreateMessageRequestBody.builder()
            .receive_id(chat_id)
            .msg_type("post")
            .content(json.dumps(post_content))
            .build()) \
        .build()
    
    response = client.im.v1.message.create(request)
    
    if response.success():
        print(f"✅ 发送成功! message_id: {response.data.message_id}")
        return response.data.message_id
    else:
        print(f"❌ 发送失败: {response.code} - {response.msg}")
        return None

if __name__ == "__main__":
    import sys
    
    print("飞书 Markdown 渲染测试\n")
    
    # 默认发送所有测试
    test_type = sys.argv[1] if len(sys.argv) > 1 else "all"
    
    if test_type in ("all", "1"):
        send_old_card()
    
    if test_type in ("all", "2"):
        send_new_card()
    
    if test_type in ("all", "3"):
        send_post_message()
    
    print("\n" + "=" * 60)
    print("测试完成！请在飞书中查看消息效果。")
    print("=" * 60)
