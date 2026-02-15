#!/usr/bin/env python3
"""测试文件下载功能"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import json
from src.config import CONFIG, get_absolute_path
from src.bot import LarkBot

def test_file_download():
    """测试文件下载功能"""
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
    
    print(f"\n查找群聊中的文件消息...")
    print(f"Chat ID: {test_chat_id}")
    
    # 获取最近消息
    from lark_oapi.api.im.v1 import ListMessageRequest
    
    all_items = []
    page_token = None
    
    for page in range(3):
        builder = ListMessageRequest.builder() \
            .container_id_type("chat") \
            .container_id(test_chat_id) \
            .page_size(50)
        
        if page_token:
            builder = builder.page_token(page_token)
        
        request = builder.build()
        response = bot.client.im.v1.message.list(request)
        
        if not response.success():
            break
        
        items = response.data.items if response.data else []
        all_items.extend(items)
        
        has_more = response.data.has_more if hasattr(response.data, 'has_more') else False
        page_token = response.data.page_token if hasattr(response.data, 'page_token') else None
        
        if not has_more or not page_token:
            break
    
    print(f"✓ 获取到 {len(all_items)} 条消息")
    
    # 查找文件消息
    file_messages = []
    
    for item in all_items:
        msg_type = getattr(item, 'msg_type', 'unknown')
        try:
            content = json.loads(item.body.content) if item.body else {}
            message_id = getattr(item, 'message_id', '')
            create_time = int(getattr(item, 'create_time', 0) or 0)
            
            from datetime import datetime
            dt = datetime.fromtimestamp(create_time / 1000)
            
            if msg_type == 'file':
                file_key = content.get('file_key', '')
                file_name = content.get('file_name', 'unknown')
                file_messages.append({
                    'message_id': message_id,
                    'file_key': file_key,
                    'file_name': file_name,
                    'create_time': dt.strftime('%Y-%m-%d %H:%M:%S')
                })
        except:
            pass
    
    print(f"\n找到 {len(file_messages)} 条文件消息:")
    for i, f in enumerate(file_messages[:5], 1):
        print(f"  {i}. [{f['create_time']}] {f['file_name']}")
    
    if not file_messages:
        print("\n⚠️ 没有找到文件消息")
        return
    
    # 获取 tenant_access_token
    tenant_token = bot._get_tenant_access_token()
    if not tenant_token:
        print("❌ 获取 tenant_access_token 失败")
        return
    
    print(f"\n✓ 获取 tenant_access_token 成功")
    
    # 测试保存路径
    files_dir = get_absolute_path('WORKPLACE/user_files')
    os.makedirs(files_dir, exist_ok=True)
    print(f"✓ 文件保存目录: {files_dir}")
    
    # 测试下载第一个文件
    test_file = file_messages[0]
    print(f"\n测试下载文件: {test_file['file_name']}")
    
    import requests
    import urllib.parse
    import time
    
    encoded_key = urllib.parse.quote(test_file['file_key'], safe='')
    url = f"https://open.feishu.cn/open-apis/im/v1/messages/{test_file['message_id']}/resources/{encoded_key}?type=file"
    headers = {"Authorization": f"Bearer {tenant_token}"}
    
    print(f"请求 URL: {url[:80]}...")
    resp = requests.get(url, headers=headers, timeout=60)
    
    print(f"响应状态: {resp.status_code}")
    
    if resp.status_code == 200:
        file_data = resp.content
        print(f"✓ 下载成功！文件大小: {len(file_data)} bytes ({len(file_data)/1024:.1f} KB)")
        
        # 保存文件
        safe_filename = f"{int(time.time())}_{test_file['file_name']}"
        file_path = os.path.join(files_dir, safe_filename)
        
        with open(file_path, 'wb') as f:
            f.write(file_data)
        
        print(f"✓ 文件已保存到: {file_path}")
        
        # 验证文件
        if os.path.exists(file_path):
            file_size = os.path.getsize(file_path)
            print(f"✓ 文件验证成功，大小: {file_size} bytes")
            
            # 列出目录中的文件
            all_files = os.listdir(files_dir)
            print(f"\nWORKPLACE/user_files 目录现在有 {len(all_files)} 个文件:")
            for f in all_files[:10]:
                fpath = os.path.join(files_dir, f)
                fsize = os.path.getsize(fpath)
                print(f"  - {f} ({fsize/1024:.1f} KB)")
        else:
            print("❌ 文件保存失败")
    else:
        print(f"❌ 下载失败: {resp.status_code}")
        print(f"错误信息: {resp.text[:500]}")

if __name__ == "__main__":
    test_file_download()
