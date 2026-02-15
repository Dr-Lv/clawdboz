#!/usr/bin/env python3
"""
Detect if a website requires login.

Returns:
    NEED_LOGIN - Login is required
    LOGGED_IN - User is already logged in
    PUBLIC - Page is publicly accessible
"""

import argparse
import asyncio
import sys
from urllib.parse import urlparse

from playwright.async_api import async_playwright


# Common selectors that indicate login state
LOGIN_INDICATORS = [
    # Login form elements
    'input[type="password"]',
    'input[name="password"]',
    'input[id="password"]',
    '.login-form',
    '.signin-form',
    '#login-form',
    '[class*="login"]',
    '[class*="signin"]',
    '[id*="login"]',
    # QR code containers
    '.qr-code',
    '[class*="qr"]',
    'canvas[class*="qr"]',
    'img[src*="qr"]',
    # Auth-related buttons
    'button:has-text("登录")',
    'button:has-text("Log in")',
    'button:has-text("Sign in")',
    'a:has-text("登录")',
    'a:has-text("Log in")',
]

LOGGED_IN_INDICATORS = [
    # User profile elements
    '.user-avatar',
    '.profile-dropdown',
    '[class*="user-menu"]',
    '[class*="account-menu"]',
    # Logout buttons
    'button:has-text("退出")',
    'button:has-text("Logout")',
    'a:has-text("退出")',
    'a:has-text("Logout")',
    # Username display
    '[class*="username"]',
    '[class*="nickname"]',
]


def get_domain(url: str) -> str:
    """Extract domain from URL."""
    parsed = urlparse(url)
    return parsed.netloc


async def detect_login_state(url: str, timeout: int = 10, verbose: bool = False) -> str:
    """
    Detect if the website requires login.
    
    Returns:
        NEED_LOGIN, LOGGED_IN, or PUBLIC
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = await context.new_page()
        
        try:
            # Navigate to the page
            if verbose:
                print(f"Navigating to {url}...")
            
            response = await page.goto(url, wait_until='networkidle', timeout=timeout*1000)
            
            # Wait a bit for dynamic content
            await page.wait_for_timeout(2000)
            
            current_url = page.url
            
            # Check if redirected to login page
            login_keywords = ['login', 'signin', 'auth', 'passport', 'sign-in', 'log-in']
            if any(keyword in current_url.lower() for keyword in login_keywords):
                if verbose:
                    print(f"Redirected to login page: {current_url}")
                return "NEED_LOGIN"
            
            # Check for login indicators
            login_found = False
            for selector in LOGIN_INDICATORS:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        if verbose:
                            print(f"Login indicator found: {selector}")
                        login_found = True
                        break
                except:
                    continue
            
            # Check for logged-in indicators
            logged_in_found = False
            for selector in LOGGED_IN_INDICATORS:
                try:
                    element = await page.query_selector(selector)
                    if element:
                        if verbose:
                            print(f"Logged-in indicator found: {selector}")
                        logged_in_found = True
                        break
                except:
                    continue
            
            # Determine state
            if logged_in_found:
                return "LOGGED_IN"
            elif login_found:
                return "NEED_LOGIN"
            else:
                # Check if page has restricted content indicators
                restricted_keywords = ['请登录', '登录后', '需要登录', '请先登录',
                                       'Please login', 'Please sign in', 
                                       '需要权限', '无权限访问']
                content = await page.content()
                if any(keyword in content for keyword in restricted_keywords):
                    return "NEED_LOGIN"
                
                return "PUBLIC"
                
        except Exception as e:
            if verbose:
                print(f"Error: {e}")
            return f"ERROR: {e}"
        finally:
            await context.close()
            await browser.close()


def main():
    parser = argparse.ArgumentParser(description='Detect if website requires login')
    parser.add_argument('url', help='Website URL to check')
    parser.add_argument('--timeout', type=int, default=10, help='Page load timeout (seconds)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    result = asyncio.run(detect_login_state(args.url, args.timeout, args.verbose))
    print(result)
    
    # Return appropriate exit code
    if result == "NEED_LOGIN":
        return 1
    elif result == "LOGGED_IN":
        return 0
    elif result == "PUBLIC":
        return 0
    else:
        return 2


if __name__ == '__main__':
    sys.exit(main())
