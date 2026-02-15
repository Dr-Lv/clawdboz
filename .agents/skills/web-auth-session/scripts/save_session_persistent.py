#!/usr/bin/env python3
"""
Save login session using persistent browser context.
This preserves browser state (cookies, storage, cache) across sessions.
"""

import argparse
import asyncio
import json
import os
from datetime import datetime
from urllib.parse import urlparse

from playwright.async_api import async_playwright


async def save_session(url: str, site_name: str, wait_time: int = 5, 
                       assets_dir: str = 'assets', 
                       browser_data_dir: str = 'browser_data',
                       verbose: bool = False) -> bool:
    """
    Save session using persistent browser context.
    
    Args:
        url: Website URL
        site_name: Name for the session file
        wait_time: Time to wait after page load
        assets_dir: Directory to save session JSON
        browser_data_dir: Directory to persist browser state
        verbose: Print verbose output
    """
    
    # Create browser data directory for this site
    user_data_dir = os.path.join(browser_data_dir, site_name)
    os.makedirs(user_data_dir, exist_ok=True)
    
    async with async_playwright() as p:
        # Use persistent context - this saves browser state to disk
        context = await p.chromium.launch_persistent_context(
            user_data_dir,
            headless=True,
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            # Preserve all browser state
            accept_downloads=True,
            bypass_csp=True,
            java_script_enabled=True,
        )
        
        page = context.pages[0] if context.pages else await context.new_page()
        
        try:
            if verbose:
                print(f"Opening browser with persistent data dir: {user_data_dir}")
                print(f"Navigating to {url}...")
            
            # Navigate to page
            await page.goto(url, wait_until='networkidle', timeout=60000)
            await page.wait_for_timeout(wait_time * 1000)
            
            # Check if user is logged in
            user_elements = await page.query_selector_all(
                '[class*="user"], [class*="avatar"], [class*="profile"], '
                '[class*="nickname"], [class*="username"]'
            )
            login_detected = len(user_elements) > 0
            
            if verbose:
                print(f"Login detected: {login_detected}")
            
            # Get domain
            parsed = urlparse(page.url)
            domain = parsed.netloc
            
            # Get storage data
            cookies = await context.cookies()
            
            local_storage = await page.evaluate('''() => {
                const items = {};
                for (let i = 0; i < localStorage.length; i++) {
                    const key = localStorage.key(i);
                    items[key] = localStorage.getItem(key);
                }
                return items;
            }''')
            
            session_storage = await page.evaluate('''() => {
                const items = {};
                for (let i = 0; i < sessionStorage.length; i++) {
                    const key = sessionStorage.key(i);
                    items[key] = sessionStorage.getItem(key);
                }
                return items;
            }''')
            
            # Prepare session data
            session_data = {
                'metadata': {
                    'url': url,
                    'saved_at': datetime.now().isoformat(),
                    'domain': domain,
                    'site_name': site_name,
                    'login_detected': login_detected,
                    'user_data_dir': user_data_dir,
                },
                'cookies': cookies,
                'localStorage': local_storage,
                'sessionStorage': session_storage,
            }
            
            # Create assets directory
            os.makedirs(assets_dir, exist_ok=True)
            
            # Save to file
            output_file = os.path.join(assets_dir, f"{site_name}_status.json")
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=2, ensure_ascii=False)
            
            if verbose:
                print(f"\n✅ Session saved!")
                print(f"  - Browser data: {user_data_dir}")
                print(f"  - Session JSON: {output_file}")
                print(f"  - Cookies: {len(cookies)}")
                print(f"  - localStorage: {len(local_storage)} items")
                print(f"  - sessionStorage: {len(session_storage)} items")
            
            print(f"Session saved to {output_file}")
            print(f"Browser data persisted in: {user_data_dir}")
            return True
            
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            # Important: Close context to ensure data is saved
            await context.close()


def main():
    parser = argparse.ArgumentParser(description='Save session with persistent browser')
    parser.add_argument('url', help='Website URL')
    parser.add_argument('--name', '-n', required=True, help='Site name')
    parser.add_argument('--wait', '-w', type=int, default=5, 
                        help='Wait time after page load (seconds)')
    parser.add_argument('--assets-dir', '-a', default='assets', 
                        help='Directory to save session JSON')
    parser.add_argument('--browser-data-dir', '-b', default='browser_data',
                        help='Directory to persist browser state')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    success = asyncio.run(save_session(
        args.url, args.name, args.wait, 
        args.assets_dir, args.browser_data_dir, args.verbose
    ))
    
    return 0 if success else 1


if __name__ == '__main__':
    exit(main())
