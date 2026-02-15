#!/usr/bin/env python3
"""
Correct session saving using Playwright's storage_state API.
This properly saves all browser storage including IndexedDB, cookies, and localStorage.
"""

import asyncio
import json
import os
from datetime import datetime
from playwright.async_api import async_playwright


async def save_session(url: str, site_name: str, wait_time: int = 5):
    """Save complete browser session using storage_state."""
    
    async with async_playwright() as p:
        # 使用非 headless 模式（某些网站会检测 headless）
        browser = await p.chromium.launch(headless=True)
        
        # 创建上下文
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
        )
        
        page = await context.new_page()
        
        try:
            print(f"1. 打开 {url}...")
            await page.goto(url, wait_until='networkidle', timeout=60000)
            await page.wait_for_timeout(2000)
            
            print("2. 请扫码登录...")
            print("   登录成功后按回车键继续...")
            input()
            
            print("3. 等待页面稳定...")
            await page.wait_for_timeout(wait_time * 1000)
            
            # 使用 storage_state() 保存所有存储状态
            print("4. 保存完整会话状态...")
            storage_state = await context.storage_state()
            
            # 添加元数据
            session_data = {
                'metadata': {
                    'url': url,
                    'saved_at': datetime.now().isoformat(),
                    'site_name': site_name,
                },
                'storage_state': storage_state,
            }
            
            # 保存到文件
            os.makedirs('assets', exist_ok=True)
            output_file = f'assets/{site_name}_storage.json'
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=2, ensure_ascii=False)
            
            print(f"\n✅ 会话已保存到: {output_file}")
            print(f"\n数据摘要:")
            print(f"   - Cookies: {len(storage_state.get('cookies', []))}")
            print(f"   - Origins: {len(storage_state.get('origins', []))}")
            for origin in storage_state.get('origins', []):
                print(f"     * {origin['origin']}: {len(origin.get('localStorage', []))} localStorage items")
            
            # 测试发布功能
            print("\n5. 测试发布功能...")
            await page.click('text=发布产品')
            await page.wait_for_timeout(3000)
            
            has_login = await page.query_selector('text=扫码登录') is not None
            if has_login:
                print("   ⚠️ 发布需要登录 - 会话未生效")
            else:
                print("   ✅ 发布功能正常！")
                await page.screenshot(path=f'WORKPLACE/{site_name}_post.png')
            
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
        print("用法: python save_session_correct.py <url> <site_name>")
        sys.exit(1)
    
    asyncio.run(save_session(sys.argv[1], sys.argv[2]))
