#!/usr/bin/env python3
"""
独立启动 Web 服务器
"""
import os
import sys

sys.path.insert(0, '/Users/tomlee/code/github/clawdboz')

from clawdboz.bot_manager import BotManager
from clawdboz.web import start_web_chat

project_root = '/Users/tomlee/code/github/clawdboz'
workplace = os.path.join(project_root, "WORKPLACE")

print("="*60)
print("启动 Web Chat 服务器")
print("="*60)

manager = BotManager(base_workplace=workplace)

# 注册 Bot 1: 嗑唠的宝子（通用助手）
bot1 = manager.register(
    "feishu-bot",
    "cli_a93c287fc2f9dbd6",
    "ee74qJIDFO3rHED9VhFcighyjlgKPJSF",
    system_prompt="你是嗑唠的宝子，一个友好的飞书机器人助手"
)
print("✓ Bot 1: feishu-bot (嗑唠的宝子) 已注册")

# 注册 Bot 2: 代码助手
bot2 = manager.register(
    "code-assistant",
    "cli_a93c287fc2f9dbd6",
    "ee74qJIDFO3rHED9VhFcighyjlgKPJSF",
    system_prompt="你是代码助手，擅长编程、代码审查、技术方案设计。你可以帮助用户编写、优化和调试代码，支持多种编程语言。"
)
print("✓ Bot 2: code-assistant (代码助手) 已注册")

# 注册 Bot 3: 文档助手
bot3 = manager.register(
    "doc-writer",
    "cli_a93c287fc2f9dbd6",
    "ee74qJIDFO3rHED9VhFcighyjlgKPJSF",
    system_prompt="你是文档助手，擅长写作、文档整理、内容创作。你可以帮助用户撰写技术文档、产品说明、会议纪要等各种文本内容。"
)
print("✓ Bot 3: doc-writer (文档助手) 已注册")

# 启动 Web 服务（阻塞模式，保持运行）
from clawdboz.web.server import WebChatServer
server = WebChatServer(
    manager.bots,
    port=8080,
    auth_token="clawdboz-test-2024",
    base_workplace=workplace
)
server.run(blocking=True)
