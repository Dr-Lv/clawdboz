#!/usr/bin/env python3
"""
Restore saved login session v2 - Enhanced version.

Supports:
- Cookies restoration
- localStorage/sessionStorage restoration
- JS variables restoration
- Network headers setup
- API token injection
"""

import argparse
import asyncio
import json
import os

from playwright.async_api import async_playwright


async def restore_session(url: str, site_name: str, assets_dir: str = 'assets', 
                          verify: bool = False, verbose: bool = False,
                          inject_headers: bool = True) -> bool:
    """
    Restore saved session v2 with enhanced capabilities.
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
    
    metadata = session_data.get('metadata', {})
    if verbose:
        print(f"  Session saved at: {metadata.get('saved_at')}")
        print(f"  Original URL: {metadata.get('url')}")
        print(f"  Login was detected: {metadata.get('login_detected', False)}")
        print(f"  Cookies: {len(session_data.get('cookies', []))}")
        print(f"  localStorage: {len(session_data.get('localStorage', {}))} items")
        print(f"  JS Variables: {len(session_data.get('jsVariables', {}))} found")
    
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = await context.new_page()
        
        # Setup request interception for header injection
        auth_headers = {}
        if inject_headers and 'network' in session_data:
            network = session_data['network']
            
            # Extract authorization headers
            for item in network.get('authorization_headers', []):
                auth = item.get('auth', '')
                if auth.startswith('Bearer ') or auth.startswith('token='):
                    auth_headers['Authorization'] = auth
                    break
            
            # Extract API tokens
            for token in network.get('api_tokens', []):
                header_name = token.get('header', '')
                if header_name:
                    auth_headers[header_name] = token.get('value', '')
        
        # Intercept requests to inject auth headers
        if auth_headers:
            async def handle_route(route, request):
                # Only inject for same-origin requests
                if session_data['metadata'].get('domain') in request.url:
                    headers = {**request.headers, **auth_headers}
                    await route.continue_(headers=headers)
                else:
                    await route.continue_()
            
            await page.route("**/*", handle_route)
            if verbose:
                print(f"  Injected auth headers: {list(auth_headers.keys())}")
        
        try:
            # Restore cookies
            if session_data.get('cookies'):
                if verbose:
                    print("Restoring cookies...")
                await context.add_cookies(session_data['cookies'])
            
            # Navigate to page
            if verbose:
                print(f"Navigating to {url}...")
            await page.goto(url, wait_until='networkidle', timeout=60000)
            await page.wait_for_timeout(3000)
            
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
            
            # Restore JS variables
            if session_data.get('jsVariables'):
                if verbose:
                    print("Restoring JS variables...")
                js_vars = session_data['jsVariables']
                await page.evaluate('''(vars) => {
                    for (const [key, value] of Object.entries(vars)) {
                        try {
                            // Try to parse JSON values
                            if (typeof value === 'string' && 
                                (value.startsWith('{') || value.startsWith('['))) {
                                window[key] = JSON.parse(value);
                            } else {
                                window[key] = value;
                            }
                        } catch (e) {
                            window[key] = value;
                        }
                    }
                }''', js_vars)
            
            # Restore auth data
            if session_data.get('authData'):
                if verbose:
                    print("Restoring auth data...")
                auth_data = session_data['authData']
                for key, value in auth_data.items():
                    if key.startswith('local_'):
                        await page.evaluate(f'() => localStorage.setItem("{key[6:]}", "{value}")')
                    elif key.startswith('session_'):
                        await page.evaluate(f'() => sessionStorage.setItem("{key[8:]}", "{value}")')
            
            # Reload to apply all changes
            if verbose:
                print("Reloading to apply session...")
            await page.reload(wait_until='networkidle')
            await page.wait_for_timeout(3000)
            
            # Verify session if requested
            if verify:
                if verbose:
                    print("Verifying session...")
                
                # Check for logged-in indicators
                logged_in_indicators = [
                    '.user-avatar', '.avatar', '.profile-avatar',
                    '[class*="user-menu"]', '[class*="account-menu"]',
                    '[class*="nickname"]', '[class*="username"]',
                    'text=退出', 'text=Logout', 'text=我的', 'text=个人中心',
                ]
                
                is_logged_in = False
                found_indicators = []
                for selector in logged_in_indicators:
                    try:
                        element = await page.query_selector(selector)
                        if element:
                            is_logged_in = True
                            found_indicators.append(selector)
                    except:
                        continue
                
                if verbose and found_indicators:
                    print(f"  Found indicators: {found_indicators}")
                
                # Check for login-required indicators
                need_login_indicators = [
                    'input[type="password"]',
                    '.login-form', '.signin-form',
                    'text=登录', 'text=Login', 'text=Sign in',
                    '[class*="login-modal"]', '[class*="login-popup"]',
                ]
                
                need_login = False
                for selector in need_login_indicators:
                    try:
                        element = await page.query_selector(selector)
                        if element:
                            need_login = True
                            break
                    except:
                        continue
                
                if is_logged_in:
                    print("✅ SESSION_VALID")
                elif need_login:
                    print("❌ SESSION_INVALID")
                    return False
                else:
                    print("⚠️ SESSION_UNCERTAIN")
            
            if verbose:
                print("\n✅ Session restoration completed")
            
            print(f"Session restored for {site_name}")
            return True
            
        except Exception as e:
            print(f"ERROR: {e}")
            import traceback
            traceback.print_exc()
            return False
        finally:
            await context.close()
            await browser.close()


def main():
    parser = argparse.ArgumentParser(description='Restore website login session v2 (Enhanced)')
    parser.add_argument('url', help='Website URL')
    parser.add_argument('--name', '-n', required=True, help='Site name (session file name)')
    parser.add_argument('--assets-dir', '-a', default='assets', 
                        help='Directory containing session files')
    parser.add_argument('--verify', action='store_true', 
                        help='Verify session is still valid')
    parser.add_argument('--no-header-inject', action='store_true',
                        help='Disable auth header injection')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    success = asyncio.run(restore_session(
        args.url, args.name, args.assets_dir, args.verify, args.verbose,
        inject_headers=not args.no_header_inject
    ))
    
    return 0 if success else 1


if __name__ == '__main__':
    exit(main())
