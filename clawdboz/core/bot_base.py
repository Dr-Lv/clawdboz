#!/usr/bin/env python3
"""
Bot 基类模块

提供 Bot 的公共功能，消除 LarkBot 和 Bot 的重复代码
"""
import os
from abc import ABC, abstractmethod
from typing import Optional, Dict, Any

from ..utils.logger import Logger
from ..communication import HistoryManager


class BotBase(ABC):
    """Bot 基类"""

    def __init__(self, app_id: str, app_secret: str,
                 workplace_dir: str = "WORKPLACE"):
        """
        初始化 Bot

        Args:
            app_id: 飞书应用 ID
            app_secret: 飞书应用密钥
            workplace_dir: 工作目录路径
        """
        self.app_id = app_id
        self.app_secret = app_secret
        self.workplace_dir = os.path.abspath(workplace_dir)

        # 日志文件路径
        self.log_file = os.path.join(
            self.workplace_dir,
            "logs",
            "bot_debug.log"
        )

        # 确保日志目录存在
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)

        # 初始化历史记录管理器
        self.history_manager = HistoryManager(self.workplace_dir)

        # Bot 元数据
        self._bot_id: Optional[str] = None
        self._system_prompt: Optional[str] = None
        self.name: str = "Bot"

    def _log(self, message: str):
        """
        记录日志（使用统一的 Logger）

        Args:
            message: 日志消息
        """
        Logger.log(message, self.log_file)

    def _log_info(self, message: str):
        """记录信息级别日志"""
        Logger.info(message, self.log_file)

    def _log_warning(self, message: str):
        """记录警告级别日志"""
        Logger.warning(message, self.log_file)

    def _log_error(self, message: str):
        """记录错误级别日志"""
        Logger.error(message, self.log_file)

    def _log_debug(self, message: str):
        """记录调试级别日志"""
        Logger.debug(message, self.log_file)

    def save_message_to_history(self, chat_id: str, sender: str,
                               content: str, is_group: bool = False):
        """
        保存消息到历史记录（使用统一的历史管理器）

        Args:
            chat_id: 会话 ID
            sender: 发送者
            content: 消息内容
            is_group: 是否是群聊
        """
        bot_id = self._bot_id if not is_group else None
        self.history_manager.save_message(
            chat_id, sender, content,
            is_group=is_group,
            bot_id=bot_id
        )

    def get_chat_history(self, chat_id: str, is_group: bool = False,
                        limit: int = 30) -> list:
        """
        获取聊天历史（使用统一的历史管理器）

        Args:
            chat_id: 会话 ID
            is_group: 是否是群聊
            limit: 最大返回条数

        Returns:
            消息列表
        """
        bot_id = self._bot_id if not is_group else None
        return self.history_manager.get_history(
            chat_id,
            is_group=is_group,
            bot_id=bot_id,
            limit=limit
        )

    def get_history_path(self, chat_id: str, is_group: bool = False) -> str:
        """
        获取历史文件路径（使用统一的历史管理器）

        Args:
            chat_id: 会话 ID
            is_group: 是否是群聊

        Returns:
            历史文件路径
        """
        return self.history_manager.get_history_path(
            chat_id,
            is_group=is_group,
            bot_id=self._bot_id
        )

    @abstractmethod
    def send_message(self, chat_id: str, message: str) -> bool:
        """
        发送消息（抽象方法，子类实现）

        Args:
            chat_id: 会话 ID
            message: 消息内容

        Returns:
            是否发送成功
        """
        pass

    @abstractmethod
    def send_message_card(self, chat_id: str, title: str,
                         content: str) -> bool:
        """
        发送消息卡片（抽象方法，子类实现）

        Args:
            chat_id: 会话 ID
            title: 标题
            content: 内容

        Returns:
            是否发送成功
        """
        pass

    def get_bot_id(self) -> Optional[str]:
        """获取 Bot ID"""
        return self._bot_id

    def set_bot_id(self, bot_id: str):
        """设置 Bot ID"""
        self._bot_id = bot_id

    def get_system_prompt(self) -> Optional[str]:
        """获取系统提示词"""
        return self._system_prompt

    def set_system_prompt(self, prompt: str):
        """设置系统提示词"""
        self._system_prompt = prompt
