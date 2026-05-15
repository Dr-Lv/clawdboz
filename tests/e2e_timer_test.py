#!/usr/bin/env python3
"""
定时任务端到端测试脚本
按照 test_plan.md 执行测试流程
"""

import time
import sys
import subprocess
from playwright.sync_api import sync_playwright

MAX_RETRIES = 3
RETRY_DELAY = 5


def debug_check():
    """执行 debug 检查和修复"""
    print("\n🔧 开始 Debug 流程...")
    
    # Debug 1: 检查任务文件
    print("\n1. 检查 scheduler_tasks.json...")
    result = subprocess.run(
        ["find", "/Users/suntom/code/github/clawdboz/WORKPLACE/workplace_doc-writer", 
         "-name", "scheduler_tasks.json"],
        capture_output=True, text=True
    )
    print(f"   找到任务文件: {result.stdout.strip()}")
    
    # Debug 2: 检查 Kimi 登录状态
    print("\n2. 检查 Kimi 登录状态...")
    result = subprocess.run(["kimi", "info"], capture_output=True, text=True)
    if "version" in result.stdout:
        print("   ✅ Kimi 已登录")
    else:
        print("   ❌ Kimi 未登录，需要重新登录")
        print("   请运行: kimi login")
        return False
    
    # Debug 3: 检查服务状态
    print("\n3. 检查 Web Server 状态...")
    result = subprocess.run(
        ["curl", "-k", "-s", 
         "https://localhost:8443/api/sessions?token=clawdboz-test-2024"],
        capture_output=True, text=True
    )
    if result.returncode == 0 and "sessions" in result.stdout:
        print("   ✅ Web Server 正常运行")
    else:
        print("   ❌ Web Server 未响应，尝试重启...")
        subprocess.run(["pkill", "-f", "python.*web_server"])
        time.sleep(2)
        subprocess.Popen(
            ["python3", "web_server.py", "--port", "8443", "--https"],
            cwd="/Users/suntom/code/github/clawdboz",
            stdout=subprocess.DEVNULL,
            stderr=subprocess.DEVNULL
        )
        time.sleep(5)
    
    print("\n✅ Debug 完成")
    return True


def run_test():
    """执行一次完整测试流程"""
    
    print("=" * 60)
    print("🧪 开始定时任务 E2E 测试")
    print("=" * 60)
    
    with sync_playwright() as p:
        browser = p.chromium.launch(
            headless=False, 
            args=['--ignore-certificate-errors']
        )
        context = browser.new_context(
            ignore_https_errors=True,
            viewport={'width': 1280, 'height': 800}
        )
        page = context.new_page()
        
        try:
            # Step 1: 打开浏览器
            print("\n📍 Step 1: 打开浏览器...")
            page.goto(
                "https://localhost:8443/static/index.html?token=clawdboz-test-2024",
                wait_until='networkidle'
            )
            time.sleep(2)
            page.screenshot(path='/tmp/test_step1_open.png')
            print("   ✅ 浏览器已打开")
            
            # Step 2: 新建会话 (选择 doc-writer)
            print("\n📍 Step 2: 新建会话...")
            page.click("text=doc-writer")
            time.sleep(2)
            page.screenshot(path='/tmp/test_step2_session.png')
            print("   ✅ 已选择 doc-writer 会话")
            
            # Step 3: 发送定时任务消息
            print("\n📍 Step 3: 发送定时任务消息...")
            message = "1分钟后发我个消息，内容是1"
            page.fill('textarea', message)
            time.sleep(0.5)
            page.keyboard.press('Enter')
            print(f"   已发送: {message}")
            
            # 等待 AI 响应
            print("   等待 AI 响应 (15秒)...")
            time.sleep(15)
            
            # 滚动到底部
            page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            time.sleep(1)
            page.screenshot(path='/tmp/test_step3_response.png')
            
            # 检查任务是否创建成功
            text = page.inner_text('body')
            if "定时任务" in text and ("创建" in text or "成功" in text):
                print("   ✅ 定时任务创建成功")
            else:
                print("   ⚠️ 未看到任务创建确认，继续执行")
            
            # Step 4: 等待并验证定时消息
            print("\n📍 Step 4: 等待并验证定时消息...")
            print("   ⏰ 等待 70 秒...")
            time.sleep(70)
            
            # 滚动到底部查看最新消息
            page.evaluate('window.scrollTo(0, document.body.scrollHeight)')
            time.sleep(1)
            page.screenshot(path='/tmp/test_step4_check.png')
            
            # 检查是否收到定时消息
            text = page.inner_text('body')
            
            # 成功判断：检查是否收到 Bot 发送的包含 "1" 的新消息
            # 获取页面上的所有消息
            lines = [l.strip() for l in text.split('\n') if l.strip()]
            
            # 查找包含 "1" 且前面有 doc-writer 或时间戳的消息
            for i, line in enumerate(lines):
                if line == "1" and i > 0:
                    # 检查前面几行是否有 doc-writer 或机器人标识
                    context = ' '.join(lines[max(0, i-5):i])
                    if any(keyword in context for keyword in ["doc-writer", "机器人", "code-assistant"]):
                        print("   ✅ 收到定时消息！")
                        print(f"   消息内容: '{line}'")
                        return True
            
            # 备选方案：检查是否有新消息（通过消息数量或内容判断）
            # 如果页面包含 "定时任务执行" 或特定标识
            if "定时任务执行成功" in text or "⏰" in text:
                print("   ✅ 检测到定时任务执行标记")
                return True
            
            print("   ❌ 未找到定时消息 '1'")
            print(f"   页面内容片段: {text[-200:]}")
            return False
                
        except Exception as e:
            print(f"   ❌ 测试执行异常: {e}")
            return False
        finally:
            browser.close()


def main():
    """主函数：循环执行测试直到成功或达到最大重试次数"""
    
    for attempt in range(1, MAX_RETRIES + 1):
        print(f"\n{'='*60}")
        print(f"🔄 第 {attempt}/{MAX_RETRIES} 次测试尝试")
        print('='*60)
        
        # 执行测试
        success = run_test()
        
        if success:
            print("\n" + "="*60)
            print("🎉 测试通过！")
            print("="*60)
            return 0
        
        # 测试失败，执行 debug
        if attempt < MAX_RETRIES:
            print(f"\n⚠️ 测试失败，{RETRY_DELAY}秒后开始 Debug...")
            time.sleep(RETRY_DELAY)
            
            if not debug_check():
                print("❌ Debug 修复失败，需要手动干预")
                return 1
            
            print(f"\n🔄 Debug 完成，准备第 {attempt + 1} 次测试...")
            time.sleep(2)
    
    # 所有重试都失败
    print("\n" + "="*60)
    print(f"❌ 测试失败！已重试 {MAX_RETRIES} 次")
    print("="*60)
    print("\n建议:")
    print("1. 手动检查日志: tail -100 /tmp/web_server.log")
    print("2. 检查 Kimi 状态: kimi info")
    print("3. 重启服务后重试")
    return 1


if __name__ == "__main__":
    sys.exit(main())
