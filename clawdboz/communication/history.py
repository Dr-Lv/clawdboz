#!/usr/bin/env python3
"""
统一历史记录管理模块

提供统一的历史记录保存和加载接口，替代分散在多个文件中的实现
"""
import json
import os
from typing import List, Dict, Optional, Any
from pathlib import Path


class HistoryManager:
    """统一的历史记录管理器"""

    def __init__(self, base_workplace: str = "WORKPLACE"):
        """
        初始化历史记录管理器

        Args:
            base_workplace: 基础工作目录路径
        """
        self.base_workplace = os.path.abspath(base_workplace)

    def get_history_path(self, chat_id: str, is_group: bool = False,
                        bot_id: str = None) -> str:
        """
        获取历史文件路径（统一逻辑）

        Args:
            chat_id: 会话 ID
            is_group: 是否是群聊
            bot_id: Bot ID（单聊时必需）

        Returns:
            历史文件的完整路径
        """
        if is_group:
            # 群聊：groupspace/g_{chat_id}/history.json
            return os.path.join(
                self.base_workplace,
                "groupspace",
                f"g_{chat_id}",
                "history.json"
            )
        else:
            # 单聊：workplace_{bot_id}/w_{chat_id}/history.json
            if not bot_id:
                raise ValueError("单聊必须提供 bot_id")
            return os.path.join(
                self.base_workplace,
                f"workplace_{bot_id}",
                f"w_{chat_id}",
                "history.json"
            )

    def get_meta_path(self, chat_id: str, is_group: bool = False,
                     bot_id: str = None) -> str:
        """
        获取元数据文件路径

        Args:
            chat_id: 会话 ID
            is_group: 是否是群聊
            bot_id: Bot ID（单聊时必需）

        Returns:
            元数据文件的完整路径
        """
        history_path = self.get_history_path(chat_id, is_group, bot_id)
        # history.json 和 meta.json 在同一目录
        return os.path.join(os.path.dirname(history_path), "meta.json")

    def save_message(self, chat_id: str, sender: str, content: str,
                    is_group: bool = False, bot_id: str = None,
                    message_type: str = "text") -> bool:
        """
        保存单条消息到历史记录

        Args:
            chat_id: 会话 ID
            sender: 发送者标识
            content: 消息内容
            is_group: 是否是群聊
            bot_id: Bot ID（单聊时必需）
            message_type: 消息类型

        Returns:
            是否保存成功
        """
        try:
            history_file = self.get_history_path(chat_id, is_group, bot_id)
            history_dir = os.path.dirname(history_file)
            os.makedirs(history_dir, exist_ok=True)

            # 读取现有历史
            history = []
            if os.path.exists(history_file):
                with open(history_file, 'r', encoding='utf-8') as f:
                    history = json.load(f)

            # 添加新消息
            import time
            message = {
                "sender": sender,
                "content": content,
                "type": message_type,
                "timestamp": time.time()
            }
            history.append(message)

            # 保存历史
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)

            return True
        except Exception as e:
            print(f"[HistoryManager] 保存消息失败: {e}")
            return False

    def get_history(self, chat_id: str, is_group: bool = False,
                   bot_id: str = None, limit: int = 30) -> List[Dict]:
        """
        获取历史记录

        Args:
            chat_id: 会话 ID
            is_group: 是否是群聊
            bot_id: Bot ID（单聊时必需）
            limit: 最大返回条数

        Returns:
            消息列表
        """
        try:
            history_file = self.get_history_path(chat_id, is_group, bot_id)

            if not os.path.exists(history_file):
                return []

            with open(history_file, 'r', encoding='utf-8') as f:
                history = json.load(f)

            # 返回最近的 N 条消息
            if limit and len(history) > limit:
                return history[-limit:]
            return history

        except Exception as e:
            print(f"[HistoryManager] 读取历史失败: {e}")
            return []

    def save_session_history(self, chat_id: str, messages: List[Dict],
                           is_group: bool = False, bot_id: str = None,
                           meta: Dict = None) -> bool:
        """
        保存完整会话历史（批量）

        Args:
            chat_id: 会话 ID
            messages: 消息列表
            is_group: 是否是群聊
            bot_id: Bot ID（单聊时必需）
            meta: 会话元数据（保存到 meta.json）

        Returns:
            是否保存成功
        """
        try:
            history_file = self.get_history_path(chat_id, is_group, bot_id)
            history_dir = os.path.dirname(history_file)
            os.makedirs(history_dir, exist_ok=True)

            # 保存历史消息
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(messages, f, ensure_ascii=False, indent=2)

            # 保存元数据
            if meta:
                meta_file = self.get_meta_path(chat_id, is_group, bot_id)
                with open(meta_file, 'w', encoding='utf-8') as f:
                    json.dump(meta, f, ensure_ascii=False, indent=2)

            return True
        except Exception as e:
            print(f"[HistoryManager] 保存会话历史失败: {e}")
            return False

    def clear_history(self, chat_id: str, is_group: bool = False,
                     bot_id: str = None) -> bool:
        """
        清空历史记录

        Args:
            chat_id: 会话 ID
            is_group: 是否是群聊
            bot_id: Bot ID（单聊时必需）

        Returns:
            是否清空成功
        """
        try:
            history_file = self.get_history_path(chat_id, is_group, bot_id)

            if os.path.exists(history_file):
                os.remove(history_file)

            return True
        except Exception as e:
            print(f"[HistoryManager] 清空历史失败: {e}")
            return False

    def get_meta(self, chat_id: str, is_group: bool = False,
                bot_id: str = None) -> Optional[Dict]:
        """
        获取会话元数据

        Args:
            chat_id: 会话 ID
            is_group: 是否是群聊
            bot_id: Bot ID（单聊时必需）

        Returns:
            元数据字典，不存在返回 None
        """
        try:
            meta_file = self.get_meta_path(chat_id, is_group, bot_id)

            if not os.path.exists(meta_file):
                return None

            with open(meta_file, 'r', encoding='utf-8') as f:
                return json.load(f)

        except Exception as e:
            print(f"[HistoryManager] 读取元数据失败: {e}")
            return None

    def update_meta(self, chat_id: str, meta: Dict,
                   is_group: bool = False, bot_id: str = None) -> bool:
        """
        更新会话元数据

        Args:
            chat_id: 会话 ID
            meta: 元数据字典
            is_group: 是否是群聊
            bot_id: Bot ID（单聊时必需）

        Returns:
            是否更新成功
        """
        try:
            meta_file = self.get_meta_path(chat_id, is_group, bot_id)
            meta_dir = os.path.dirname(meta_file)
            os.makedirs(meta_dir, exist_ok=True)

            with open(meta_file, 'w', encoding='utf-8') as f:
                json.dump(meta, f, ensure_ascii=False, indent=2)

            return True
        except Exception as e:
            print(f"[HistoryManager] 更新元数据失败: {e}")
            return False
