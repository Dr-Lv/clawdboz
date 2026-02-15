#!/usr/bin/env python3
"""测试图片 API"""

import sys
import os
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

import requests
import urllib.parse
from src.config import CONFIG
from src.bot import LarkBot

def test_api():
    app_id = CONFIG.get('feishu', {}).get('app_id')
    app_secret = CONFIG.get('feishu', {}).get('app_secret')
    
    bot = LarkBot(app_id, app_secret)
    
    tenant_token = bot._get_tenant_access_token()
    print(f"Token: {tenant_token[:30]}...")
    
    image_key = "img_v3_02ad_e19fca1f-912a-450e-95de-3c229091b53g"
    
    # 方法1: 图片 API v4
    url1 = f"https://open.feishu.cn/open-apis/image/v4/get?image_key={urllib.parse.quote(image_key)}"
    headers = {"Authorization": f"Bearer {tenant_token}"}
    
    print(f"\n方法1: {url1}")
    resp1 = requests.get(url1, headers=headers, timeout=30)
    print(f"Status: {resp1.status_code}")
    print(f"Content-Type: {resp1.headers.get('Content-Type')}")
    print(f"Body: {resp1.text[:500]}")
    
    # 方法2: 图片 API v1
    url2 = f"https://open.feishu.cn/open-apis/image/v1/get?image_key={urllib.parse.quote(image_key)}"
    print(f"\n方法2: {url2}")
    resp2 = requests.get(url2, headers=headers, timeout=30)
    print(f"Status: {resp2.status_code}")
    print(f"Content-Type: {resp2.headers.get('Content-Type')}")
    if resp2.headers.get('Content-Type', '').startswith('image/'):
        print(f"图片大小: {len(resp2.content)} bytes")
    else:
        print(f"Body: {resp2.text[:500]}")

if __name__ == "__main__":
    test_api()
