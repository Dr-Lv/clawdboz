#!/usr/bin/env python3
"""
Restore saved login session and optionally verify it's still valid.
"""

import argparse
import asyncio
import json
import os

from playwright.async_api import async_playwright


async def restore_session(url: str, site_name: str, assets_dir: str = 'assets', 
                          verify: bool = False, verbose: bool = False) -> bool:
    """
    Restore saved session and optionally verify it.
    
    Args:
        url: Website URL
        site_name: Name of the session
        assets_dir: Directory containing session files
        verify: Whether to verify the session is valid
        verbose: Print verbose output
    
    Returns:
        True if successful
    """
    # Load session file
    session_file = os.path.join(assets_dir, f"{site_name}_status.json")
    
    if not os.path.exists(session_file):
        print(f"ERROR: Session file not found: {session_file}")
        return False
    
    if verbose:
        print(f"Loading session from {session_file}...")
    
    with open(session_file, 'r', encoding='utf-8') as f:
        session_data = json.load(f)
    
    if verbose:
        print(f"  - Cookies: {len(session_data.get('cookies', []))}")
        print(f"  - localStorage items: {len(session_data.get('localStorage', {}))}")
        print(f"  - sessionStorage items: {len(session_data.get('sessionStorage', {}))}")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = await context.new_page()
        
        try:
            # Restore cookies
            if session_data.get('cookies'):
                if verbose:
                    print("Restoring cookies...")
                await context.add_cookies(session_data['cookies'])
            
            # Navigate to page
            if verbose:
                print(f"Navigating to {url}...")
            await page.goto(url, wait_until='networkidle', timeout=30000)
            
            # Wait a bit for page to stabilize
            await page.wait_for_timeout(2000)
            
            # Restore localStorage
            if session_data.get('localStorage'):
                if verbose:
                    print("Restoring localStorage...")
                await page.evaluate('''(items) => {
                    for (const [key, value] of Object.entries(items)) {
                        localStorage.setItem(key, value);
                    }
                }''', session_data['localStorage'])
            
            # Restore sessionStorage
            if session_data.get('sessionStorage'):
                if verbose:
                    print("Restoring sessionStorage...")
                await page.evaluate('''(items) => {
                    for (const [key, value] of Object.entries(items)) {
                        sessionStorage.setItem(key, value);
                    }
                }''', session_data['sessionStorage'])
            
            # Reload to apply storage changes
            if session_data.get('localStorage') or session_data.get('sessionStorage'):
                if verbose:
                    print("Reloading to apply storage changes...")
                await page.reload(wait_until='networkidle')
                await page.wait_for_timeout(2000)
            
            # Verify session if requested
            if verify:
                if verbose:
                    print("Verifying session...")
                
                # Check for logged-in indicators
                logged_in_indicators = [
                    '.user-avatar',
                    '.profile-dropdown',
                    '[class*="user-menu"]',
                    '[class*="account-menu"]',
                    'button:has-text("退出")',
                    'button:has-text("Logout")',
                    'a:has-text("退出")',
                    'a:has-text("Logout")',
                    '[class*="username"]',
                    '[class*="nickname"]',
                ]
                
                is_logged_in = False
                for selector in logged_in_indicators:
                    try:
                        element = await page.query_selector(selector)
                        if element:
                            is_logged_in = True
                            if verbose:
                                print(f"  Logged-in indicator found: {selector}")
                            break
                    except:
                        continue
                
                # Check for login-required indicators
                need_login_indicators = [
                    'input[type="password"]',
                    '.login-form',
                    '.signin-form',
                    '[class*="login"] input',
                ]
                
                need_login = False
                for selector in need_login_indicators:
                    try:
                        element = await page.query_selector(selector)
                        if element:
                            need_login = True
                            if verbose:
                                print(f"  Login indicator found: {selector}")
                            break
                    except:
                        continue
                
                if is_logged_in:
                    print("SESSION_VALID")
                elif need_login:
                    print("SESSION_INVALID")
                    return False
                else:
                    print("SESSION_UNCERTAIN")
            
            if verbose:
                print("Session restored successfully")
            
            print(f"Session restored for {site_name}")
            return True
            
        except Exception as e:
            print(f"ERROR: {e}")
            return False
        finally:
            await context.close()
            await browser.close()


def main():
    parser = argparse.ArgumentParser(description='Restore website login session')
    parser.add_argument('url', help='Website URL')
    parser.add_argument('--name', '-n', required=True, help='Site name (session file name)')
    parser.add_argument('--assets-dir', '-a', default='assets', 
                        help='Directory containing session files')
    parser.add_argument('--verify', action='store_true', 
                        help='Verify session is still valid')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    success = asyncio.run(restore_session(
        args.url, args.name, args.assets_dir, args.verify, args.verbose
    ))
    
    return 0 if success else 1


if __name__ == '__main__':
    exit(main())
