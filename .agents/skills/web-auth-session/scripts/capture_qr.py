#!/usr/bin/env python3
"""
Capture QR code screenshot from a website's login page.
"""

import argparse
import asyncio
import os
from urllib.parse import urlparse

from playwright.async_api import async_playwright


# Common QR code selectors
QR_SELECTORS = [
    'canvas[class*="qr"]',
    'canvas[class*="QR"]',
    'img[class*="qr"]',
    'img[class*="QR"]',
    'img[src*="qr"]',
    'img[src*="QR"]',
    '[class*="qr-code"]',
    '[class*="qrcode"]',
    '[class*="QRCode"]',
    '.login-qr',
    '.scan-qr',
    '#qrcode',
    '#qr-code',
    # Specific platform selectors
    '[class*="login_qrcode"]',
    '[class*="login-qrcode"]',
]


async def capture_qr(url: str, output_path: str, wait_time: int = 10, verbose: bool = False):
    """
    Navigate to URL and capture QR code screenshot.
    
    Args:
        url: Website URL
        output_path: Path to save screenshot
        wait_time: Time to wait for QR code to load (seconds)
        verbose: Print verbose output
    """
    async with async_playwright() as p:
        browser = await p.chromium.launch(headless=True)
        context = await browser.new_context(
            viewport={'width': 1920, 'height': 1080},
            user_agent='Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36'
        )
        page = await context.new_page()
        
        try:
            if verbose:
                print(f"Navigating to {url}...")
            
            # Navigate to page
            await page.goto(url, wait_until='networkidle', timeout=30000)
            
            # Wait for initial load
            await page.wait_for_timeout(2000)
            
            # Look for login/QR buttons and click if needed
            login_button_selectors = [
                'button:has-text("登录")',
                'button:has-text("扫码登录")',
                'button:has-text("Log in")',
                'a:has-text("登录")',
                '[class*="login-btn"]',
                '[class*="login_button"]',
            ]
            
            for selector in login_button_selectors:
                try:
                    button = await page.query_selector(selector)
                    if button:
                        if verbose:
                            print(f"Clicking login button: {selector}")
                        await button.click()
                        await page.wait_for_timeout(2000)
                        break
                except:
                    continue
            
            # Look for QR tab/button and click
            qr_tab_selectors = [
                'text=扫码登录',
                'text=QR Code',
                'text=二维码',
                '[class*="qr-tab"]',
                '[class*="scan-tab"]',
            ]
            
            for selector in qr_tab_selectors:
                try:
                    tab = await page.query_selector(selector)
                    if tab:
                        if verbose:
                            print(f"Clicking QR tab: {selector}")
                        await tab.click()
                        await page.wait_for_timeout(2000)
                        break
                except:
                    continue
            
            # Wait for QR code to appear
            if verbose:
                print(f"Waiting {wait_time}s for QR code to load...")
            
            qr_element = None
            for _ in range(wait_time):
                for selector in QR_SELECTORS:
                    try:
                        element = await page.query_selector(selector)
                        if element:
                            # Verify element is visible and has size
                            box = await element.bounding_box()
                            if box and box['width'] > 50 and box['height'] > 50:
                                qr_element = element
                                if verbose:
                                    print(f"QR code found: {selector}")
                                break
                    except:
                        continue
                
                if qr_element:
                    break
                
                await page.wait_for_timeout(1000)
            
            if not qr_element:
                # Fallback: take full page screenshot
                if verbose:
                    print("QR code not found, taking full page screenshot")
                await page.screenshot(path=output_path, full_page=False)
                print(f"Screenshot saved to {output_path}")
                return True
            
            # Take screenshot of QR element with padding
            box = await qr_element.bounding_box()
            if box:
                # Add padding around QR code
                padding = 50
                screenshot_box = {
                    'x': max(0, box['x'] - padding),
                    'y': max(0, box['y'] - padding),
                    'width': box['width'] + (padding * 2),
                    'height': box['height'] + (padding * 2),
                }
                
                await page.screenshot(path=output_path, clip=screenshot_box)
                if verbose:
                    print(f"QR code screenshot saved: {output_path}")
                print(f"Screenshot saved to {output_path}")
                return True
            else:
                # Fallback to element screenshot
                await qr_element.screenshot(path=output_path)
                print(f"Screenshot saved to {output_path}")
                return True
                
        except Exception as e:
            print(f"ERROR: {e}")
            return False
        finally:
            await context.close()
            await browser.close()


def main():
    parser = argparse.ArgumentParser(description='Capture QR code from website')
    parser.add_argument('url', help='Website URL')
    parser.add_argument('--output', '-o', default='qr_code.png', help='Output screenshot path')
    parser.add_argument('--wait', '-w', type=int, default=10, help='Wait time for QR to load (seconds)')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    # Create output directory if needed
    output_dir = os.path.dirname(args.output)
    if output_dir and not os.path.exists(output_dir):
        os.makedirs(output_dir)
    
    success = asyncio.run(capture_qr(args.url, args.output, args.wait, args.verbose))
    
    return 0 if success else 1


if __name__ == '__main__':
    exit(main())
