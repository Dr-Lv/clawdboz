#!/usr/bin/env python3
"""
小红书手动发布辅助脚本
只打开浏览器和发布页面，用户手动完成发布
"""

import json
import time
from pathlib import Path
from playwright.sync_api import sync_playwright

SCRIPT_DIR = Path(__file__).parent.absolute()
STORAGE_PATH = SCRIPT_DIR.parent / "storage_state.json"


def main():
    print("=" * 50)
    print("小红书手动发布助手")
    print("=" * 50)
    
    # 读取内容配置
    content_path = SCRIPT_DIR.parent / "assets" / "post_template" / "content.json"
    try:
        with open(content_path, 'r', encoding='utf-8') as f:
            content = json.load(f)
        print(f"\n标题: {content['title']}")
        print(f"图片: {content['images']}")
        print(f"\n正文预览:\n{content['content'][:200]}...")
        if 'topics' in content:
            print(f"\n话题标签: {' '.join(['#' + t for t in content['topics']])}")
    except Exception as e:
        print(f"读取内容配置失败: {e}")
    
    print("\n" + "=" * 50)
    print("正在打开浏览器...")
    print("=" * 50)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        
        # 加载登录状态
        storage_state = str(STORAGE_PATH) if STORAGE_PATH.exists() else None
        context = browser.new_context(
            storage_state=storage_state,
            viewport={'width': 1400, 'height': 900}
        )
        
        page = context.new_page()
        
        # 打开小红书创作平台发布页面
        print("正在进入小红书发布页面...")
        page.goto("https://creator.xiaohongshu.com/publish/publish")
        
        # 等待页面加载
        page.wait_for_timeout(3000)
        
        # 检查是否需要登录
        if "login" in page.url:
            print("\n⚠️ 请先完成登录")
            print("登录完成后请按 Enter 键继续...")
            input()
            # 保存登录状态
            context.storage_state(path=str(STORAGE_PATH))
            print(f"✅ 登录状态已保存")
        else:
            print("✅ 已登录状态")
        
        print("\n" + "=" * 50)
        print("浏览器已打开，请手动完成发布：")
        print("=" * 50)
        print("1. 点击'上传图文'")
        print(f"2. 选择图片文件夹: {SCRIPT_DIR.parent / 'assets' / 'post_template' / 'images'}")
        print("3. 填写标题和正文")
        print("4. 添加话题标签")
        print("5. 点击发布")
        print("\n操作完成后关闭浏览器即可")
        print("=" * 50)
        
        # 保持浏览器打开直到用户关闭
        try:
            while True:
                time.sleep(1)
                # 检查浏览器是否关闭
                try:
                    page.title()
                except:
                    break
        except KeyboardInterrupt:
            pass
        
        browser.close()
        print("\n✅ 浏览器已关闭")


if __name__ == "__main__":
    main()
