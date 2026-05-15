"""
Communication Layer - 通信层

提供 AI 对话、会话管理和历史记录功能。
"""

from .acp_client import ACPClient
from .history import HistoryManager
from .session_manager import SessionManager, Session

__all__ = [
    'ACPClient',
    'HistoryManager',
    'SessionManager',
    'Session',
]
