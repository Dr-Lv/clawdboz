#!/usr/bin/env python3
"""
CLI 查看 Bot 回复日志
用法: python cli_tail.py [行数，默认 20]
"""

import sys
import subprocess
import os

def main():
    lines = int(sys.argv[1]) if len(sys.argv) > 1 else 20
    
    # 找到最近的 bot 日志
    log_file = None
    possible_paths = [
        '/Users/tomlee/code/github/test/test_auto_create/logs/bot_debug.log',
        'logs/bot_debug.log',
        '../test/test_auto_create/logs/bot_debug.log'
    ]
    
    for path in possible_paths:
        if os.path.exists(path):
            log_file = path
            break
    
    if not log_file:
        print("❌ 未找到 Bot 日志文件")
        sys.exit(1)
    
    print(f"📋 查看 Bot 日志 ({log_file}) 最后 {lines} 行:")
    print("=" * 60)
    
    try:
        # 使用 tail 命令
        result = subprocess.run(['tail', '-n', str(lines), log_file], 
                              capture_output=True, text=True)
        print(result.stdout)
    except Exception as e:
        print(f"❌ 错误: {e}")

if __name__ == "__main__":
    main()
