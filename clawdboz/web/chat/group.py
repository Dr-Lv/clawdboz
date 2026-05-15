#!/usr/bin/env python3
"""
Group Chat - 群聊功能模块

提供群聊功能，包括群组 workspace 管理、@提及处理和级联回复。
"""

import json
import os
import time
from typing import List, TYPE_CHECKING

from fastapi import WebSocket

if TYPE_CHECKING:
    from .core import ChatCore


class GroupChatHandler:
    """群聊处理器

    处理群聊相关的逻辑，包括群组 workspace 管理、@提及处理和级联回复。
    """

    def __init__(self, chat_core: "ChatCore"):
        """初始化群聊处理器

        Args:
            chat_core: ChatCore 实例
        """
        self._core = chat_core

    async def handle_group_chat(self, ws: WebSocket, bot_ids: list, message: str,
                                chat_id: str = "default", thinking_mode: bool = True, is_hidden: bool = False):
        """群聊：多个 Bot 同时回复（共享上下文）v3.0

        在群聊模式下：
        1. 所有 Bot 共享同一个群组 workspace：groupspace/g_[session_id]/
        2. 不再创建符号链接，所有 Bot 直接使用该目录

        Args:
            ws: WebSocket 连接
            bot_ids: Bot ID 列表
            message: 用户消息
            chat_id: 聊天会话 ID
            thinking_mode: 是否显示思考过程
        """
        print(f"[GroupChat] group_chat 开始: chat_id={chat_id}, bots={bot_ids}, "
              f"thinking_mode={thinking_mode}, message={message[:50]}")

        # 先保存用户消息到历史
        print(f"[GroupChat] 正在保存用户消息到历史: chat_id={chat_id}, message={message[:50]}..., is_hidden={is_hidden}")
        await self._core._history_mgr.add_to_history(chat_id, "user", message, is_group=True, is_hidden=is_hidden)
        print(f"[GroupChat] 用户消息已保存")

        # 广播用户消息到所有客户端
        if not is_hidden:
            print(f"[GroupChat] 准备广播用户消息，has callback: {self._core._broadcast_callback is not None}")
            if self._core._broadcast_callback:
                user_msg_data = {
                    "type": "user_message",
                    "chat_id": chat_id,
                    "content": message,
                    "sender": "user"
                }
                print(f"[GroupChat] 广播用户消息: {user_msg_data}")
                await self._core._broadcast_callback(user_msg_data, ws)
                print(f"[GroupChat] 广播用户消息完成")
        else:
            print(f"[GroupChat] 消息标记为隐藏，跳过广播")

        # 默认使用传入的 bot_ids
        final_bot_ids = bot_ids

        # 创建群组 workspace
        try:
            group_dir = self._core._workspace_mgr.get_group_workspace(chat_id, member_bot_ids=bot_ids)
            print(f"[GroupChat] 群组 workspace: {group_dir}")

            # 更新或创建 session.json (新格式，合并了 history.json 和 meta.json)
            session_path = os.path.join(group_dir, 'session.json')

            # 读取现有 session.json（向后兼容旧的 meta.json）
            session_data = {"meta": {}, "messages": [], "stats": {}}
            if os.path.exists(session_path):
                try:
                    with open(session_path, 'r', encoding='utf-8') as f:
                        session_data = json.load(f)
                except:
                    pass
            else:
                # 向后兼容：如果 session.json 不存在，尝试读取旧的 meta.json
                legacy_meta_path = os.path.join(group_dir, 'meta.json')
                if os.path.exists(legacy_meta_path):
                    try:
                        with open(legacy_meta_path, 'r', encoding='utf-8') as f:
                            session_data["meta"] = json.load(f)
                    except:
                        pass

            # 合并 bot_ids
            final_bot_ids = list(dict.fromkeys(
                (session_data.get("meta", {}).get('bot_ids', []) or []) + bot_ids
            ))
            if not final_bot_ids:
                # 向后兼容：尝试从旧的 history.json 读取
                legacy_history_path = os.path.join(group_dir, 'history.json')
                if os.path.exists(legacy_history_path):
                    try:
                        with open(legacy_history_path, 'r', encoding='utf-8') as f:
                            hd = json.load(f)
                        if isinstance(hd, dict) and hd.get('bot_ids'):
                            final_bot_ids = hd['bot_ids']
                    except:
                        pass

            # 更新时间戳
            now = time.time()

            # 构建 session.json 结构
            session_data["meta"].update({
                'id': chat_id,
                'bot_ids': final_bot_ids,
                'chat_type': 'group',
                'is_group': True,
                'updated_at': now
            })
            if 'created_at' not in session_data["meta"]:
                session_data["meta"]['created_at'] = now

            with open(session_path, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
            print(f"[GroupChat] 更新群组 session.json: {session_path}")

        except Exception as e:
            print(f"[GroupChat] 创建群组 workspace 或更新 session.json 失败: {e}")

        # 保存当前会话的 bot_ids
        self._core._current_session_bot_ids = final_bot_ids
        self._core._history_mgr.set_current_session_bots(final_bot_ids)
        self._core._mention_mgr.set_chat_history(self._core._history_mgr._chat_history)

        # 检查用户消息是否@了特定Bot
        mentioned_bots = self._core._mention_mgr.parse_mentions(message, chat_id)
        mentioned_bots = [b for b in mentioned_bots if b in bot_ids]

        if mentioned_bots:
            # 用户@了特定Bot
            print(f"[GroupChat] 用户消息@了Bot: {mentioned_bots}，使用上下文截取")

            for target_id in mentioned_bots:
                if target_id not in bot_ids:
                    continue

                # 获取被@的上下文历史
                mention_context = self._core._mention_mgr.get_mention_context_history(
                    chat_id, "user", message, target_id
                )

                # 构建引导性消息
                import re
                bot = self._core.bots.get(target_id)
                if bot:
                    bot_name = getattr(bot, 'name', None) or \
                        getattr(bot, '_bot_id', target_id)
                elif self._core._remote_bot_mgr and self._core._remote_bot_mgr.is_remote_bot(target_id):
                    # 获取远程 Bot 显示名称
                    remote_bots = self._core._remote_bot_mgr.get_all_bots({})
                    remote_bot = remote_bots.get(target_id)
                    bot_name = remote_bot.get('name', target_id) if remote_bot else target_id
                else:
                    bot_name = target_id
                short_id = bot_name[0] if bot_name else target_id[0] if target_id else ''

                content_without_mention = re.sub(rf'@{re.escape(target_id)}(?:\s|$)',
                                                  '', message, flags=re.IGNORECASE).strip()
                content_without_mention = re.sub(rf'@{re.escape(bot_name)}(?:\s|$)',
                                                  '', content_without_mention, flags=re.IGNORECASE).strip()
                if short_id and short_id != target_id and short_id != bot_name:
                    content_without_mention = re.sub(rf'@{re.escape(short_id)}(?:\s|$)',
                                                      '', content_without_mention, flags=re.IGNORECASE).strip()

                if not content_without_mention:
                    enhanced_message = f"{message}\n\n[系统提示：用户@了你。请基于上述对话上下文，直接执行相关操作或继续话题。]"
                else:
                    enhanced_message = message

                print(f"[GroupChat] 触发用户@回复: user -> {target_id}, "
                      f"上下文消息数: {len(mention_context)}")

                # 触发目标 Bot 回复
                result = await self._core.single_chat_with_context(
                    ws, target_id, enhanced_message, chat_id,
                    is_group=True, thinking_mode=thinking_mode,
                    context_history=mention_context
                )

                # 保存回复到历史
                if result:
                    await self._core._history_mgr.add_to_history(chat_id, target_id, result, is_group=True)

                    # 检查级联回复
                    await self._check_and_trigger_mention_cascade(
                        ws, target_id, result, chat_id, thinking_mode=thinking_mode
                    )
        else:
            # 用户没有@任何Bot
            print(f"[GroupChat] 用户消息没有@任何Bot，不触发Bot回复")

    async def _check_and_trigger_mention_cascade(self, ws: WebSocket, sender_bot_id: str,
                                                  message: str, chat_id: str,
                                                  thinking_mode: bool = True):
        """检查 Bot 回复中是否 @ 了其他 Bot，触发级联回复

        Args:
            ws: WebSocket 连接
            sender_bot_id: 发送消息的 Bot ID
            message: 消息内容
            chat_id: 聊天会话 ID
            thinking_mode: 是否显示思考过程
        """
        print(f"[GroupChat] 检查级联回复 - Bot {sender_bot_id} 的回复 ({len(message)} 字符)")

        # 解析消息中的 @提及
        mentioned_bots = self._core._mention_mgr.parse_mentions(message, chat_id)
        if not mentioned_bots:
            print(f"[GroupChat] 未检测到 @提及")
            return

        print(f"[GroupChat] Bot {sender_bot_id} 的回复中 @ 了: {mentioned_bots}")

        # 获取有权限的 @ 目标
        authorized_targets = await self._core._mention_mgr.get_authorized_targets(
            sender_bot_id, chat_id, mentioned_bots
        )

        if not authorized_targets:
            print(f"[GroupChat] 没有授权的 @ 目标")
            return

        print(f"[GroupChat] 触发级联回复: {sender_bot_id} -> {authorized_targets}")

        # 增加深度
        current_depth = await self._core._mention_mgr.increment_depth(chat_id)

        try:
            # 为每个被 @ 的 Bot 创建上下文并触发回复
            for target_id in authorized_targets:
                is_remote = self._core._remote_bot_mgr and self._core._remote_bot_mgr.is_remote_bot(target_id)
                if target_id not in self._core.bots and not is_remote:
                    print(f"[GroupChat] Bot {target_id} 不存在，跳过")
                    continue

                # 获取被@的上下文历史
                mention_context = self._core._mention_mgr.get_mention_context_history(
                    chat_id, sender_bot_id, message, target_id
                )

                context_message = f"[被 @{sender_bot_id} 提及]\n\n{message}\n\n请回复上述消息。"

                print(f"[GroupChat] 触发级联回复: {sender_bot_id} -> {target_id}, "
                      f"上下文消息数: {len(mention_context)}")

                # 触发目标 Bot 回复
                result = await self._core.single_chat_with_context(
                    ws, target_id, context_message, chat_id,
                    is_group=True, thinking_mode=thinking_mode,
                    context_history=mention_context
                )

                # 保存级联回复到历史记录
                if result:
                    await self._core._history_mgr.add_to_history(chat_id, target_id, result, is_group=True)
        finally:
            # 恢复深度
            await self._core._mention_mgr.decrement_depth(chat_id)
