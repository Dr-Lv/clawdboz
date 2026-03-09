#!/usr/bin/env python3
"""
CLI 测试脚本 - 测试与 Bot 的双向通信
"""

import os
import sys
import time

# 添加到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from clawdboz.cli_client import CLIClient


def test_basic_chat():
    """测试基本聊天"""
    print("=" * 60)
    print("测试 1: 基本聊天")
    print("=" * 60)
    
    client = CLIClient()
    
    # 测试状态
    print("\n1. 获取 Bot 状态...")
    status = client.get_status()
    print(f"   状态: {status}")
    
    # 测试聊天
    print("\n2. 发送测试消息...")
    response = client.chat("你好，请简单介绍一下你自己")
    print(f"   回复: {response[:200]}...")
    
    print("\n✅ 基本聊天测试完成")


def test_interactive():
    """测试交互式聊天"""
    print("\n" + "=" * 60)
    print("测试 2: 交互式聊天")
    print("=" * 60)
    
    client = CLIClient()
    client.interactive_mode()


def main():
    """主函数"""
    import argparse
    
    parser = argparse.ArgumentParser(description='Bot CLI 测试')
    parser.add_argument('--basic', action='store_true', help='运行基本测试')
    parser.add_argument('--interactive', '-i', action='store_true', help='交互式模式')
    
    args = parser.parse_args()
    
    if args.basic:
        test_basic_chat()
    elif args.interactive:
        test_interactive()
    else:
        # 默认运行基本测试
        test_basic_chat()
        
        # 询问是否进入交互模式
        print("\n" + "=" * 60)
        user_input = input("是否进入交互式聊天模式? (y/n): ").strip().lower()
        if user_input in ('y', 'yes'):
            test_interactive()


if __name__ == '__main__':
    main()
