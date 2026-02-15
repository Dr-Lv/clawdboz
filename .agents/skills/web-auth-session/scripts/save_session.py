#!/usr/bin/env python3
"""
Save complete login session state including cookies, localStorage, and sessionStorage.

Output file: assets/<site_name>_status.json
"""

import argparse
import asyncio
import json
import os
from datetime import datetime
from urllib.parse import urlparse

from playwright.async_api import async_playwright


async def get_all_storage_data(page, domain: str) -> dict:
    """
    Extract all storage data from the page.
    
    Returns:
        dict with cookies, localStorage, sessionStorage, indexedDB
    """
    # Get cookies
    cookies = await page.context.cookies()
    
    # Get localStorage
    local_storage = await page.evaluate('''() => {
        const items = {};
        for (let i = 0; i < localStorage.length; i++) {
            const key = localStorage.key(i);
            items[key] = localStorage.getItem(key);
        }
        return items;
    }''')
    
    # Get sessionStorage
    session_storage = await page.evaluate('''() => {
        const items = {};
        for (let i = 0; i < sessionStorage.length; i++) {
            const key = sessionStorage.key(i);
            items[key] = sessionStorage.getItem(key);
        }
        return items;
    }''')
    
    # Try to get IndexedDB (basic support)
    indexed_db = await page.evaluate('''() => {
        return new Promise((resolve) => {
            try {
                const databases = [];
                const request = indexedDB.open('_check_databases');
                request.onsuccess = () => {
                    request.result.close();
                    resolve({status: 'checked', note: 'IndexedDB access requires manual handling'});
                };
                request.onerror = () => {
                    resolve({status: 'error', message: 'Could not access IndexedDB'});
                };
            } catch (e) {
                resolve({status: 'error', message: e.toString()});
            }
        });
    }''')
    
    return {
        'cookies': cookies,
        'localStorage': local_storage,
        'sessionStorage': session_storage,
        'indexedDB': indexed_db,
    }


async def save_session(url: str, site_name: str, wait_time: int = 5, 
                       assets_dir: str = 'assets', verbose: bool = False) -> bool:
    """
    Save complete login session.
    
    Args:
        url: Website URL
        site_name: Name for the session file
        wait_time: Time to wait after page load
        assets_dir: Directory to save session file
        verbose: Print verbose output
    
    Returns:
        True if successful
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
            
            # Wait for user to be fully logged in
            if verbose:
                print(f"Waiting {wait_time}s for session to stabilize...")
            await page.wait_for_timeout(wait_time * 1000)
            
            # Get domain
            parsed = urlparse(page.url)
            domain = parsed.netloc
            
            # Get all storage data
            if verbose:
                print("Extracting session data...")
            
            storage_data = await get_all_storage_data(page, domain)
            
            # Prepare session data
            session_data = {
                'metadata': {
                    'url': url,
                    'saved_at': datetime.now().isoformat(),
                    'domain': domain,
                    'site_name': site_name,
                },
                **storage_data
            }
            
            # Create assets directory if needed
            if not os.path.exists(assets_dir):
                os.makedirs(assets_dir)
                if verbose:
                    print(f"Created directory: {assets_dir}")
            
            # Save to file
            output_file = os.path.join(assets_dir, f"{site_name}_status.json")
            with open(output_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, indent=2, ensure_ascii=False)
            
            if verbose:
                print(f"Session saved to {output_file}")
                print(f"  - Cookies: {len(storage_data['cookies'])}")
                print(f"  - localStorage items: {len(storage_data['localStorage'])}")
                print(f"  - sessionStorage items: {len(storage_data['sessionStorage'])}")
            
            print(f"Session saved to {output_file}")
            return True
            
        except Exception as e:
            print(f"ERROR: {e}")
            return False
        finally:
            await context.close()
            await browser.close()


def main():
    parser = argparse.ArgumentParser(description='Save website login session')
    parser.add_argument('url', help='Website URL')
    parser.add_argument('--name', '-n', required=True, help='Site name for session file')
    parser.add_argument('--wait', '-w', type=int, default=5, 
                        help='Wait time after page load (seconds)')
    parser.add_argument('--assets-dir', '-a', default='assets', 
                        help='Directory to save session files')
    parser.add_argument('--verbose', '-v', action='store_true', help='Verbose output')
    
    args = parser.parse_args()
    
    success = asyncio.run(save_session(
        args.url, args.name, args.wait, args.assets_dir, args.verbose
    ))
    
    return 0 if success else 1


if __name__ == '__main__':
    exit(main())
