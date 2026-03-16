#!/usr/bin/env python3
"""
启动 Web 聊天服务器
"""

import os
import sys

# 添加项目根目录到路径
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from clawdboz.web import start_web_chat

if __name__ == "__main__":
    # 创建一个空的 bots 字典（仅用于测试）
    bots = {}
    
    # 启动 Web 服务器
    print("[WebServer] 启动 Web 聊天服务器...")
    print("[WebServer] 端口: 8080")
    print("[WebServer] Token: clawdboz-test-2024")
    
    try:
        from clawdboz.web import WebChatServer
        server = WebChatServer(
            bots=bots,
            port=8080,
            auth_token='clawdboz-test-2024',
            base_workplace='WORKPLACE'
        )
        server.run(blocking=True)  # 阻塞模式保持运行
    except KeyboardInterrupt:
        print("\n[WebServer] 正在关闭...")
