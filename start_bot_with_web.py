#!/usr/bin/env python3
"""
同时启动飞书 Bot 和 Web 界面
"""
import os
import sys
import subprocess
import time
import signal

def start_services():
    """启动 Bot 和 Web 服务"""
    
    # 设置环境变量
    os.environ['FEISHU_APP_ID'] = 'cli_a93c287fc2f9dbd6'
    os.environ['FEISHU_APP_SECRET'] = 'ee74qJIDFO3rHED9VhFcighyjlgKPJSF'
    
    print("="*60)
    print("启动 Clawdboz Bot + Web 服务")
    print("="*60)
    
    # 1. 先启动飞书 Bot
    print("\n[1] 启动飞书 Bot...")
    bot_process = subprocess.Popen(
        [sys.executable, 'bot0.py'],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        cwd='/Users/tomlee/code/github/clawdboz'
    )
    
    # 等待 Bot 启动
    time.sleep(2)
    
    # 检查 Bot 是否成功启动
    if bot_process.poll() is not None:
        print("[错误] Bot 启动失败!")
        stdout, stderr = bot_process.communicate()
        print(stderr.decode())
        return
    
    print("    ✓ 飞书 Bot 已启动 (PID: %d)" % bot_process.pid)
    
    # 2. 启动 Web 服务器
    print("\n[2] 启动 Web 服务器...")
    
    # 使用 demo_web_chat.py 的方式启动 Web
    sys.path.insert(0, '/Users/tomlee/code/github/clawdboz')
    
    from clawdboz.bot_manager import BotManager
    from clawdboz.web import start_web_chat
    
    project_root = '/Users/tomlee/code/github/clawdboz'
    workplace = os.path.join(project_root, "WORKPLACE")
    
    try:
        manager = BotManager(base_workplace=workplace)
        
        # 注册一个 Bot（使用当前配置的凭证）
        bot = manager.register(
            "feishu-bot",
            "cli_a93c287fc2f9dbd6",
            "ee74qJIDFO3rHED9VhFcighyjlgKPJSF",
            system_prompt="你是嗑唠的宝子，一个友好的飞书机器人助手"
        )
        print("    ✓ Bot 已注册到 Web 管理器")
        
        # 启动 Web 服务
        print("\n[3] 启动 Web 界面...")
        server = start_web_chat(
            manager.bots,
            port=8080,
            auth_token="clawdboz-test-2024",
            base_workplace=workplace
        )
        
    except Exception as e:
        print(f"    ✗ Web 服务器启动失败: {e}")
        bot_process.terminate()
        return
    
    print("\n" + "="*60)
    print("所有服务已启动!")
    print("="*60)
    print(f"\n飞书 Bot: 运行中 (PID: {bot_process.pid})")
    print(f"Web 界面: http://localhost:8080/static/index.html?token=clawdboz-test-2024")
    print("\n按 Ctrl+C 停止所有服务")
    print("="*60)
    
    # 等待中断
    try:
        while True:
            time.sleep(1)
            # 检查 Bot 是否还在运行
            if bot_process.poll() is not None:
                print("\n[警告] Bot 进程已退出")
                break
    except KeyboardInterrupt:
        print("\n\n正在停止服务...")
    finally:
        # 清理
        bot_process.terminate()
        try:
            bot_process.wait(timeout=5)
        except:
            bot_process.kill()
        print("✓ 所有服务已停止")

if __name__ == "__main__":
    start_services()
