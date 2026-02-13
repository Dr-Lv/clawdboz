#!/usr/bin/env python3
"""
嗑唠的宝子 (Clawdboz) - 飞书 Bot

此文件为兼容入口，实际代码已放到 src/ 目录：
- src/config.py: 配置管理
- src/acp_client.py: ACP 客户端
- src/bot.py: Bot 核心类
- src/handlers.py: 事件处理器
- src/main.py: 程序入口

推荐使用: python -m src.main
"""

# 确保 src 在路径中
import sys
import os
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

# 从 src 包导入所有公开接口
from src import (
    PROJECT_ROOT,
    CONFIG,
    get_project_root,
    load_config,
    get_absolute_path,
    ACPClient,
    LarkBot,
    do_card_action_trigger,
    do_url_preview_get,
    do_bot_p2p_chat_entered,
    do_message_read,
    main,
)

__all__ = [
    'PROJECT_ROOT',
    'CONFIG',
    'get_project_root',
    'load_config',
    'get_absolute_path',
    'ACPClient',
    'LarkBot',
    'do_card_action_trigger',
    'do_url_preview_get',
    'do_bot_p2p_chat_entered',
    'do_message_read',
    'main',
]

# 保持向后兼容：如果直接运行此文件，调用 main()
if __name__ == "__main__":
    main()
