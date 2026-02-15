#!/usr/bin/env python3
"""
Correct session restore using Playwright's storage_state API.
"""

import asyncio
import json
import os
from playwright.async_api import async_playwright


async def restore_session(url: str, site_name: str, screenshot: str = None):
    """Restore browser session using storage_state."""
    
    session_file = f'assets/{site_name}_storage.json'
    
    if not os.path.exists(session_file):
        print(f"错误: 会话文件不存在: {session_file}")
        return False
    
    with open(session_file, 'r', encoding='utf-8') as f:
        session_data = json.load(f)
    
    storage_state = session_data.get('storage_state')
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        
        # 使用 storage_state 恢复所有存储
        context = await browser.new_context(
            storage_state=storage_state,
            viewport={'width': 1920, 'height': 1080},
        )
        
        page = await context.new_page()
        
        try:
            print(f"访问 {url}...")
            await page.goto(url, wait_until='networkidle', timeout=60000)
            await page.wait_for_timeout(3000)
            
            print("测试发布功能...")
            await page.click('text=发布产品')
            await page.wait_for_timeout(3000)
            
            has_login = await page.query_selector('text=扫码登录') is not None
            
            if screenshot:
                await page.screenshot(path=screenshot)
                print(f"截图已保存: {screenshot}")
            
            if has_login:
                print("❌ 会话恢复失败 - 仍需要登录")
                return False
            else:
                print("✅ 会话恢复成功！")
                return True
            
        except Exception as e:
            print(f"错误: {e}")
            return False
        finally:
            await context.close()
            await browser.close()


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 3:
        print("用法: python restore_session_correct.py <url> <site_name>")
        sys.exit(1)
    
    success = asyncio.run(restore_session(sys.argv[1], sys.argv[2]))
    sys.exit(0 if success else 1)
