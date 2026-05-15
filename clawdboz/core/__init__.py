"""
Core Business Layer - 核心业务层

提供 Bot 核心实现和多 Bot 管理功能。
"""

from .bot_base import BotBase
from .bot import LarkBot
from .bot_manager import BotManager

# SimpleBot 需要延迟导入，避免循环依赖
def __getattr__(name):
    if name == 'Bot':
        from .simple_bot import Bot
        return Bot
    raise AttributeError(f"module 'clawdboz.core' has no attribute '{name}'")

__all__ = [
    'BotBase',
    'LarkBot',
    'BotManager',
    'Bot',  # 简化 API
]
