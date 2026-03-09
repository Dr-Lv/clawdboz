#!/usr/bin/env python3
"""
Bot CLI 启动器 - 启动 Bot 并启用本地 CLI 接口

用法:
    python bot_cli.py              # 启动 Bot + CLI
    python bot_cli.py --cli-only   # 只启动 CLI（需要 Bot 已运行）
    python bot_cli.py --chat       # 直接启动交互式聊天
"""

import os
import sys
import argparse

# 获取项目目录
SCRIPT_DIR = os.path.dirname(os.path.abspath(__file__))
os.chdir(SCRIPT_DIR)

def start_bot_with_cli():
    """启动 Bot 并启用 CLI"""
    from clawdboz import Bot
    
    print("=" * 60)
    print("🤖 启动 Bot 并启用 CLI 接口")
    print("=" * 60)
    print()
    
    bot = Bot()
    
    # 使用非阻塞模式启动，以便我们可以进行交互
    bot.run(blocking=False, enable_cli=True)
    
    print()
    print("=" * 60)
    print("✅ Bot 已启动")
    print("=" * 60)
    print()
    
    return bot


def start_cli_client():
    """启动 CLI 客户端"""
    from clawdboz.cli_client import CLIClient
    
    client = CLIClient()
    client.interactive_mode()


def main():
    parser = argparse.ArgumentParser(description='Bot CLI 启动器')
    parser.add_argument('--cli-only', action='store_true', help='只启动 CLI 客户端')
    parser.add_argument('--chat', '-c', action='store_true', help='启动交互式聊天')
    parser.add_argument('--status', '-s', action='store_true', help='查看 Bot 状态')
    parser.add_argument('--message', '-m', help='发送单条消息')
    
    args = parser.parse_args()
    
    if args.cli_only:
        # 只启动 CLI 客户端
        start_cli_client()
        
    elif args.chat:
        # 检查 Bot 是否已运行
        socket_path = "/tmp/bot_cli.sock"
        if not os.path.exists(socket_path):
            print("⚠️  Bot 未运行，正在启动...")
            start_bot_with_cli()
            import time
            time.sleep(2)
        
        start_cli_client()
        
    elif args.status:
        # 查看状态
        from clawdboz.cli_client import CLIClient
        client = CLIClient()
        status = client.get_status()
        print(json.dumps(status, indent=2))
        
    elif args.message:
        # 发送单条消息
        from clawdboz.cli_client import CLIClient
        client = CLIClient()
        response = client.chat(args.message)
        print(response)
        
    else:
        # 默认：启动 Bot 并进入交互模式
        start_bot_with_cli()
        
        # 等待 CLI 服务器启动
        import time
        time.sleep(1)
        
        # 启动交互式聊天
        start_cli_client()


if __name__ == '__main__':
    import json  # 导入 json 用于 --status 选项
    main()
