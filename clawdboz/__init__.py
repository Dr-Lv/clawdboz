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
    __version__ = '2.6.9'

from .config import PROJECT_ROOT, CONFIG, get_project_root, load_config, get_absolute_path
from .acp_client import ACPClient
from .bot import LarkBot
from .handlers import (
    do_card_action_trigger,
    do_url_preview_get,
    do_bot_p2p_chat_entered,
    do_bot_p2p_chat_create,
    do_message_read,
)
from .main import main

# 导出新的内核管理模块
from .kernel_manager import (
    Kernel,
    KernelConfig,
    KernelInfo,
    KernelManager,
    KernelRegistry,
    KernelType,
    get_default_kernel_manager,
)
from .kernel_commands import KernelCommandHandler, create_kernel_commands

# 导出 Claude Code 配置模块
from .claude_config import (
    ClaudeCodeConfig,
    ClaudeCodeConfigurator,
    setup_dashscope_claude,
)

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
    'do_bot_p2p_chat_create',
    'do_message_read',
    'main',
    # 新的内核管理模块
    'Kernel',
    'KernelConfig',
    'KernelInfo',
    'KernelManager',
    'KernelRegistry',
    'KernelType',
    'get_default_kernel_manager',
    'KernelCommandHandler',
    'create_kernel_commands',
    # Claude Code 配置模块
    'ClaudeCodeConfig',
    'ClaudeCodeConfigurator',
    'setup_dashscope_claude',
]
