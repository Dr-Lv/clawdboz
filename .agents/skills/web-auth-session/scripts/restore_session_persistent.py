#!/usr/bin/env python3
"""
Restore session using persistent browser context.
This reuses the saved browser state (cookies, storage, cache).
"""

import argparse
import asyncio
import json
import os

from playwright.async_api import async_playwright


async def restore_session(url: str, site_name: str, 
                          assets_dir: str = 'assets',
                          browser_data_dir: str = 'browser_data',
                          verify: bool = False, 
                          screenshot: str = None,
                          verbose: bool = False) -> bool:
    """
    Restore session using persistent browser context.
    
    Args:
        url: Website URL
        site_name: Name of the session
        assets_dir: Directory containing session JSON
        browser_data_dir: Directory with persisted browser state
        verify: Whether to verify the session is valid
        screenshot: Path to save screenshot (optional)
        verbose: Print verbose output
    """
    
    # Load session file
    session_file = os.path.join(assets_dir, f"{site_name}_status.json")
    
    if not os.path.exists(session_file):
        print(f"ERROR: Session file not found: {session_file}")
        return False
    
    # Check for persisted browser data
    user_data_dir = os.path.join(browser_data_dir, site_name)
    has_persisted_data = os.path.exists(user_data_dir) and len(os.listdir(user_data_dir)) > 0
    
    if verbose:
        print(f"Loading session from {session_file}...")
        print(f"Browser data directory: {user_data_dir}")
        print(f"Has persisted data: {has_persisted_data}")
    
    with open(session_file, 'r', encoding='utf-8') as f:
        session_data = json.load(f)
    
    async with async_playwright() as p:
        if has_persisted_data:
            # Use persistent context - this restores all browser state
            if verbose:
                print("Using persistent browser context...")
            
            context = await p.chromium.launch_persistent_context(
                user_data_dir,
                headless=True,
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
            )
            page = context.pages[0] if context.pages else await context.new_page()
            
            # Navigate to URL
            if verbose:
                print(f"Navigating to {url}...")
            await page.goto(url, wait_until='networkidle', timeout=60000)
            await page.wait_for_timeout(3000)
            
        else:
            # Fallback: use regular context with cookie restore
            if verbose:
                print("No persisted data found, using regular context...")
            
            browser = await p.chromium.launch(headless=True)
            context = await browser.new_context(
                viewport={'width': 1920, 'height': 1080},
                user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
            )
            page = await context.new_page()
            
            # Restore cookies
            if session_data.get('cookies'):
                await context.add_cookies(session_data['cookies'])
            
            await page.goto(url, wait_until='networkidle', timeout=60000)
            await page.wait_for_timeout(3000)
            
            # Restore storage
            if session_data.get('localStorage'):
                await page.evaluate('''(items) => {
                    for (const [k, v] of Object.entries(items)) {
                        localStorage.setItem(k, v);
                    }
                }''', session_data['localStorage'])
            
            if session_data.get('sessionStorage'):
                await page.evaluate('''(items) => {
                    for (const [k, v] of Object.entries(items)) {
                        sessionStorage.setItem(k, v);
                    }
                }''', session_data['sessionStorage'])
            
            await page.reload(wait_until='networkidle')
            await page.wait_for_timeout(3000)
        
        try:
            # Verify session if requested
            if verify:
                if verbose:
                    print("Verifying session...")
                
                logged_in_indicators = [
                    '.user-avatar', '.avatar', '[class*="user-menu"]',
                    '[class*="nickname"]', '[class*="username"]',
                    'text=退出', 'text=Logout', 'text=我的'
                ]
                
                is_logged_in = False
                for selector in logged_in_indicators:
                    try:
                        element = await page.query_selector(selector)
                        if element:
                            is_logged_in = True
                            if verbose:
                                print(f"  Found: {selector}")
                            break
                    except:
                        continue
                
                # Check for login button
                need_login = await page.query_selector('text=登录, text=Login') is not None
                
                if is_logged_in:
                    print("✅ SESSION_VALID - Logged in")
                elif need_login:
                    print("❌ SESSION_INVALID - Login required")
                else:
                    print("⚠️ SESSION_UNCERTAIN")
            
            # Take screenshot if requested
            if screenshot:
                await page.screenshot(path=screenshot, full_page=False)
                print(f"Screenshot saved to {screenshot}")
            
            current_url = page.url
            if verbose:
                print(f"\n✅ Session restored")
                print(f"Current URL: {current_url}")
            
            print(f"Session restored for {site_name}")
            return True
            
        except Exception as e:
            print(f"ERROR: {e}")
            return False
        finally:
            await context.close()
            if not has_persisted_data:
                await browser.close()


def main():
    parser = argparse.ArgumentParser(description='Restore session with persistent browser')
    parser.add_argument('url', help='Website URL')
    parser.add_argument('--name', '-n', required=True, help='Site name')
    parser.add_argument('--assets-dir', '-a', default='assets', 
                        help='Directory containing session JSON')
    parser.add_argument('--browser-data-dir', '-b', default='browser_data',
                        help='Directory with persisted browser state')
    parser.add_argument('--verify', action='store_true', 
                        help='Verify session is valid')
    parser.add_argument('--screenshot', '-s', help='Save screenshot to path')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    success = asyncio.run(restore_session(
        args.url, args.name, 
        args.assets_dir, args.browser_data_dir,
        args.verify, args.screenshot, args.verbose
    ))
    
    return 0 if success else 1


if __name__ == '__main__':
    exit(main())
