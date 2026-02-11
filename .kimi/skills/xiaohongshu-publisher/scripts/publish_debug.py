#!/usr/bin/env python3
"""
小红书发布脚本 - 调试版本（修复版）
"""

import json
import sys
import time
from pathlib import Path
from datetime import datetime

from playwright.sync_api import sync_playwright, TimeoutError as PlaywrightTimeout

SCRIPT_DIR = Path(__file__).parent.absolute()
STORAGE_PATH = SCRIPT_DIR.parent / "storage_state.json"


def log(msg):
    print(f"[{datetime.now().strftime('%H:%M:%S')}] {msg}")


def take_screenshot(page, name):
    screenshot_path = f"debug_{name}_{datetime.now().strftime('%H%M%S')}.png"
    page.screenshot(path=screenshot_path, full_page=True)
    log(f"📸 截图已保存: {screenshot_path}")
    return screenshot_path


def load_content(content_path: str) -> dict:
    with open(content_path, 'r', encoding='utf-8') as f:
        return json.load(f)


def check_images(images: list, base_path: Path) -> list:
    full_paths = []
    for img in images:
        img_path = base_path / img
        if not img_path.exists():
            raise FileNotFoundError(f"图片不存在: {img_path}")
        full_paths.append(str(img_path.absolute()))
    return full_paths


def publish(content: dict, headless: bool = False) -> bool:
    with sync_playwright() as p:
        log("启动浏览器...")
        browser = p.chromium.launch(headless=headless)
        
        storage_state = str(STORAGE_PATH) if STORAGE_PATH.exists() else None
        log(f"登录状态: {'已保存' if STORAGE_PATH.exists() else '未找到'}")
        
        context = browser.new_context(
            storage_state=storage_state,
            viewport={'width': 1400, 'height': 900}
        )
        page = context.new_page()
        
        try:
            # 直接访问创作平台发布页面
            log("=" * 50)
            log("访问小红书创作平台发布页面")
            log("=" * 50)
            
            page.goto("https://creator.xiaohongshu.com/publish/publish", wait_until="networkidle")
            page.wait_for_timeout(3000)
            log(f"当前URL: {page.url}")
            take_screenshot(page, "step1_publish_page")
            
            # 检查是否需要登录
            if "login" in page.url or page.locator('text=登录').is_visible():
                log("⚠️ 需要登录，请在浏览器中完成登录")
                input("登录完成后按 Enter 继续...")
                page.wait_for_timeout(2000)
                context.storage_state(path=str(STORAGE_PATH))
                log(f"✅ 登录状态已保存")
                page.goto("https://creator.xiaohongshu.com/publish/publish")
                page.wait_for_timeout(3000)
            
            # 关闭引导弹窗/新手教程
            log("=" * 50)
            log("检查并关闭引导弹窗")
            log("=" * 50)
            
            close_selectors = [
                'text=我知道了',
                'text=跳过',
                'text=关闭',
                '[class*="close"]',
                '[class*="skip"]',
                'button svg',  # 关闭按钮通常是 SVG 图标
                '.driver-popover .driver-close-btn',  # 常见的引导库关闭按钮
                '.introjs-skipbutton',  # intro.js 引导
            ]
            
            for selector in close_selectors:
                try:
                    close_btn = page.locator(selector).first
                    if close_btn.is_visible(timeout=1000):
                        log(f"✅ 找到引导关闭按钮: {selector}")
                        close_btn.click()
                        log("✅ 已关闭引导弹窗")
                        page.wait_for_timeout(1000)
                        break
                except:
                    continue
            else:
                log("未发现引导弹窗，继续操作")
            
            take_screenshot(page, "step1_5_after_close_guide")
            
            # 查找上传图文按钮
            log("=" * 50)
            log("点击'上传图文'")
            log("=" * 50)
            
            upload_btn = None
            selectors = [
                'text=上传图文',
                'button:has-text("上传图文")',
                '[class*="upload"]',
                'text=图文',
            ]
            
            for selector in selectors:
                try:
                    btn = page.locator(selector).first
                    if btn.is_visible():
                        log(f"✅ 找到: {selector}")
                        upload_btn = btn
                        break
                except:
                    continue
            
            if upload_btn:
                upload_btn.click()
                log("✅ 已点击上传图文")
                page.wait_for_timeout(2000)
            else:
                log("⚠️ 未找到上传图文按钮，尝试直接找文件输入框")
            
            take_screenshot(page, "step2_upload_area")
            
            # 上传图片
            log("=" * 50)
            log("上传图片")
            log("=" * 50)
            
            # 查找文件输入框
            file_input = page.locator('input[type="file"]').first
            log(f"开始上传 {len(content['images'])} 张图片...")
            
            # 设置更长的超时时间
            file_input.set_input_files(content['images'], timeout=60000)
            log("✅ 图片已选择")
            
            # 等待上传完成（观察进度）
            for i in range(10):
                page.wait_for_timeout(1000)
                log(f"等待上传... {i+1}/10")
                # 检查是否有上传进度或完成标识
                try:
                    # 如果有上传完成的标识，提前退出
                    if page.locator('text=上传完成').is_visible(timeout=500):
                        log("✅ 上传完成")
                        break
                except:
                    pass
            
            take_screenshot(page, "step3_after_upload")
            
            # 填写标题
            log("=" * 50)
            log("填写标题")
            log("=" * 50)
            
            try:
                title_input = page.locator('input[placeholder*="标题"], textarea[placeholder*="标题"]').first
                title_input.fill(content['title'])
                log(f"✅ 标题: {content['title'][:30]}...")
            except Exception as e:
                log(f"⚠️ 填写标题失败: {e}")
            
            # 填写正文
            log("=" * 50)
            log("填写正文")
            log("=" * 50)
            
            try:
                content_input = page.locator('[contenteditable="true"]').first
                full_content = content['content']
                if 'topics' in content:
                    for topic in content['topics']:
                        full_content += f" #{topic}"
                content_input.fill(full_content)
                log(f"✅ 正文已填写 ({len(full_content)} 字符)")
            except Exception as e:
                log(f"⚠️ 填写正文失败: {e}")
            
            page.wait_for_timeout(2000)
            take_screenshot(page, "step4_after_fill")
            
            # 点击发布
            log("=" * 50)
            log("点击发布")
            log("=" * 50)
            
            try:
                submit_btn = page.locator('button:has-text("发布笔记"), button:has-text("立即发布")').first
                submit_btn.click()
                log("✅ 已点击发布")
            except Exception as e:
                log(f"⚠️ 点击发布失败: {e}")
                input("请手动点击发布按钮，完成后按 Enter...")
            
            page.wait_for_timeout(5000)
            take_screenshot(page, "step5_after_submit")
            
            log("=" * 50)
            log("✅ 流程完成")
            log("=" * 50)
            
            context.storage_state(path=str(STORAGE_PATH))
            return True
            
        except Exception as e:
            log(f"❌ 错误: {e}")
            take_screenshot(page, "error")
            return False
            
        finally:
            log("关闭浏览器...")
            browser.close()


def main():
    content_path = SCRIPT_DIR.parent / "assets" / "post_template" / "content.json"
    
    try:
        content = load_content(str(content_path))
        base_path = content_path.parent
        content['images'] = check_images(content['images'], base_path / "images")
        
        log(f"标题: {content['title']}")
        log(f"图片: {content['images']}")
        
        success = publish(content, headless=False)
        sys.exit(0 if success else 1)
        
    except Exception as e:
        log(f"❌ 错误: {e}")
        sys.exit(1)


if __name__ == "__main__":
    main()
