"""
clawdboz - 嗑唠的宝子 (Clawdboz) 飞书 Bot
基于 Kimi Code CLI 的智能飞书机器人

快速开始:
    from clawdboz import Bot
    bot = Bot(app_id="your_app_id", app_secret="your_app_secret")
    bot.run()
"""

import os

# 读取版本号
try:
    _version_file = os.path.join(os.path.dirname(__file__), 'VERSION')
    with open(_version_file, 'r') as f:
        __version__ = f.read().strip()
except Exception:
    __version__ = '5.0.0'

from .config import PROJECT_ROOT, CONFIG, get_project_root, load_config, get_absolute_path

# 沙箱容器中跳过重型依赖导入
if os.environ.get("CLAWDBOZ_SANDBOX_MODE") == "1":
    LarkBot = Bot = BotManager = None
    ACPClient = HistoryManager = SessionManager = None
    do_card_action_trigger = do_url_preview_get = do_bot_p2p_chat_entered = do_bot_p2p_chat_create = do_message_read = None
    main = None
else:
    from .core import LarkBot, Bot, BotManager
    from .communication import ACPClient, HistoryManager, SessionManager
    from .handlers import (
        do_card_action_trigger,
        do_url_preview_get,
        do_bot_p2p_chat_entered,
        do_bot_p2p_chat_create,
        do_message_read,
    )
    from .main import main

# 延迟导入简化 API，避免循环依赖
def __getattr__(name):
    if name == 'Bot':
        from .simple_bot import Bot
        return Bot
    if name == 'BotManager':
        from .bot_manager import BotManager
        return BotManager
    raise AttributeError(f"module 'clawdboz' has no attribute '{name}'")

__all__ = [
    'PROJECT_ROOT',
    'CONFIG',
    'get_project_root',
    'load_config',
    'get_absolute_path',
    'ACPClient',
    'LarkBot',
    'BotManager',
    'Bot',  # 简化 API
    'HistoryManager',
    'SessionManager',
    'do_card_action_trigger',
    'do_url_preview_get',
    'do_bot_p2p_chat_entered',
    'do_bot_p2p_chat_create',
    'do_message_read',
    'main',
]
