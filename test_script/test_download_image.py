#!/usr/bin/env python3
"""测试图片下载功能 - 从群聊历史中查找图片消息并下载"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from src.config import CONFIG, get_absolute_path
from src.bot import LarkBot

def test_image_download():
    """测试图片下载功能"""
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
    
    print(f"\n查找群聊中的图片消息...")
    print(f"Chat ID: {test_chat_id}")
    
    # 获取最近消息，查找图片
    from lark_oapi.api.im.v1 import ListMessageRequest
    
    all_items = []
    page_token = None
    
    # 获取最近 100 条消息
    for page in range(2):
        builder = ListMessageRequest.builder() \
            .container_id_type("chat") \
            .container_id(test_chat_id) \
            .page_size(50)
        
        if page_token:
            builder = builder.page_token(page_token)
        
        request = builder.build()
        response = bot.client.im.v1.message.list(request)
        
        if not response.success():
            print(f"❌ 获取消息失败: {response.code} - {response.msg}")
            break
        
        items = response.data.items if response.data else []
        all_items.extend(items)
        
        has_more = response.data.has_more if hasattr(response.data, 'has_more') else False
        page_token = response.data.page_token if hasattr(response.data, 'page_token') else None
        
        if not has_more or not page_token:
            break
    
    print(f"✓ 获取到 {len(all_items)} 条消息")
    
    # 查找图片消息
    image_messages = []
    for item in all_items:
        msg_type = getattr(item, 'msg_type', 'unknown')
        if msg_type == 'image':
            try:
                content = json.loads(item.body.content) if item.body else {}
                image_key = content.get('image_key', '')
                message_id = getattr(item, 'message_id', '')
                create_time = int(getattr(item, 'create_time', 0) or 0)
                
                from datetime import datetime
                dt = datetime.fromtimestamp(create_time / 1000)
                
                image_messages.append({
                    'message_id': message_id,
                    'image_key': image_key,
                    'create_time': dt.strftime('%Y-%m-%d %H:%M:%S')
                })
            except:
                pass
    
    print(f"\n找到 {len(image_messages)} 条图片消息:")
    for i, img in enumerate(image_messages[:5], 1):  # 只显示前5条
        print(f"  {i}. [{img['create_time']}] message_id={img['message_id'][:20]}... image_key={img['image_key'][:20]}...")
    
    if not image_messages:
        print("\n⚠️ 没有找到图片消息，无法测试下载功能")
        return
    
    # 测试下载第一条图片
    test_img = image_messages[0]
    print(f"\n测试下载图片: {test_img['image_key'][:30]}...")
    
    # 获取 tenant_access_token
    tenant_token = bot._get_tenant_access_token()
    if not tenant_token:
        print("❌ 获取 tenant_access_token 失败")
        return
    
    import requests
    import urllib.parse
    
    encoded_key = urllib.parse.quote(test_img['image_key'], safe='')
    url = f"https://open.feishu.cn/open-apis/im/v1/messages/{test_img['message_id']}/resources/{encoded_key}?type=image"
    headers = {"Authorization": f"Bearer {tenant_token}"}
    
    print(f"下载 URL: {url[:80]}...")
    resp = requests.get(url, headers=headers, timeout=30)
    
    print(f"响应状态: {resp.status_code}")
    
    if resp.status_code == 200:
        image_data = resp.content
        print(f"✓ 下载成功！图片大小: {len(image_data)} bytes ({len(image_data)/1024:.1f} KB)")
        
        # 保存图片
        workplace_dir = get_absolute_path('WORKPLACE/user_images')
        os.makedirs(workplace_dir, exist_ok=True)
        
        import time
        image_filename = f"test_download_{int(time.time())}.png"
        image_path = os.path.join(workplace_dir, image_filename)
        
        with open(image_path, 'wb') as f:
            f.write(image_data)
        
        print(f"✓ 图片已保存到: {image_path}")
        
        # 验证文件
        if os.path.exists(image_path):
            file_size = os.path.getsize(image_path)
            print(f"✓ 文件验证成功，大小: {file_size} bytes")
        else:
            print("❌ 文件保存失败")
    else:
        print(f"❌ 下载失败: {resp.status_code}")
        print(f"错误信息: {resp.text[:500]}")

if __name__ == "__main__":
    test_image_download()
