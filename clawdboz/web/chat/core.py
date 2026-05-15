#!/usr/bin/env python3
"""
Chat Core - 核心聊天功能模块

提供单聊、群聊和级联回复的核心功能。
支持流式输出、思考模式、上下文管理和会话隔离。
"""

import asyncio
import json
import os
import time
import uuid
from typing import Dict, List, Optional, Callable

from fastapi import WebSocket

from .group import GroupChatHandler


class ChatCore:
    """核心聊天处理器

    处理单聊、群聊和级联回复的核心逻辑。
    支持流式输出、思考模式、上下文管理。
    """

    def __init__(self, bots: Dict[str, object], base_workplace: str,
                 workspace_mgr, history_mgr, mention_mgr, acp_mgr,
                 broadcast_callback: Optional[Callable] = None):
        """初始化聊天核心

        Args:
            bots: Bot 实例字典 {bot_id: bot_instance}
            base_workplace: 基础 workplace 目录路径
            workspace_mgr: WorkspaceManager 实例
            history_mgr: ChatHistoryManager 实例
            mention_mgr: MentionManager 实例
            acp_mgr: ACPClientManager 实例
            broadcast_callback: 可选的广播回调函数，用于向所有客户端广播消息
        """
        self.bots = bots
        self.base_workplace = base_workplace
        self._workspace_mgr = workspace_mgr
        self._history_mgr = history_mgr
        self._mention_mgr = mention_mgr
        self._acp_mgr = acp_mgr
        self._broadcast_callback = broadcast_callback

        # 并发锁：每个 (session_id, bot_id) 一个锁
        self._locks: Dict[tuple, asyncio.Lock] = {}
        self._locks_lock = asyncio.Lock()

        # 当前会话的 Bot IDs（用于群聊）
        self._current_session_bot_ids: List[str] = []

        # 最大历史记录数
        self._max_history = 30

        # 初始化群聊处理器
        self._group_handler = GroupChatHandler(self)

        # 远程 Bot 管理器（通过 set_remote_bot_manager 设置）
        self._remote_bot_mgr = None

        # Feishu 管理器回调（用于发送 Bot 回复到飞书）
        self._feishu_manager = None

    async def _get_lock(self, session_id: str, bot_id: str) -> asyncio.Lock:
        """获取 (session_id, bot_id) 组合的并发锁

        这允许同一 Bot 在不同 session 中并发处理，但同一 session 内串行。

        Args:
            session_id: 前端会话 ID
            bot_id: Bot ID

        Returns:
            asyncio.Lock 实例
        """
        key = (session_id, bot_id)

        async with self._locks_lock:
            if key not in self._locks:
                self._locks[key] = asyncio.Lock()
            return self._locks[key]

    def set_feishu_manager(self, feishu_manager):
        """设置 Feishu 管理器

        Args:
            feishu_manager: FeishuBotManager 实例
        """
        self._feishu_manager = feishu_manager
        print(f"[ChatCore] Feishu 管理器已设置")

    def set_remote_bot_manager(self, remote_bot_mgr):
        """设置远程 Bot 管理器

        Args:
            remote_bot_mgr: RemoteBotManager 实例
        """
        self._remote_bot_mgr = remote_bot_mgr
        print(f"[ChatCore] 远程 Bot 管理器已设置")

    async def _call_remote_bot(
        self, ws: WebSocket, bot_id: str, message: str,
        chat_id: str, is_group: bool, thinking_mode: bool, is_hidden: bool,
        context_history: list = None
    ) -> Optional[str]:
        """调用远程 Bot

        Args:
            ws: WebSocket 连接
            bot_id: 远程 Bot ID (格式: instance_id:bot_id)
            message: 用户消息
            chat_id: 聊天会话 ID
            is_group: 是否是群聊模式
            thinking_mode: 是否显示思考过程
            is_hidden: 是否隐藏消息
            context_history: 群聊上下文历史记录

        Returns:
            Bot 的完整回复内容，或 None
        """
        print(f"[ChatCore] 调用远程 Bot: {bot_id}, context_len={len(context_history) if context_history else 0}")

        # 生成消息唯一标识
        msg_id = str(uuid.uuid4())
        seq = 0

        # 获取远程Bot的头像和显示名称
        bot_avatar_color = ""
        bot_avatar_icon = ""
        bot_avatar_image = ""
        bot_display_name = bot_id
        if self._remote_bot_mgr:
            bot_info = self._remote_bot_mgr.get_remote_bot_info(bot_id)
            if bot_info:
                bot_avatar_color = bot_info.get("avatar_color", "")
                bot_avatar_icon = bot_info.get("avatar_icon", "")
                bot_avatar_image = bot_info.get("avatar_image", "")
                bot_display_name = bot_info.get("display_name", bot_id)
            else:
                # fallback: 从本地 bots 字典查找（本地 bot）
                local_bot = self.bots.get(bot_id)
                if local_bot and hasattr(local_bot, 'avatar_color'):
                    bot_avatar_color = local_bot.avatar_color
                if local_bot and hasattr(local_bot, 'avatar_icon'):
                    bot_avatar_icon = local_bot.avatar_icon
                if local_bot and hasattr(local_bot, 'avatar_image'):
                    bot_avatar_image = local_bot.avatar_image
                if local_bot and hasattr(local_bot, 'name'):
                    bot_display_name = local_bot.name

        # 发送开始标记
        start_data = {
            "type": "start",
            "msg_id": msg_id,
            "seq": seq,
            "bot_id": bot_id,
            "bot_name": bot_display_name,
            "avatar_color": bot_avatar_color,
            "avatar_icon": bot_avatar_icon,
            "avatar_image": bot_avatar_image,
            "chat_id": chat_id
        }
        try:
            await ws.send_json(start_data)
        except Exception as e:
            print(f"[ChatCore] 发送 start 到当前连接失败: {e}")
        if self._broadcast_callback:
            try:
                await self._broadcast_callback(start_data, ws)
            except Exception as e:
                print(f"[ChatCore] 广播 start 失败: {e}")

        # 保存用户消息到历史记录
        if not is_group:
            await self._history_mgr.add_to_history(chat_id, "user", message, bot_id=bot_id)

        # 广播用户消息（仅单聊模式；群聊的用户消息由 group_chat 统一广播，
        # mention cascade 调用远程 bot 时不应重复广播 synthetic prompt）
        if not is_group and not is_hidden and self._broadcast_callback:
            user_msg_data = {
                "type": "user_message",
                "chat_id": chat_id,
                "content": message,
                "sender": "user"
            }
            await self._broadcast_callback(user_msg_data, ws)

        async def send_chunk(text: str, is_thinking: bool = False):
            """发送流式内容"""
            nonlocal seq
            seq += 1
            message_data = {
                "type": "chunk",
                "msg_id": msg_id,
                "seq": seq,
                "bot_id": bot_id,
                "content": text,
                "is_thinking": is_thinking,
                "chat_id": chat_id
            }
            try:
                await ws.send_json(message_data)
            except Exception as e:
                print(f"[ChatCore] 发送 chunk 到当前连接失败: {e}")
            if self._broadcast_callback:
                try:
                    await self._broadcast_callback(message_data, ws)
                except Exception as e:
                    print(f"[ChatCore] 广播 chunk 失败: {e}")

        try:
            # 构建 API 基础 URL（从当前请求获取）
            # TODO: 从 ws 获取实际的主机名和端口
            fs_api_url = f"http://localhost:8080/api/remote/fs"

            # 调用远程 Bot
            params = {
                "message": message,
                "chat_id": chat_id
            }
            if context_history:
                params["context_history"] = context_history
                print(f"[ChatCore] 传递群聊上下文给远程 Bot: {len(context_history)} 条消息")

            result = await self._remote_bot_mgr.call_remote_bot(
                bot_id=bot_id,
                method="chat",
                params=params,
                chat_id=chat_id,
                fs_api_url=fs_api_url,
                timeout=120
            )

            if result and result.get("success"):
                response_content = result.get("result", result.get("content", ""))
                await send_chunk(response_content)

                # 保存到历史记录
                if not is_group:
                    await self._history_mgr.add_to_history(chat_id, bot_id, response_content, bot_id=bot_id)

                # 发送完成标记
                done_data = {
                    "type": "done",
                    "msg_id": msg_id,
                    "bot_id": bot_id,
                    "final": response_content,
                    "chat_id": chat_id
                }
                try:
                    await ws.send_json(done_data)
                except Exception as e:
                    print(f"[ChatCore] 发送 done 到当前连接失败: {e}")
                if self._broadcast_callback:
                    try:
                        await self._broadcast_callback(done_data, ws)
                    except Exception as e:
                        print(f"[ChatCore] 广播 done 失败: {e}")

                return response_content
            else:
                if result:
                    error_msg = result.get("error", "远程 Bot 调用失败")
                else:
                    error_msg = "远程 Bot 无响应（可能离线或网络不通），消息已加入注册服务器队列，远程实例上线后将自动处理"
                await send_chunk(f"Error: {error_msg}")

                # 发送完成标记（即使失败）
                done_data = {
                    "type": "done",
                    "msg_id": msg_id,
                    "bot_id": bot_id,
                    "final": f"Error: {error_msg}",
                    "chat_id": chat_id
                }
                try:
                    await ws.send_json(done_data)
                except Exception as e:
                    print(f"[ChatCore] 发送 done 到当前连接失败: {e}")
                if self._broadcast_callback:
                    try:
                        await self._broadcast_callback(done_data, ws)
                    except Exception as e:
                        print(f"[ChatCore] 广播 done 失败: {e}")

                return None

        except Exception as e:
            print(f"[ChatCore] 远程 Bot 调用失败: {e}")
            import traceback
            traceback.print_exc()
            await send_chunk(f"Error: {str(e)}")

            # 发送完成标记（即使异常）
            done_data = {
                "type": "done",
                "msg_id": msg_id,
                "bot_id": bot_id,
                "final": f"Error: {str(e)}",
                "chat_id": chat_id
            }
            try:
                await ws.send_json(done_data)
            except Exception as e2:
                print(f"[ChatCore] 发送 done 到当前连接失败: {e2}")
            if self._broadcast_callback:
                try:
                    await self._broadcast_callback(done_data, ws)
                except Exception as e2:
                    print(f"[ChatCore] 广播 done 失败: {e2}")

            return None


    async def single_chat(self, ws: WebSocket, bot_id: str, message: str,
                          chat_id: str = "default", is_group: bool = False,
                          thinking_mode: bool = True, is_hidden: bool = False) -> Optional[str]:
        """单聊：一个 Bot 回复（v3.0 - 支持会话级隔离）

        Args:
            ws: WebSocket 连接
            bot_id: Bot ID
            message: 用户消息
            chat_id: 聊天会话 ID（同时也是 session_id）
            is_group: 是否是群聊模式（用于控制是否保存历史记录）
            thinking_mode: 是否显示思考过程
            is_hidden: 是否隐藏消息（不广播到前端）

        Returns:
            Bot 的完整回复内容，或 None（如果出错）
        """
        print(f"[ChatCore] _single_chat 开始: bot_id={bot_id}, chat_id={chat_id}, "
              f"is_group={is_group}, thinking_mode={thinking_mode}, message={message[:50]}")

        # 检查是否是远程 Bot
        if self._remote_bot_mgr and self._remote_bot_mgr.is_remote_bot(bot_id):
            return await self._call_remote_bot(
                ws, bot_id, message, chat_id, is_group, thinking_mode, is_hidden
            )

        bot = self.bots[bot_id]

        # 获取会话级的锁
        lock = await self._get_lock(chat_id, bot_id)

        # 生成消息唯一标识
        msg_id = str(uuid.uuid4())
        seq = 0

        # 发送开始标记
        print(f"[ChatCore] 发送 start 消息")
        await ws.send_json({
            "type": "start",
            "msg_id": msg_id,
            "seq": seq,
            "bot_id": bot_id,
            "bot_name": getattr(bot, '_bot_id', bot_id),
            "chat_id": chat_id
        })

        async def send_chunk(text: str, is_thinking: bool = False):
            """发送流式内容（同时广播给所有客户端）"""
            nonlocal seq
            seq += 1
            message_data = {
                "type": "chunk",
                "msg_id": msg_id,
                "seq": seq,
                "bot_id": bot_id,
                "content": text,
                "is_thinking": is_thinking,
                "chat_id": chat_id
            }
            try:
                # 发送给当前连接
                await ws.send_json(message_data)
                # 广播给其他所有连接的客户端（排除当前连接避免重复）
                if self._broadcast_callback:
                    await self._broadcast_callback(message_data, ws)
            except Exception as e:
                print(f"[ChatCore] 发送 chunk 失败（客户端可能已断开）: {e}")
                raise

        # 加锁执行
        print(f"[ChatCore] 获取锁 (session={chat_id}, bot={bot_id})...")
        async with lock:
            print(f"[ChatCore] 锁已获取，调用 _call_bot_chat")
            try:
                # 先保存用户消息到历史记录
                if not is_group:
                    await self._history_mgr.add_to_history(chat_id, "user", message, bot_id=bot_id)

                # 广播用户消息到所有客户端（让其他连接的客户端也能看到）
                if not is_hidden:
                    print(f"[ChatCore] 准备广播用户消息，has callback: {self._broadcast_callback is not None}")
                    if self._broadcast_callback:
                        user_msg_data = {
                            "type": "user_message",
                            "chat_id": chat_id,
                            "content": message,
                            "sender": "user"
                        }
                        print(f"[ChatCore] 广播用户消息: {user_msg_data}")
                        await self._broadcast_callback(user_msg_data, ws)
                        print(f"[ChatCore] 广播用户消息完成")
                else:
                    print(f"[ChatCore] 消息标记为隐藏，跳过广播")

                # 获取历史记录
                history = await self._history_mgr.get_chat_history(chat_id) \
                    if chat_id and chat_id != "default" else []
                print(f"[ChatCore] 获取到历史记录: {len(history)} 条")

                # 调用 chat
                result = await self._call_bot_chat(
                    bot, message, send_chunk,
                    history=history, bot_id=bot_id,
                    session_id=chat_id, is_group=is_group,
                    thinking_mode=thinking_mode
                )
                print(f"[ChatCore] _call_bot_chat 返回: {result[:100] if result else 'None'}...")

                # 保存 bot 回复到历史记录
                if not is_group:
                    await self._history_mgr.add_to_history(chat_id, bot_id, result)

                # 检查级联回复（Bot 回复中 @ 了其他 Bot）
                # 单聊模式下也支持级联，使 CLI 发送的消息可以触发级联
                if result:
                    print(f"[ChatCore] 检查级联回复...")
                    await self._check_and_trigger_mention_cascade(
                        ws, bot_id, result, chat_id, thinking_mode=thinking_mode
                    )

                # 发送完成标记
                seq += 1
                print(f"[ChatCore] 发送 done 消息: msg_id={msg_id}, bot_id={bot_id}")
                done_msg_data = {
                    "type": "done",
                    "msg_id": msg_id,
                    "seq": seq,
                    "bot_id": bot_id,
                    "final": result,
                    "chat_id": chat_id
                }
                try:
                    await ws.send_json(done_msg_data)
                    print(f"[ChatCore] done 消息已发送到 WebSocket")
                except Exception as e:
                    print(f"[ChatCore] 发送 done 失败（客户端可能已断开）: {e}")

                # 广播 done 消息到所有客户端（让其他连接的客户端停止 loading）
                if self._broadcast_callback:
                    print(f"[ChatCore] 广播 done 消息: msg_id={msg_id}")
                    await self._broadcast_callback(done_msg_data, ws)
                    print(f"[ChatCore] done 消息广播完成")
                else:
                    print(f"[ChatCore] 无广播回调，跳过广播")

                return result
            except Exception as e:
                print(f"[ChatCore] _call_bot_chat 异常: {e}")
                import traceback
                traceback.print_exc()
                seq += 1
                try:
                    await ws.send_json({
                        "type": "error",
                        "msg_id": msg_id,
                        "seq": seq,
                        "bot_id": bot_id,
                        "error": str(e)
                    })
                except Exception as e2:
                    print(f"[ChatCore] 发送 error 失败（客户端可能已断开）: {e2}")
                return None

    async def single_chat_with_context(self, ws: WebSocket, bot_id: str, message: str,
                                       chat_id: str = "default", is_group: bool = False,
                                       thinking_mode: bool = True,
                                       context_history: list = None) -> Optional[str]:
        """单聊/级联回复：带指定上下文的 Bot 回复

        与 single_chat 的区别：
        - 可以传入指定的 context_history 作为上下文
        - 不从 get_chat_history 获取历史

        Args:
            ws: WebSocket 连接
            bot_id: Bot ID
            message: 用户消息
            chat_id: 聊天会话 ID
            is_group: 是否是群聊模式
            thinking_mode: 是否显示思考过程
            context_history: 指定的上下文历史记录列表

        Returns:
            Bot 的完整回复内容，或 None（如果出错）
        """
        print(f"[ChatCore] single_chat_with_context 开始: bot_id={bot_id}, chat_id={chat_id}, "
              f"context_len={len(context_history) if context_history else 0}")

        # 检查是否是远程 Bot
        is_remote = self._remote_bot_mgr and self._remote_bot_mgr.is_remote_bot(bot_id)
        print(f"[ChatCore] is_remote_bot check: {is_remote}")
        if is_remote:
            print(f"[ChatCore] Routing to remote bot manager")
            return await self._call_remote_bot(
                ws, bot_id, message, chat_id, is_group, thinking_mode,
                is_hidden=False, context_history=context_history
            )

        bot = self.bots[bot_id]

        # 获取会话级的锁
        lock = await self._get_lock(chat_id, bot_id)

        # 生成消息唯一标识
        msg_id = str(uuid.uuid4())
        seq = 0

        # 发送开始标记
        await ws.send_json({
            "type": "start",
            "msg_id": msg_id,
            "seq": seq,
            "bot_id": bot_id,
            "bot_name": getattr(bot, '_bot_id', bot_id),
            "chat_id": chat_id
        })

        async def send_chunk(text: str, is_thinking: bool = False):
            """发送流式内容（同时广播给所有客户端）"""
            nonlocal seq
            seq += 1
            message_data = {
                "type": "chunk",
                "msg_id": msg_id,
                "seq": seq,
                "bot_id": bot_id,
                "content": text,
                "is_thinking": is_thinking,
                "chat_id": chat_id
            }
            # 发送给当前连接（失败不阻断广播，例如 cli_web 已断开）
            try:
                await ws.send_json(message_data)
            except Exception as e:
                print(f"[ChatCore] 发送 chunk 到当前连接失败: {e}")
            # 广播给其他所有连接的客户端（排除当前连接避免重复）
            if self._broadcast_callback:
                try:
                    await self._broadcast_callback(message_data, ws)
                except Exception as e:
                    print(f"[ChatCore] 广播 chunk 失败: {e}")

        # 加锁执行
        async with lock:
            try:
                # 使用传入的 context_history
                history = context_history if context_history else []
                print(f"[ChatCore] 使用指定上下文: {len(history)} 条")

                # 调用 chat
                result = await self._call_bot_chat(
                    bot, message, send_chunk,
                    history=history, bot_id=bot_id,
                    session_id=chat_id, is_group=is_group,
                    thinking_mode=thinking_mode
                )

                # 保存 bot 回复到历史记录
                if not is_group:
                    await self._history_mgr.add_to_history(chat_id, bot_id, result)

                # 检查级联回复（Bot 回复中 @ 了其他 Bot）
                if result:
                    print(f"[ChatCore] 检查级联回复...")
                    await self._check_and_trigger_mention_cascade(
                        ws, bot_id, result, chat_id, thinking_mode=thinking_mode
                    )

                # 发送完成标记
                seq += 1
                done_msg_data = {
                    "type": "done",
                    "msg_id": msg_id,
                    "seq": seq,
                    "bot_id": bot_id,
                    "final": result,
                    "chat_id": chat_id
                }
                try:
                    await ws.send_json(done_msg_data)
                except Exception as e:
                    print(f"[ChatCore] 发送 done 到当前连接失败: {e}")

                # 广播 done 消息到所有客户端（让其他连接的客户端停止 loading）
                if self._broadcast_callback:
                    try:
                        print(f"[ChatCore] 广播 done 消息: msg_id={msg_id}")
                        await self._broadcast_callback(done_msg_data, ws)
                        print(f"[ChatCore] done 消息广播完成")
                    except Exception as e:
                        print(f"[ChatCore] 广播 done 失败: {e}")
                else:
                    print(f"[ChatCore] 无广播回调，跳过广播")

                return result
            except Exception as e:
                print(f"[ChatCore] single_chat_with_context 异常: {e}")
                import traceback
                traceback.print_exc()
                seq += 1
                await ws.send_json({
                    "type": "error",
                    "msg_id": msg_id,
                    "seq": seq,
                    "bot_id": bot_id,
                    "error": str(e)
                })
                return None

    async def group_chat(self, ws: WebSocket, bot_ids: list, message: str,
                         chat_id: str = "default", thinking_mode: bool = True, is_hidden: bool = False):
        """群聊：多个 Bot 同时回复（共享上下文）v3.0

        委托给 GroupChatHandler 处理。

        Args:
            ws: WebSocket 连接
            bot_ids: Bot ID 列表
            message: 用户消息
            chat_id: 聊天会话 ID
            thinking_mode: 是否显示思考过程
            is_hidden: 是否隐藏消息（不广播到前端）
        """
        await self._group_handler.handle_group_chat(ws, bot_ids, message, chat_id, thinking_mode, is_hidden)

    def _build_context_prompt(self, history: list, current_message: str, bot_id: str) -> str:
        """构建带上下文的 prompt

        Args:
            history: 历史记录列表
            current_message: 当前用户消息
            bot_id: 当前 Bot ID

        Returns:
            构建好的 prompt
        """
        if not history:
            return current_message

        context_parts = ["以下是最近聊天记录上下文：\n"]
        for msg in history[-self._max_history:]:
            sender = msg.get('sender', 'unknown')
            content = msg.get('content', '')

            if sender == "user":
                context_parts.append(f"用户: {content}")
            elif sender == "system":
                # 系统消息（如成员介绍）直接显示，不添加前缀
                context_parts.append(content)
            elif sender == bot_id:
                context_parts.append(f"你(Bot): {content}")
            else:
                context_parts.append(f"其他Bot({sender}): {content}")

        context_parts.append(f"\n用户当前消息：{current_message}\n\n请基于上下文回复用户的消息。")
        return "\n".join(context_parts)

    async def _call_bot_chat(self, bot: object, message: str, send_chunk,
                              history: list = None, bot_id: str = None,
                              session_id: str = "default", is_group: bool = False,
                              thinking_mode: bool = True) -> str:
        """
        调用 Bot 的聊天接口（v3.0 - 支持会话级隔离）

        使用 session 级的 ACPClient，确保不同会话之间的上下文不会混合。

        Args:
            bot: Bot 实例（LarkBot 或 simple_bot.Bot）
            message: 用户消息
            send_chunk: 异步回调函数，用于发送流式内容
            history: 历史记录列表（群聊模式下）
            bot_id: Bot ID
            session_id: 前端会话 ID（用于创建 session 级的 ACP session）
            is_group: 是否是群组模式
            thinking_mode: 是否显示思考过程

        Returns:
            完整的回复内容
        """
        loop = asyncio.get_event_loop()
        collected_chunks = []

        def on_chunk(text: str):
            """同步回调：收集内容并通过异步方式发送"""
            collected_chunks.append(text)
            asyncio.run_coroutine_threadsafe(send_chunk(text, is_thinking=False), loop)

        def on_thinking(text: str):
            """同步回调：发送思考过程（仅在 thinking_mode 为 True 时发送）"""
            if thinking_mode:
                asyncio.run_coroutine_threadsafe(send_chunk(text, is_thinking=True), loop)

        # 获取实际的 Bot 实例
        actual_bot = bot
        if hasattr(bot, '_bot'):  # simple_bot.Bot 包装类
            actual_bot = bot._bot

        # 构建带上下文的 prompt
        if history:
            final_prompt = self._build_context_prompt(history, message, bot_id)
            print(f"[ChatCore] 使用上下文 prompt，历史记录数: {len(history)}")
        else:
            final_prompt = message

        # 检查是否为飞书会话（通过检查 workplace_{bot_id}/f_{session_id} 是否存在）
        feishu_session_dir = os.path.join(
            self._workspace_mgr.base_workplace,
            f"workplace_{bot_id}",
            f"f_{session_id}"
        )
        is_feishu_session = os.path.exists(feishu_session_dir)
        if is_feishu_session:
            print(f"[ChatCore] 检测到飞书会话，使用 f_{session_id} 作为工作目录")

        # 在线程池中执行同步的 chat 方法
        def do_chat():
            """在线程中执行 Bot 调用"""
            if is_group:
                session_work_dir = self._workspace_mgr.get_group_workspace(session_id)
            else:
                # 如果是飞书会话，使用 f_ 前缀
                effective_session_id = f"f_{session_id}" if is_feishu_session else session_id
                session_work_dir = self._workspace_mgr.get_session_workspace(
                    bot_id, effective_session_id, is_group=False
                )

            original_dir = os.getcwd()
            os.chdir(session_work_dir)

            os.environ['CLAWDBOZ_SESSION_WORK_DIR'] = session_work_dir
            print(f"[ChatCore] 设置环境变量 CLAWDBOZ_SESSION_WORK_DIR={session_work_dir}")

            try:
                # 使用新的 session.json 格式（合并了 history.json 和 meta.json）
                session_path = os.path.join(session_work_dir, 'session.json')

                # 读取现有 session.json（向后兼容旧的 meta.json）
                session_data = {"meta": {}, "messages": [], "stats": {}}
                if os.path.exists(session_path):
                    with open(session_path, 'r', encoding='utf-8') as f:
                        session_data = json.load(f)
                else:
                    # 向后兼容：如果 session.json 不存在，尝试读取旧的 meta.json
                    legacy_meta_path = os.path.join(session_work_dir, 'meta.json')
                    if os.path.exists(legacy_meta_path):
                        with open(legacy_meta_path, 'r', encoding='utf-8') as f:
                            session_data["meta"] = json.load(f)

                bot_ids_list = [bot_id] if not is_group else getattr(self, '_current_session_bot_ids', [bot_id])
                now = time.time()

                session_data["meta"].update({
                    'id': session_id,
                    'bot_ids': bot_ids_list,
                    'chat_type': 'group' if is_group else 'single',
                    'is_group': is_group,
                    'updated_at': now
                })
                if 'created_at' not in session_data["meta"]:
                    session_data["meta"]['created_at'] = now
                if 'name' not in session_data["meta"]:
                    session_data["meta"]['name'] = ''

                with open(session_path, 'w', encoding='utf-8') as f:
                    json.dump(session_data, f, ensure_ascii=False, indent=2)
                print(f"[ChatCore] 更新 session.json: {session_path}")
            except Exception as e:
                print(f"[ChatCore] 更新 session.json 失败: {e}")

            try:
                future = asyncio.run_coroutine_threadsafe(
                    self._acp_mgr.get_or_create_client(session_id, bot_id, is_group=is_group),
                    loop
                )
                acp_client = future.result(timeout=10)

                if acp_client is None:
                    return "[无法创建 ACP 会话]"

                print(f"[ChatCore] 使用会话级 ACPClient: session={session_id}, bot={bot_id}")

                result = acp_client.chat(final_prompt, on_chunk=on_chunk, on_thinking=on_thinking, timeout=180, include_thinking_in_result=thinking_mode)
                return result

            except Exception as e:
                print(f"[ChatCore] chat 调用失败: {e}")
                import traceback
                traceback.print_exc()
                return f"[调用失败: {e}]"
            finally:
                os.chdir(original_dir)

        result = await loop.run_in_executor(None, do_chat)
        final_result = result if result else "[无回复]"

        # 如果是飞书会话，发送 Bot 回复到飞书
        if is_feishu_session and self._feishu_manager and final_result and not final_result.startswith("["):
            try:
                feishu_bot = self._feishu_manager.get_bot(bot_id)
                if feishu_bot:
                    # 提取飞书 chat_id（去掉 f_ 前缀）
                    feishu_chat_id = session_id[2:] if session_id.startswith("f_") else session_id
                    print(f"[ChatCore] 发送 Bot 回复到飞书: chat_id={feishu_chat_id}")
                    feishu_bot.send_reply(feishu_chat_id, final_result)
            except Exception as e:
                print(f"[ChatCore] 发送回复到飞书失败: {e}")

        return final_result

    async def _check_and_trigger_mention_cascade(self, ws: WebSocket, sender_bot_id: str,
                                                  message: str, chat_id: str,
                                                  thinking_mode: bool = True):
        """检查 Bot 回复中是否 @ 了其他 Bot，触发级联回复

        从 GroupChatHandler 迁移过来，使单聊模式也支持级联回复。

        Args:
            ws: WebSocket 连接
            sender_bot_id: 发送消息的 Bot ID
            message: 消息内容
            chat_id: 聊天会话 ID
            thinking_mode: 是否显示思考过程
        """
        print(f"[ChatCore] 检查级联回复 - Bot {sender_bot_id} 的回复 ({len(message)} 字符)")

        # 解析消息中的 @提及
        mentioned_bots = self._mention_mgr.parse_mentions(message, chat_id)
        if not mentioned_bots:
            print(f"[ChatCore] 未检测到 @提及")
            return

        print(f"[ChatCore] Bot {sender_bot_id} 的回复中 @ 了: {mentioned_bots}")

        # 获取有权限的 @ 目标
        authorized_targets = await self._mention_mgr.get_authorized_targets(
            sender_bot_id, chat_id, mentioned_bots
        )

        if not authorized_targets:
            print(f"[ChatCore] 没有授权的 @ 目标")
            return

        print(f"[ChatCore] 触发级联回复: {sender_bot_id} -> {authorized_targets}")

        # 增加深度
        current_depth = await self._mention_mgr.increment_depth(chat_id)

        try:
            # 为每个被 @ 的 Bot 创建上下文并触发回复
            for target_id in authorized_targets:
                is_remote = self._remote_bot_mgr and self._remote_bot_mgr.is_remote_bot(target_id)
                if target_id not in self.bots and not is_remote:
                    print(f"[ChatCore] Bot {target_id} 不存在，跳过")
                    continue

                # 获取被@的上下文历史
                mention_context = self._mention_mgr.get_mention_context_history(
                    chat_id, sender_bot_id, message, target_id
                )

                context_message = f"[被 @{sender_bot_id} 提及]\n\n{message}\n\n请回复上述消息。"

                print(f"[ChatCore] 触发级联回复: {sender_bot_id} -> {target_id}, "
                      f"上下文消息数: {len(mention_context)}")

                # 触发目标 Bot 回复
                result = await self.single_chat_with_context(
                    ws, target_id, context_message, chat_id,
                    is_group=True, thinking_mode=thinking_mode,
                    context_history=mention_context
                )

                # 保存级联回复到历史记录
                if result:
                    await self._history_mgr.add_to_history(chat_id, target_id, result, is_group=True)
        finally:
            # 恢复深度
            await self._mention_mgr.decrement_depth(chat_id)
