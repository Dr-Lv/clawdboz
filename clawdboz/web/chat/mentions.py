#!/usr/bin/env python3
"""
Mention Manager - Bot @mention 管理模块

提供 Bot @mention 的解析、权限管理和级联回复功能。
支持单向授权、双向授权和完全授权模式。
"""

import asyncio
import json
import os
import re
from typing import Dict, List, Optional


class MentionManager:
    """Bot @mention 管理器

    管理 Bot @mention 的权限控制、消息解析和级联回复触发。
    支持群聊和单聊两种模式。
    """

    def __init__(self, base_workplace: str, bots: Dict[str, object], max_history: int = 30):
        """初始化 mention 管理器

        Args:
            base_workplace: 基础 workplace 目录路径
            bots: Bot 实例字典 {bot_id: bot_instance}
            max_history: 最大历史记录数
        """
        self.base_workplace = base_workplace
        self.bots = bots
        self._max_history = max_history

        # Bot @mention 权限管理
        # {chat_id: {"allowed_directions": {sender_id: [target_ids]}, "depth": 0}}
        # - allowed_directions: 有向图，记录谁可以@谁
        # - depth: 当前@触发深度（防止无限循环）
        self._mention_permissions: Dict[str, dict] = {}
        self._mention_permissions_lock = asyncio.Lock()
        self._max_mention_depth = 5  # 最大@嵌套深度（默认值）

        # 历史记录引用（由外部传入）
        self._chat_history: Dict[str, list] = {}

    def set_remote_bot_manager(self, remote_bot_mgr):
        """设置远程 Bot 管理器

        Args:
            remote_bot_mgr: RemoteBotManager 实例
        """
        self._remote_bot_mgr = remote_bot_mgr

    def _get_bot_display_name(self, bot_id: str) -> str:
        """获取 Bot 的显示名称（支持本地和远程 Bot）

        Args:
            bot_id: Bot ID

        Returns:
            显示名称
        """
        # 先检查本地 Bot
        bot = self.bots.get(bot_id)
        if bot:
            return getattr(bot, 'name', None) or getattr(bot, '_bot_id', bot_id)

        # 再检查远程 Bot
        if hasattr(self, '_remote_bot_mgr') and self._remote_bot_mgr:
            remote_bots = self._remote_bot_mgr.get_all_bots({})
            remote_bot = remote_bots.get(bot_id)
            if remote_bot:
                return remote_bot.get('name', bot_id)

        return bot_id

    def set_chat_history(self, chat_history: Dict[str, list]):
        """设置历史记录引用

        Args:
            chat_history: 历史记录字典
        """
        self._chat_history = chat_history

    def set_max_mention_depth(self, depth: int):
        """设置最大@嵌套深度

        Args:
            depth: 最大嵌套深度（必须 >= 1）
        """
        try:
            depth = int(depth)
            if depth >= 1:
                self._max_mention_depth = depth
                print(f"[MentionManager] 最大@嵌套深度已设置为: {depth}")
            else:
                print(f"[MentionManager] 无效的深度值: {depth}，保持当前值 {self._max_mention_depth}")
        except (ValueError, TypeError):
            print(f"[MentionManager] 无效的深度值类型，保持当前值 {self._max_mention_depth}")

    def parse_mentions(self, message: str, chat_id: str) -> list:
        """解析消息中的 @提及

        支持以下格式:
        - @bot_id: 完整 Bot ID
        - @bot_name: Bot 显示名称
        - @short_id: Bot 名称首字母（短 ID）
        - @all: 提及所有 Bot

        Args:
            message: 消息内容
            chat_id: 聊天会话 ID

        Returns:
            被提及的 Bot ID 列表
        """
        mentioned_bots = []

        # 获取当前会话的所有 Bot（本地 + 远程）
        all_bot_ids = list(self.bots.keys())

        # 也获取远程 Bot IDs
        if hasattr(self, '_remote_bot_mgr') and self._remote_bot_mgr:
            try:
                remote_bots = self._remote_bot_mgr.get_all_bots({})
                for bot_id, bot_info in remote_bots.items():
                    if bot_info.get('type') == 'remote' and bot_id not in all_bot_ids:
                        all_bot_ids.append(bot_id)
            except Exception as e:
                print(f"[MentionManager] 获取远程Bot列表失败: {e}")

        print(f"[MentionManager] _parse_mentions - 可用 Bot IDs: {all_bot_ids}")
        print(f"[MentionManager] _parse_mentions - 消息内容: {message[:300]}...")

        # 检查 @all
        if re.search(r'@all(?:\s|$)', message, re.IGNORECASE):
            print(f"[MentionManager] _parse_mentions - 检测到 @all")
            return all_bot_ids

        # 检查每个本地 Bot（包括短 ID 匹配）
        for bot_id in all_bot_ids:
            bot = self.bots.get(bot_id)
            if not bot:
                continue

            # 获取 Bot 的显示名称（优先使用 name 属性）
            bot_display_name = getattr(bot, 'name', None)
            if not bot_display_name:
                bot_display_name = getattr(bot, '_bot_id', bot_id)

            # 检查 @bot_id 格式（完整 ID）
            pattern = rf'@{re.escape(bot_id)}(?:\s|$)'
            if re.search(pattern, message, re.IGNORECASE):
                print(f"[MentionManager] _parse_mentions - 检测到 @{bot_id}")
                mentioned_bots.append(bot_id)
                continue

            # 检查 @bot_display_name 格式
            if bot_display_name and bot_display_name != bot_id:
                pattern = rf'@{re.escape(bot_display_name)}(?:\s|$)'
                if re.search(pattern, message, re.IGNORECASE):
                    print(f"[MentionManager] _parse_mentions - 检测到名称 @{bot_display_name} -> {bot_id}")
                    mentioned_bots.append(bot_id)
                    continue

            # 检查短 ID（使用显示名称的首字母）
            short_id = bot_display_name[0] if bot_display_name else bot_id[0] if bot_id else ''
            if short_id and short_id != bot_id and short_id != bot_display_name:
                pattern_short = rf'@{re.escape(short_id)}(?:\s|$)'
                if re.search(pattern_short, message, re.IGNORECASE):
                    print(f"[MentionManager] _parse_mentions - 检测到短 ID @{short_id} -> {bot_id} ({bot_display_name})")
                    mentioned_bots.append(bot_id)
                    continue

        # 检查远程 Bot
        if hasattr(self, '_remote_bot_mgr') and self._remote_bot_mgr:
            try:
                remote_bots = self._remote_bot_mgr.get_all_bots({})
                for bot_id, bot_info in remote_bots.items():
                    if bot_info.get('type') != 'remote':
                        continue

                    bot_name = bot_info.get('name', bot_id)

                    # 检查 @bot_id 格式（完整 ID，如 instance_id:bot_id）
                    pattern = rf'@{re.escape(bot_id)}(?:\s|$)'
                    if re.search(pattern, message, re.IGNORECASE):
                        print(f"[MentionManager] _parse_mentions - 检测到远程Bot @{bot_id}")
                        mentioned_bots.append(bot_id)
                        continue

                    # 检查 @bot_name 格式
                    if bot_name and bot_name != bot_id:
                        pattern = rf'@{re.escape(bot_name)}(?:\s|$)'
                        if re.search(pattern, message, re.IGNORECASE):
                            print(f"[MentionManager] _parse_mentions - 检测到远程Bot名称 @{bot_name} -> {bot_id}")
                            mentioned_bots.append(bot_id)
                            continue

                    # 检查短 ID
                    short_id = bot_name[0] if bot_name else bot_id[0] if bot_id else ''
                    if short_id and short_id != bot_id and short_id != bot_name:
                        pattern_short = rf'@{re.escape(short_id)}(?:\s|$)'
                        if re.search(pattern_short, message, re.IGNORECASE):
                            print(f"[MentionManager] _parse_mentions - 检测到远程Bot短 ID @{short_id} -> {bot_id} ({bot_name})")
                            mentioned_bots.append(bot_id)
                            continue
            except Exception as e:
                print(f"[MentionManager] 检查远程Bot @mention 失败: {e}")

        return list(dict.fromkeys(mentioned_bots))  # 去重

    async def check_authorization(self, message: str, chat_id: str, bot_ids: list):
        """检查用户是否发送了 Bot @mention 授权指令（支持单向授权）

        支持的授权指令：
        - "允许 feishu-bot @ code-assistant 和 doc-writer"（单向）
        - "允许 feishu-bot 和 code-assistant 互相@"（双向）
        - "允许所有 Bot 协作"（完全双向）
        - "禁止 Bot 互相@" / "取消授权"

        Args:
            message: 用户消息
            chat_id: 聊天会话 ID
            bot_ids: 可用的 Bot ID 列表
        """
        async with self._mention_permissions_lock:
            if chat_id not in self._mention_permissions:
                self._mention_permissions[chat_id] = {
                    "allowed_directions": {},
                    "depth": 0
                }

            allowed = self._mention_permissions[chat_id]["allowed_directions"]
            original_allowed = {k: v.copy() for k, v in allowed.items()}

            # 1. 单向授权: "允许 feishu-bot @ code-assistant 和 doc-writer"
            single_direction_match = re.search(
                r'允许\s+(\w+(?:-\w+)*)\s*[@＠]\s*(.+?)(?:\s*$|禁止|允许所有|取消)',
                message, re.IGNORECASE
            )
            if single_direction_match and '互相' not in message and '协作' not in message:
                sender = single_direction_match.group(1).strip()
                targets_str = single_direction_match.group(2).strip()

                # 解析目标列表
                targets = []
                for bot_id in bot_ids:
                    if bot_id in targets_str:
                        targets.append(bot_id)

                if sender in bot_ids and targets:
                    allowed[sender] = targets
                    print(f"[MentionManager] 单向授权: {sender} 可以 @ {targets}")
                    return

            # 2. 双向授权: "允许 feishu-bot 和 code-assistant 互相@"
            if re.search(r'允许.*和.*(协作|互相@)', message) and '所有' not in message:
                mentioned_bots = []
                for bot_id in bot_ids:
                    if bot_id in message:
                        mentioned_bots.append(bot_id)

                # 互相授权
                for sender in mentioned_bots:
                    allowed[sender] = [b for b in mentioned_bots if b != sender]

                print(f"[MentionManager] 双向授权: {mentioned_bots} 可以互相 @")

            # 3. 完全授权: "允许所有 Bot 协作"
            elif re.search(r'允许.*所有.*[Bb]ot.*(协作|互相@)', message):
                for sender in bot_ids:
                    allowed[sender] = [b for b in bot_ids if b != sender]
                print(f"[MentionManager] 完全授权: 所有 Bot 可以互相 @")

            # 4. 取消授权
            elif re.search(r'(禁止|取消|关闭).*[Bb]ot.*(协作|互相@|@)', message):
                allowed.clear()
                print(f"[MentionManager] 取消所有授权")

            # 如果授权列表发生变化，打印当前状态
            if allowed != original_allowed:
                if allowed:
                    print(f"[MentionManager] 当前授权状态:")
                    for sender, targets in allowed.items():
                        print(f"  - {sender} 可以 @ {targets}")
                else:
                    print(f"[MentionManager] 当前没有 Bot 被授权 @mention")

    async def get_authorized_targets(self, sender_bot_id: str, chat_id: str,
                                     mentioned_bots: list) -> list:
        """获取有权限的 @ 目标列表

        Args:
            sender_bot_id: 发送者 Bot ID
            chat_id: 聊天会话 ID
            mentioned_bots: 被提及的 Bot 列表

        Returns:
            有权限的 Bot ID 列表
        """
        # 从文件加载权限设置（与前端保存的权限同步）
        file_permissions = {}
        permissions_file = os.path.join(
            self.base_workplace, "groupspace", f"g_{chat_id}", ".permissions.json"
        )
        print(f"[MentionManager] 查找权限文件: {permissions_file}")
        print(f"[MentionManager] 权限文件是否存在: {os.path.exists(permissions_file)}")

        if os.path.exists(permissions_file):
            try:
                with open(permissions_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    file_permissions = data.get("permissions", {})
                    print(f"[MentionManager] 从文件加载权限: {file_permissions}")
            except Exception as e:
                print(f"[MentionManager] 加载权限文件失败: {e}")

        async with self._mention_permissions_lock:
            if chat_id not in self._mention_permissions:
                self._mention_permissions[chat_id] = {
                    "allowed_directions": {},
                    "depth": 0
                }

            permissions = self._mention_permissions[chat_id]
            # 合并内存权限和文件权限（文件权限优先）
            allowed_directions = permissions.get("allowed_directions", {})
            if file_permissions:
                allowed_directions = file_permissions
                print(f"[MentionManager] 使用文件权限: {allowed_directions}")

            # 检查深度限制
            current_depth = permissions.get("depth", 0)
            if current_depth >= self._max_mention_depth:
                print(f"[MentionManager] 达到最大 @ 嵌套深度 ({self._max_mention_depth})，停止级联")
                return []

            # 过滤出有权限的 @目标
            authorized_targets = []
            for target_id in mentioned_bots:
                # 用户消息（sender_bot_id 为 None 或 user）总是可以 @
                if sender_bot_id == "user":
                    authorized_targets.append(target_id)
                    continue

                # 获取 Bot 的显示名称用于短 ID 匹配（支持本地和远程 Bot）
                sender_name = self._get_bot_display_name(sender_bot_id)
                target_name = self._get_bot_display_name(target_id)

                # Bot 消息需要检查权限
                # 尝试完整 ID 匹配
                has_permission = False
                if sender_bot_id in allowed_directions and \
                   target_id in allowed_directions[sender_bot_id]:
                    has_permission = True
                elif sender_name in allowed_directions and \
                     (target_name in allowed_directions[sender_name] or
                      target_id in allowed_directions[sender_name]):
                    has_permission = True
                else:
                    # 尝试短 ID 匹配（使用显示名称的首字母）
                    sender_short = sender_name[0] if sender_name else ''
                    target_short = target_name[0] if target_name else ''
                    if sender_short in allowed_directions:
                        allowed_targets_short = allowed_directions[sender_short]
                        if target_short in allowed_targets_short or \
                           target_id in allowed_targets_short or \
                           target_name in allowed_targets_short:
                            has_permission = True
                            print(f"[MentionManager] 短 ID 权限匹配: "
                                  f"{sender_bot_id}({sender_short}) -> {target_id}({target_short})")

                if has_permission:
                    authorized_targets.append(target_id)
                else:
                    print(f"[MentionManager] Bot {sender_bot_id}({sender_name[0]}) "
                          f"无权 @ {target_id}({target_name[0]})，当前权限: {allowed_directions}")

            return authorized_targets

    async def increment_depth(self, chat_id: str) -> int:
        """增加 @ 嵌套深度

        Args:
            chat_id: 聊天会话 ID

        Returns:
            增加后的深度
        """
        async with self._mention_permissions_lock:
            if chat_id not in self._mention_permissions:
                self._mention_permissions[chat_id] = {
                    "allowed_directions": {},
                    "depth": 0
                }
            self._mention_permissions[chat_id]["depth"] += 1
            return self._mention_permissions[chat_id]["depth"]

    async def decrement_depth(self, chat_id: str) -> int:
        """减少 @ 嵌套深度

        Args:
            chat_id: 聊天会话 ID

        Returns:
            减少后的深度
        """
        async with self._mention_permissions_lock:
            if chat_id not in self._mention_permissions:
                return 0
            self._mention_permissions[chat_id]["depth"] = \
                max(0, self._mention_permissions[chat_id]["depth"] - 1)
            return self._mention_permissions[chat_id]["depth"]

    async def get_current_depth(self, chat_id: str) -> int:
        """获取当前 @ 嵌套深度

        Args:
            chat_id: 聊天会话 ID

        Returns:
            当前深度
        """
        async with self._mention_permissions_lock:
            if chat_id not in self._mention_permissions:
                return 0
            return self._mention_permissions[chat_id].get("depth", 0)

    def get_mention_context_history(self, chat_id: str, sender_bot_id: str,
                                    message: str, target_bot_id: str) -> list:
        """获取被@ Bot 的上下文历史记录

        截取方式：
        1. 从本次被@的消息开始（即 sender_bot_id 发送的包含 @target_bot_id 的消息）
        2. 逐个向上追溯历史消息
        3. 一直追溯到上一次被@的消息截止（不包含上一次被@的消息本身）
        4. 如果找不到上一次被@，就一直追溯到开头

        Args:
            chat_id: 聊天会话 ID
            sender_bot_id: 发送@消息的 Bot ID
            message: 包含@的完整消息内容
            target_bot_id: 被@的目标 Bot ID

        Returns:
            截取的历史记录列表（按时间正序，从旧到新）
        """
        # 获取完整历史记录
        history = self._chat_history.get(chat_id, [])
        if not history:
            print(f"[MentionContext] 无历史记录: chat_id={chat_id}")
            return []

        print(f"[MentionContext] 总历史记录数: {len(history)}")

        # 找到本次被@的消息索引（从后往前找，sender_bot_id 发送的包含 @target_bot_id 的消息）
        # 如果 sender_bot_id 是 "user"，则查找用户发送的包含@的消息
        current_mention_idx = -1
        for i in range(len(history) - 1, -1, -1):
            msg = history[i]
            sender = msg.get('sender', '')
            # 匹配 sender：如果是 "user" 则匹配 user，否则匹配特定 bot_id
            if sender_bot_id == "user":
                if sender != "user":
                    continue
            elif sender != sender_bot_id:
                continue

            content = msg.get('content', '')
            # 检查是否包含 @target_bot_id
            # 支持格式: @bot_id, @bot_name, @short_id
            bot_name = self._get_bot_display_name(target_bot_id)
            short_id = bot_name[0] if bot_name else target_bot_id[0] if target_bot_id else ''

            patterns = [
                rf'@{re.escape(target_bot_id)}(?:\s|$)',
                rf'@{re.escape(bot_name)}(?:\s|$)',
            ]
            if short_id and short_id != target_bot_id and short_id != bot_name:
                patterns.append(rf'@{re.escape(short_id)}(?:\s|$)')

            for pattern in patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    current_mention_idx = i
                    print(f"[MentionContext] 找到本次被@消息: idx={i}, sender={sender_bot_id}")
                    break
            if current_mention_idx != -1:
                break

        if current_mention_idx == -1:
            print(f"[MentionContext] 未找到本次被@消息")
            return []

        # 从 current_mention_idx 往前找，找到上一次 target_bot_id 被@的位置
        prev_mention_idx = -1
        for i in range(current_mention_idx - 1, -1, -1):
            msg = history[i]
            content = msg.get('content', '')
            sender = msg.get('sender', '')

            # 检查这条消息是否@了 target_bot_id
            bot_name = self._get_bot_display_name(target_bot_id)
            short_id = bot_name[0] if bot_name else target_bot_id[0] if target_bot_id else ''

            patterns = [
                rf'@{re.escape(target_bot_id)}(?:\s|$)',
                rf'@{re.escape(bot_name)}(?:\s|$)',
            ]
            if short_id and short_id != target_bot_id and short_id != bot_name:
                patterns.append(rf'@{re.escape(short_id)}(?:\s|$)')

            for pattern in patterns:
                if re.search(pattern, content, re.IGNORECASE):
                    prev_mention_idx = i
                    print(f"[MentionContext] 找到上一次被@消息: idx={i}, sender={sender}")
                    break
            if prev_mention_idx != -1:
                break

        # 截取上下文：从上一次被@之后（或开头）到本次被@消息（包含）
        start_idx = prev_mention_idx + 1 if prev_mention_idx != -1 else 0
        end_idx = current_mention_idx + 1  # 包含本次被@的消息

        context_history = history[start_idx:end_idx]
        print(f"[MentionContext] 截取范围: [{start_idx}:{end_idx}], 共 {len(context_history)} 条消息")

        return context_history

    def update_bots(self, bots: Dict[str, object]):
        """更新 Bot 字典

        Args:
            bots: 新的 Bot 字典
        """
        self.bots = bots

    def build_context_prompt(self, history: list, current_message: str, bot_id: str) -> str:
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
        final_prompt = "\n".join(context_parts)
        print(f"[BuildContext] 构建的prompt:\n{final_prompt[:500]}...")
        return final_prompt
