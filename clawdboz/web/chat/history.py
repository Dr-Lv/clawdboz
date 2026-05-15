#!/usr/bin/env python3
"""
Chat History Manager - 聊天历史记录管理模块

提供聊天历史记录的加载、保存、管理功能。
支持群聊和单聊历史记录的持久化存储。

新版本：使用 session.json 合并 history.json 和 meta.json
保持向后兼容：如果 session.json 不存在，自动迁移旧数据
"""

import asyncio
import json
import os
import time
from typing import Dict, List, Optional


class ChatHistoryManager:
    """聊天历史记录管理器

    管理聊天历史记录的内存缓存和持久化存储。
    支持群聊和单聊两种模式的历史记录管理。

    存储路径 (新格式):
    - 群聊: groupspace/g_{chat_id}/session.json
    - 单聊: workplace_{bot_id}/w_{chat_id}/session.json

    向后兼容:
    - 如果 session.json 不存在，尝试读取旧的 history.json 和 meta.json
    - 保存时统一保存到 session.json
    """

    def __init__(self, base_workplace: str, bots: Dict[str, object] = None):
        """初始化历史记录管理器

        Args:
            base_workplace: 基础 workplace 目录路径
            bots: Bot 实例字典 {bot_id: bot_instance}
        """
        self.base_workplace = base_workplace
        self.bots = bots or {}

        # 内存中的历史记录缓存: {chat_id: [{"sender": "user|bot_id", "content": "...", "time": timestamp}, ...]}
        self._chat_history: Dict[str, list] = {}
        self._chat_history_lock = asyncio.Lock()
        self._max_history = 30  # 最多保留 30 条记录

        # 当前会话的 Bot IDs（用于判断群聊/单聊）
        self._current_session_bot_ids: List[str] = []

    def set_current_session_bots(self, bot_ids: List[str]):
        """设置当前会话的 Bot IDs

        Args:
            bot_ids: Bot ID 列表
        """
        self._current_session_bot_ids = bot_ids

    def _get_session_file_path(self, chat_id: str, is_group: bool = False, bot_id: str = None) -> str:
        """获取会话文件路径 (session.json)

        群聊：groupspace/g_{chat_id}/session.json
        单聊：workplace_{bot_id}/w_{chat_id}/session.json
        飞书会话：workplace_{bot_id}/f_{chat_id}/session.json

        修复：处理 chat_id 已经带有 g_、w_ 或 f_ 前缀的情况，避免双重前缀

        Args:
            chat_id: 会话 ID
            is_group: 是否是群聊
            bot_id: Bot ID（单聊时需要，如未提供会尝试查找现有文件）

        Returns:
            会话文件路径 (session.json)
        """
        # 处理 chat_id 已经带有前缀的情况
        if chat_id.startswith('g_'):
            # 群聊且已经有 g_ 前缀
            if is_group:
                return os.path.join(self.base_workplace, 'groupspace', chat_id, 'session.json')
            else:
                # 这种情况不应该发生，但兼容处理
                chat_id = chat_id[2:]  # 去掉 g_ 前缀
        elif chat_id.startswith('w_'):
            # 单聊且已经有 w_ 前缀
            if not is_group:
                if not bot_id:
                    # 尝试从所有 workplace 中查找已存在的会话
                    bot_id = self._find_existing_session_bot_id(chat_id)
                if bot_id:
                    return os.path.join(self.base_workplace, f'workplace_{bot_id}', chat_id, 'session.json')
            else:
                chat_id = chat_id[2:]  # 去掉 w_ 前缀
        elif chat_id.startswith('f_'):
            # 飞书会话且已经有 f_ 前缀
            if not is_group:
                if not bot_id:
                    # 尝试从所有 workplace 中查找已存在的飞书会话
                    bot_id = self._find_existing_session_bot_id(chat_id)
                if bot_id:
                    return os.path.join(self.base_workplace, f'workplace_{bot_id}', chat_id, 'session.json')
            else:
                chat_id = chat_id[2:]  # 去掉 f_ 前缀

        if is_group:
            # 群聊使用 groupspace
            return os.path.join(self.base_workplace, 'groupspace', f'g_{chat_id}', 'session.json')
        else:
            # 单聊使用 Bot 的 workplace（先查找 w_，再查找 f_）
            if not bot_id:
                # 尝试从所有 workplace 中查找已存在的 web 会话
                bot_id = self._find_existing_session_bot_id(f'w_{chat_id}')
            if not bot_id:
                # 尝试查找飞书会话
                bot_id = self._find_existing_session_bot_id(f'f_{chat_id}')
            if bot_id:
                # 检查是 web 会话还是飞书会话
                web_path = os.path.join(self.base_workplace, f'workplace_{bot_id}', f'w_{chat_id}', 'session.json')
                if os.path.exists(web_path):
                    return web_path
                feishu_path = os.path.join(self.base_workplace, f'workplace_{bot_id}', f'f_{chat_id}', 'session.json')
                if os.path.exists(feishu_path):
                    return feishu_path
                # 默认返回 web 路径（用于创建新会话）
                return web_path
            return None

    def _find_existing_session_bot_id(self, session_dir_name: str) -> Optional[str]:
        """查找已存在会话的 bot_id

        在所有 workplace 目录中搜索 session_dir_name，返回找到的第一个 bot_id

        Args:
            session_dir_name: 会话目录名 (如 'w_session_xxx')

        Returns:
            bot_id 或 None
        """
        if not os.path.exists(self.base_workplace):
            return None

        for dirname in os.listdir(self.base_workplace):
            if dirname.startswith('workplace_'):
                bot_id = dirname[len('workplace_'):]
                session_path = os.path.join(
                    self.base_workplace, dirname, session_dir_name, 'session.json'
                )
                if os.path.exists(session_path):
                    return bot_id
        return None

    def _get_legacy_history_path(self, chat_id: str, is_group: bool = False, bot_id: str = None) -> str:
        """获取旧版 history.json 路径（用于向后兼容）"""
        session_path = self._get_session_file_path(chat_id, is_group, bot_id)
        if session_path:
            return session_path.replace('session.json', 'history.json')
        return None

    def _get_legacy_meta_path(self, chat_id: str, is_group: bool = False, bot_id: str = None) -> str:
        """获取旧版 meta.json 路径（用于向后兼容）"""
        session_path = self._get_session_file_path(chat_id, is_group, bot_id)
        if session_path:
            return session_path.replace('session.json', 'meta.json')
        return None

    async def get_chat_history(self, chat_id: str) -> list:
        """获取聊天历史记录

        优先从内存获取，如果没有则从文件加载

        Args:
            chat_id: 会话 ID

        Returns:
            历史记录列表
        """
        async with self._chat_history_lock:
            if chat_id in self._chat_history and self._chat_history[chat_id]:
                return self._chat_history[chat_id].copy()

        # 内存中没有，从文件加载
        return await self.load_session_history(chat_id)

    async def add_to_history(self, chat_id: str, sender: str, content: str,
                             bot_id: str = None, is_group: bool = None, is_hidden: bool = False):
        """添加记录到聊天历史并持久化到文件

        Args:
            chat_id: 会话 ID
            sender: 发送者（"user" 或 bot_id）
            content: 消息内容
            bot_id: 当前会话的 bot_id（单聊时传入，群聊时可不传）
            is_group: 是否是群聊（传入则优先使用，否则自动判断）
            is_hidden: 是否隐藏消息（不在页面显示，但记录到 history）
        """
        print(f"[ChatHistory] chat_id={chat_id}, sender={sender}, bot_id={bot_id}, "
              f"is_group={is_group}, content={content[:50]}...")

        # 如果传入了 is_group 则优先使用，否则自动判断
        if is_group is None:
            is_group = False
            if chat_id.startswith('session_'):
                # 从当前会话的 bot_ids 判断
                if self._current_session_bot_ids:
                    is_group = len(self._current_session_bot_ids) > 1
                    if not bot_id:
                        bot_id = self._current_session_bot_ids[0] if self._current_session_bot_ids else None
                else:
                    # 单聊（没有 _current_session_bot_ids）
                    is_group = False
                    # 如果未传入 bot_id，尝试从 sender 推断
                    if not bot_id and sender != "user":
                        bot_id = sender
                    # 注意：不再默认使用第一个 bot，而是让 _get_session_file_path 去查找已存在的会话

        async with self._chat_history_lock:
            if chat_id not in self._chat_history:
                # 如果内存中没有该会话的历史记录，先从文件加载，避免覆盖已有消息
                self._chat_history[chat_id] = await self.load_session_history(
                    chat_id, is_group=is_group, bot_id=bot_id
                )
            msg_data = {
                "sender": sender,
                "content": content,
                "time": time.time()
            }
            if is_hidden:
                msg_data["is_hidden"] = True
            self._chat_history[chat_id].append(msg_data)
            # 限制历史记录数量
            if len(self._chat_history[chat_id]) > self._max_history:
                self._chat_history[chat_id] = self._chat_history[chat_id][-self._max_history:]

            # 获取 bot_ids 用于保存
            bot_ids_to_save = None
            if self._current_session_bot_ids:
                bot_ids_to_save = self._current_session_bot_ids
            elif bot_id:
                bot_ids_to_save = [bot_id]

            await self.save_session_history(
                chat_id, is_group=is_group, bot_id=bot_id, bot_ids=bot_ids_to_save
            )

    async def save_session_history(self, chat_id: str, is_group: bool = False,
                                   bot_id: str = None, bot_ids: list = None,
                                   name: str = None):
        """将历史记录保存到 session.json

        新格式：session.json 包含 meta + messages + stats

        Args:
            chat_id: 会话 ID
            is_group: 是否是群聊
            bot_id: Bot ID（单聊时使用）
            bot_ids: Bot ID 列表（群聊时使用）
            name: 会话名称
        """
        try:
            messages = self._chat_history.get(chat_id, [])

            # 确定保存路径（使用统一的方法避免双重前缀）
            session_path = self._get_session_file_path(chat_id, is_group=is_group, bot_id=bot_id)
            if not session_path:
                print(f"[ChatHistory] 无法确定会话文件路径，跳过保存: {chat_id}")
                return

            # 确保目录存在
            os.makedirs(os.path.dirname(session_path), exist_ok=True)

            # 读取现有数据（合并模式）
            existing_data = self._load_session_file_sync(session_path)

            # 更新时间戳
            now = time.time()

            # 构建 session.json 结构
            session_data = {
                "meta": {
                    "id": chat_id,
                    "chat_type": "group" if is_group else "single",
                    "bot_ids": bot_ids or existing_data.get("meta", {}).get("bot_ids", []),
                    "name": name if name is not None else existing_data.get("meta", {}).get("name", ""),
                    "created_at": existing_data.get("meta", {}).get("created_at", now),
                    "updated_at": now,
                    # 保留其他可能存在的元数据
                    **{k: v for k, v in existing_data.get("meta", {}).items()
                       if k not in ["id", "chat_type", "bot_ids", "name", "created_at", "updated_at"]}
                },
                "messages": messages,
                "stats": {
                    "message_count": len(messages),
                    "last_active": messages[-1]["time"] if messages else now
                }
            }

            # 异步写入文件
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, lambda: self._write_json_file(session_path, session_data))
            print(f"[ChatHistory] 会话数据已保存: {session_path} "
                  f"({len(messages)} 条, bot_ids={session_data['meta']['bot_ids']})")
        except Exception as e:
            print(f"[ChatHistory] 保存会话数据失败: {e}")

    def _write_json_file(self, file_path: str, data: dict):
        """同步写入 JSON 文件（在线程池中执行）

        Args:
            file_path: 文件路径
            data: 要写入的数据
        """
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)

    def _load_session_file_sync(self, session_path: str) -> dict:
        """同步加载 session.json（支持向后兼容）

        1. 如果 session.json 存在，直接读取
        2. 如果 session.json 不存在，尝试合并 history.json 和 meta.json
        3. 如果都不存在，返回空结构
        """
        # 优先读取 session.json
        if os.path.exists(session_path):
            try:
                with open(session_path, 'r', encoding='utf-8') as f:
                    return json.load(f)
            except Exception as e:
                print(f"[ChatHistory] 读取 session.json 失败: {e}")

        # 向后兼容：尝试读取旧文件
        legacy_history_path = session_path.replace('session.json', 'history.json')
        legacy_meta_path = session_path.replace('session.json', 'meta.json')

        result = {"meta": {}, "messages": [], "stats": {}}

        # 读取旧 history.json
        if os.path.exists(legacy_history_path):
            try:
                with open(legacy_history_path, 'r', encoding='utf-8') as f:
                    history_data = json.load(f)
                if isinstance(history_data, dict) and 'messages' in history_data:
                    result["messages"] = history_data["messages"]
                    # 迁移其他字段到 meta
                    for key in ['bot_ids', 'name']:
                        if key in history_data:
                            result["meta"][key] = history_data[key]
                elif isinstance(history_data, list):
                    result["messages"] = history_data
            except Exception as e:
                print(f"[ChatHistory] 读取旧 history.json 失败: {e}")

        # 读取旧 meta.json
        if os.path.exists(legacy_meta_path):
            try:
                with open(legacy_meta_path, 'r', encoding='utf-8') as f:
                    meta_data = json.load(f)
                result["meta"].update(meta_data)
            except Exception as e:
                print(f"[ChatHistory] 读取旧 meta.json 失败: {e}")

        return result

    async def load_session_history(self, chat_id: str, is_group: bool = False,
                                   bot_id: str = None) -> list:
        """从会话文件加载聊天记录

        统一从 session.json 读取（群聊在 groupspace，单聊在 workplace）
        向后兼容：如果 session.json 不存在，尝试读取 history.json

        Args:
            chat_id: 会话 ID
            is_group: 是否是群聊
            bot_id: Bot ID（单聊时使用）

        Returns:
            历史记录列表
        """
        try:
            # 确定文件路径（使用统一的方法避免双重前缀）
            session_path = self._get_session_file_path(chat_id, is_group=is_group, bot_id=bot_id)
            if not session_path:
                return []

            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(
                None, self._load_session_file_sync, session_path
            )

            return data.get("messages", [])
        except Exception as e:
            print(f"[ChatHistory] 加载历史记录失败: {e}")
            return []

    async def load_session_meta(self, chat_id: str, is_group: bool = False,
                                bot_id: str = None) -> dict:
        """加载会话元数据

        Args:
            chat_id: 会话 ID
            is_group: 是否是群聊
            bot_id: Bot ID（单聊时使用）

        Returns:
            元数据字典
        """
        try:
            session_path = self._get_session_file_path(chat_id, is_group=is_group, bot_id=bot_id)
            if not session_path:
                return {}

            loop = asyncio.get_event_loop()
            data = await loop.run_in_executor(
                None, self._load_session_file_sync, session_path
            )

            return data.get("meta", {})
        except Exception as e:
            print(f"[ChatHistory] 加载会话元数据失败: {e}")
            return {}

    async def load_all_sessions(self) -> Dict[str, list]:
        """加载所有保存的会话（从 groupspace）

        Returns:
            会话字典 {chat_id: history_list}
        """
        sessions = {}
        try:
            groupspace_dir = os.path.join(self.base_workplace, 'groupspace')
            if not os.path.exists(groupspace_dir):
                return sessions

            for dirname in os.listdir(groupspace_dir):
                if dirname.startswith('g_session_'):
                    chat_id = dirname[2:]  # 移除 'g_' 前缀
                    history = await self.load_session_history(chat_id, is_group=True)
                    if history:
                        sessions[chat_id] = history

            return sessions
        except Exception as e:
            print(f"[ChatHistory] 加载所有会话失败: {e}")
            return sessions

    async def clear_history(self, chat_id: str):
        """清空指定会话的历史记录

        Args:
            chat_id: 会话 ID
        """
        async with self._chat_history_lock:
            if chat_id in self._chat_history:
                del self._chat_history[chat_id]

    async def get_history_from_memory(self, chat_id: str) -> list:
        """从内存获取历史记录（不触发文件加载）

        Args:
            chat_id: 会话 ID

        Returns:
            历史记录列表，如果内存中没有则返回空列表
        """
        async with self._chat_history_lock:
            return self._chat_history.get(chat_id, []).copy()

    def update_bots(self, bots: Dict[str, object]):
        """更新 Bot 字典

        Args:
            bots: 新的 Bot 字典
        """
        self.bots = bots
