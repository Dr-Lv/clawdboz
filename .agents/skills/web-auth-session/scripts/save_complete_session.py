#!/usr/bin/env python3
"""
Complete session saver - captures all possible login data.
Includes: Cookies, localStorage, sessionStorage, IndexedDB, and network tokens.
"""

import asyncio
import json
import os
import shutil
from datetime import datetime
from playwright.async_api import async_playwright


async def save_complete_session(url: str, site_name: str, browser_data_dir: str = 'browser_data'):
    """Save complete browser session including all storage types."""
    
    user_data_dir = os.path.join(browser_data_dir, site_name)
    
    # 清理旧数据确保干净
    if os.path.exists(user_data_dir):
        shutil.rmtree(user_data_dir)
    
    async with async_playwright() as p:
        context = await p.chromium.launch_persistent_context(
            user_data_dir,
            headless=False,  # 非 headless 模式更接近真实浏览器
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36',
            accept_downloads=True,
            locale='zh-CN',
            timezone_id='Asia/Shanghai',
        )
        page = context.pages[0] if context.pages else await context.new_page()
        
        # 存储网络请求
        auth_tokens = []
        def handle_route(route, request):
            headers = request.headers
            auth = headers.get('authorization') or headers.get('x-auth-token') or headers.get('x-token')
            if auth:
                auth_tokens.append({'url': request.url, 'token': auth[:100]})
            asyncio.create_task(route.continue_())
        
        await page.route("**/*", handle_route)
        
        try:
            print(f"1. 打开 {url}...")
            await page.goto(url, wait_until='networkidle', timeout=60000)
            await page.wait_for_timeout(3000)
            
            print("2. 请点击登录并扫码...")
            print("   登录成功后，按回车键继续...")
            input()
            
            print("3. 等待页面稳定...")
            await page.wait_for_timeout(5000)
            
            # 收集所有数据
            print("4. 收集登录数据...")
            
            # Cookies
            cookies = await context.cookies()
            
            # localStorage
            local_storage = await page.evaluate('''() => {
                const items = {};
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    items[key] = localStorage.getItem(key);
                }
                return items;
            }''')
            
            # sessionStorage
            session_storage = await page.evaluate('''() => {
                const items = {};
                for (let i = 0; i < sessionStorage.length; i++) {
                    const key = sessionStorage.key(i);
                    items[key] = sessionStorage.getItem(key);
                }
                return items;
            }''')
            
            # 尝试获取 IndexedDB 数据
            indexed_db_data = await page.evaluate('''() => {
                return new Promise(async (resolve) => {
                    try {
                        const databases = await indexedDB.databases();
                        const result = {};
                        for (const db of databases) {
                            result[db.name] = { version: db.version };
                        }
                        resolve(result);
                    } catch (e) {
                        resolve({error: e.toString()});
                    }
                });
            }''')
            
            # 保存所有数据
            session_data = {
                'metadata': {
                    'url': url,
                    'saved_at': datetime.now().isoformat(),
                    'site_name': site_name,
                },
                'cookies': cookies,
                'localStorage': local_storage,
                'sessionStorage': session_storage,
                'indexedDB': indexed_db_data,
                'networkTokens': auth_tokens,
            }
            
            os.makedirs('assets', exist_ok=True)
            with open(f'assets/{site_name}_complete.json', 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=2, ensure_ascii=False)
            
            print(f"\n✅ 完整会话已保存!")
            print(f"   浏览器数据: {user_data_dir}")
            print(f"   Session JSON: assets/{site_name}_complete.json")
            print(f"\n数据摘要:")
            print(f"   - Cookies: {len(cookies)}")
            print(f"   - localStorage: {len(local_storage)} 项")
            print(f"   - sessionStorage: {len(session_storage)} 项")
            print(f"   - IndexedDB 数据库: {len(indexed_db_data) if not indexed_db_data.get('error') else 0}")
            print(f"   - 网络 Token: {len(auth_tokens)}")
            
            # 测试发布功能
            print("\n5. 测试发布功能...")
            await page.click('text=发布产品')
            await page.wait_for_timeout(3000)
            
            has_login = await page.query_selector('text=扫码登录') is not None
            if has_login:
                print("   ⚠️ 仍需要登录 - 会话可能未完全保存")
            else:
                print("   ✅ 登录有效！可以发布内容")
                await page.screenshot(path=f'WORKPLACE/{site_name}_post_form.png')
            
        except Exception as e:
            print(f"错误: {e}")
        finally:
            await context.close()


if __name__ == '__main__':
    import sys
    if len(sys.argv) < 3:
        print("用法: python save_complete_session.py <url> <site_name>")
        sys.exit(1)
    
    asyncio.run(save_complete_session(sys.argv[1], sys.argv[2]))
