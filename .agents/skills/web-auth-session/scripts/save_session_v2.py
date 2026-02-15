#!/usr/bin/env python3
"""
Save complete login session state v2 - Enhanced version.

Captures:
- Cookies (all domains)
- localStorage
- sessionStorage  
- IndexedDB
- Network request tokens (intercepted)
- Page JavaScript variables
- Session/Local Storage keys with user data patterns
"""

import argparse
import asyncio
import json
import os
from datetime import datetime
from urllib.parse import urlparse

from playwright.async_api import async_playwright


async def get_all_storage_data(page, domain: str) -> dict:
    """Extract all storage data from the page."""
    
    # Get cookies
    cookies = await page.context.cookies()
    
    # Get localStorage - all items
    local_storage = await page.evaluate('''() => {
        const items = {};
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            items[key] = localStorage.getItem(key);
        }
        return items;
    }''')
    
    # Get sessionStorage - all items
    session_storage = await page.evaluate('''() => {
        const items = {};
        for (let i = 0; i < sessionStorage.length; i++) {
            const key = sessionStorage.key(i);
            items[key] = sessionStorage.getItem(key);
        }
        return items;
    }''')
    
    # Get common auth-related JS variables from window object
    js_vars = await page.evaluate('''() => {
        const authPatterns = ['token', 'user', 'auth', 'session', 'login', 'account', 
                             'uid', 'uuid', 'id', 'profile', 'credential', 'pass',
                             'key', 'secret', 'access', 'refresh'];
        const vars = {};
        
        for (const key of Object.keys(window)) {
            const lowerKey = key.toLowerCase();
            if (authPatterns.some(p => lowerKey.includes(p))) {
                try {
                    const value = window[key];
                    if (value !== null && value !== undefined) {
                        if (typeof value === 'string' || typeof value === 'number' || typeof value === 'boolean') {
                            vars[key] = value;
                        } else if (typeof value === 'object') {
                            // Try to serialize, but limit depth
                            vars[key] = JSON.stringify(value).substring(0, 1000);
                        }
                    }
                } catch (e) {
                    // Skip if can't access
                }
            }
        }
        return vars;
    }''')
    
    # Try to get IndexedDB database names
    indexed_db_info = await page.evaluate('''() => {
        return new Promise((resolve) => {
            try {
                // Try to list databases if API is available
                if (typeof indexedDB.databases === 'function') {
                    indexedDB.databases().then(dbs => {
                        resolve({databases: dbs.map(db => db.name)});
                    }).catch(e => {
                        resolve({error: e.toString()});
                    });
                } else {
                    resolve({note: 'indexedDB.databases() not supported'});
                }
            } catch (e) {
                resolve({error: e.toString()});
            }
        });
    }''')
    
    # Get document cookies (may differ from context cookies)
    document_cookies = await page.evaluate('() => document.cookie')
    
    # Try to get any auth tokens from common storage keys
    auth_data = await page.evaluate('''() => {
        const patterns = ['token', 'auth', 'session', 'user', 'login', 'credential'];
        const data = {};
        
        // Check localStorage
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            if (patterns.some(p => key.toLowerCase().includes(p))) {
                data[`local_${key}`] = localStorage.getItem(key);
            }
        }
        
        // Check sessionStorage
        for (let i = 0; i < sessionStorage.length; i++) {
            const key = sessionStorage.key(i);
            if (patterns.some(p => key.toLowerCase().includes(p))) {
                data[`session_${key}`] = sessionStorage.getItem(key);
            }
        }
        
        return data;
    }''')
    
    return {
        'cookies': cookies,
        'localStorage': local_storage,
        'sessionStorage': session_storage,
        'indexedDB': indexed_db_info,
        'jsVariables': js_vars,
        'documentCookies': document_cookies,
        'authData': auth_data,
    }


async def intercept_network_tokens(page):
    """
    Intercept network requests to capture authorization tokens.
    Returns intercepted headers and tokens.
    """
    intercepted_data = {
        'authorization_headers': [],
        'api_tokens': [],
        'request_headers': {},
    }
    
    def handle_route(route, request):
        headers = request.headers
        
        # Capture authorization headers
        auth_header = headers.get('authorization') or headers.get('Authorization')
        if auth_header:
            intercepted_data['authorization_headers'].append({
                'url': request.url,
                'method': request.method,
                'auth': auth_header[:100] + '...' if len(auth_header) > 100 else auth_header,
            })
        
        # Capture common token headers
        for key in ['x-token', 'x-auth-token', 'x-access-token', 'api-key', 'apikey']:
            if key in headers:
                intercepted_data['api_tokens'].append({
                    'url': request.url,
                    'header': key,
                    'value': headers[key][:50] + '...' if len(headers[key]) > 50 else headers[key],
                })
        
        # Store request headers for the main domain
        if not any(h in request.url for h in ['google', 'bing', 'baidu', 'analytics', 'tracking']):
            intercepted_data['request_headers'][request.url[:100]] = {
                k: v for k, v in headers.items() 
                if k.lower() in ['authorization', 'cookie', 'x-token', 'x-auth', 'x-user']
            }
        
        route.continue_()
    
    await page.route("**/*", handle_route)
    return intercepted_data


async def save_session(url: str, site_name: str, wait_time: int = 5, 
                       assets_dir: str = 'assets', verbose: bool = False,
                       intercept_network: bool = True) -> bool:
    """
    Save complete login session v2.
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = await context.new_page()
        
        # Setup network interception
        intercepted_data = None
        if intercept_network:
            intercepted_data = await intercept_network_tokens(page)
        
        try:
            if verbose:
                print(f"Navigating to {url}...")
            
            # Navigate with longer timeout
            await page.goto(url, wait_until='networkidle', timeout=60000)
            
            # Wait for page to fully load
            await page.wait_for_timeout(wait_time * 1000)
            
            # Check if user is logged in by looking for user elements
            user_elements = await page.query_selector_all(
                '[class*="user"], [class*="avatar"], [class*="profile"], '
                '[class*="nickname"], [class*="username"], '
                'text=退出, text=Logout, text=我的'
            )
            login_detected = len(user_elements) > 0
            
            if verbose:
                print(f"User elements found: {len(user_elements)}")
                print(f"Login appears to be: {'ACTIVE' if login_detected else 'INACTIVE'}")
            
            # Get domain
            parsed = urlparse(page.url)
            domain = parsed.netloc
            
            # Get all storage data
            if verbose:
                print("Extracting comprehensive session data...")
            
            storage_data = await get_all_storage_data(page, domain)
            
            # Prepare session data
            session_data = {
                'metadata': {
                    'url': url,
                    'saved_at': datetime.now().isoformat(),
                    'domain': domain,
                    'site_name': site_name,
                    'login_detected': login_detected,
                },
                'network': intercepted_data or {},
                **storage_data
            }
            
            # Create assets directory
            if not os.path.exists(assets_dir):
                os.makedirs(assets_dir)
            
            # Save to file
            output_file = os.path.join(assets_dir, f"{site_name}_status.json")
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=2, ensure_ascii=False)
            
            if verbose:
                print(f"\n✅ Session saved to {output_file}")
                print(f"\n📊 Summary:")
                print(f"  - Cookies: {len(storage_data['cookies'])}")
                print(f"  - localStorage: {len(storage_data['localStorage'])} items")
                print(f"  - sessionStorage: {len(storage_data['sessionStorage'])} items")
                print(f"  - JS Variables: {len(storage_data['jsVariables'])} found")
                print(f"  - Auth Data: {len(storage_data['authData'])} entries")
                if intercepted_data:
                    print(f"  - Auth Headers: {len(intercepted_data['authorization_headers'])} captured")
                    print(f"  - API Tokens: {len(intercepted_data['api_tokens'])} captured")
                print(f"  - Login State: {'DETECTED' if login_detected else 'NOT DETECTED'}")
            
            print(f"Session saved to {output_file}")
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
    parser = argparse.ArgumentParser(description='Save website login session v2 (Enhanced)')
    parser.add_argument('url', help='Website URL')
    parser.add_argument('--name', '-n', required=True, help='Site name for session file')
    parser.add_argument('--wait', '-w', type=int, default=5, 
                        help='Wait time after page load (seconds)')
    parser.add_argument('--assets-dir', '-a', default='assets', 
                        help='Directory to save session files')
    parser.add_argument('--no-intercept', action='store_true',
                        help='Disable network interception')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    success = asyncio.run(save_session(
        args.url, args.name, args.wait, args.assets_dir, args.verbose,
        intercept_network=not args.no_intercept
    ))
    
    return 0 if success else 1


if __name__ == '__main__':
    exit(main())
