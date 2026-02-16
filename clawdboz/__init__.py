"""
clawdboz - 嗑唠的宝子 (Clawdboz) 飞书 Bot
基于 Kimi Code CLI 的智能飞书机器人

快速开始:
    from clawdboz import Bot
    bot = Bot(app_id="your_app_id", app_secret="your_app_secret")
    bot.run()
"""

from .config import PROJECT_ROOT, CONFIG, get_project_root, load_config, get_absolute_path
from .acp_client import ACPClient
from .bot import LarkBot
from .handlers import (
    do_card_action_trigger,
    do_url_preview_get,
    do_bot_p2p_chat_entered,
    do_message_read,
)
from .main import main

# 延迟导入简化 API，避免循环依赖
def __getattr__(name):
    if name == 'Bot':
        from .simple_bot import Bot
        return Bot
    raise AttributeError(f"module 'clawdboz' has no attribute '{name}'")

__all__ = [
    'PROJECT_ROOT',
    'CONFIG',
    'get_project_root',
    'load_config',
    'get_absolute_path',
    'ACPClient',
    'LarkBot',
    'Bot',  # 简化 API
    'do_card_action_trigger',
    'do_url_preview_get',
    'do_bot_p2p_chat_entered',
    'do_message_read',
    'main',
]
