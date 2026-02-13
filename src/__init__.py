"""
src 包 - 嗑唠的宝子核心代码
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
