#!/usr/bin/env python3
"""
小红书登录状态保存脚本
运行后手动登录，登录状态会自动保存
"""

from pathlib import Path
from playwright.sync_api import sync_playwright

# 登录状态文件路径
SCRIPT_DIR = Path(__file__).parent.absolute()
STORAGE_PATH = SCRIPT_DIR.parent / "storage_state.json"

with sync_playwright() as p:
    browser = p.chromium.launch(headless=False)
    context = browser.new_context(viewport={'width': 1280, 'height': 800})
    page = context.new_page()
    
    print("正在打开小红书...")
    page.goto("https://www.xiaohongshu.com")
    
    print("\n请完成登录（扫码或手机号）")
    print("登录成功后按 Enter 键保存登录状态...")
    
    input()  # 等待用户按回车
    
    # 保存登录状态
    context.storage_state(path=str(STORAGE_PATH))
    print(f"✅ 登录状态已保存到: {STORAGE_PATH}")
    
    browser.close()
