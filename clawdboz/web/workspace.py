#!/usr/bin/env python3
"""
Workspace 管理模块

实现多级 workspace 架构，支持 Bot 级和会话级 workspace 隔离。
"""

import os
from typing import Dict, List, Optional


def _get_default_workplace():
    """获取默认的 WORKPLACE 路径

    默认使用当前工作目录下的 WORKPLACE，与 BotManager 保持一致。
    这样用户在任何目录下运行代码，都会在该目录创建 WORKPLACE。
    """
    return os.path.abspath('WORKPLACE')


class WorkspaceManager:
    """
    Workspace 管理器

    实现新的多级 workspace 架构：
    - workplace_[bot_id]/           # Bot 级 workspace（共享资源）
      - logs/
      - user_files/
      - user_images/
      - .agents/skills/               # Bot 级 skills
      - w_[session_id]/             # 会话级 workspace
        - .agents/skills/             # 会话级 skills
        - .bot.md                  # 会话级系统提示词
        - .session_memory.md        # 会话级记忆
      - w_[session_id]_group/       # 群组 workspace（带 _group 后缀）
        - g_[session_id]/ -> w_[session_id]/  # 符号链接到其他成员的会话目录

    Args:
        base_workplace: 基础 workplace 目录路径
        bot_configs: Bot 配置字典 {bot_id: config}
    """

    def __init__(self, base_workplace: str, bot_configs: Dict[str, dict] = None):
        self.base_workplace = os.path.abspath(base_workplace)
        self.bot_configs = bot_configs or {}
        self._ensure_directories()

    def _ensure_directories(self):
        """确保基础目录结构存在"""
        os.makedirs(self.base_workplace, exist_ok=True)

    def get_bot_workspace(self, bot_id: str) -> str:
        """
        获取或创建 Bot 级 workspace

        Returns:
            Bot 级 workspace 路径
        """
        bot_dir = os.path.join(self.base_workplace, f"workplace_{bot_id}")

        # 创建基础目录结构
        for subdir in ['logs', 'user_files', 'user_images', '.agents/skills']:
            os.makedirs(os.path.join(bot_dir, subdir), exist_ok=True)

        # 创建 Bot 级 .bot.md（如果不存在）
        bots_md_path = os.path.join(bot_dir, '.bot.md')
        if not os.path.exists(bots_md_path):
            # 从 Bot 配置获取 system_prompt
            system_prompt = self.bot_configs.get(bot_id, {}).get('system_prompt', '')
            if system_prompt:
                with open(bots_md_path, 'w', encoding='utf-8') as f:
                    f.write(f"# Bot 配置\n\n{system_prompt}\n")

        return bot_dir

    def get_session_workspace(self, bot_id: str, session_id: str, is_group: bool = False) -> str:
        """
        获取或创建会话级 workspace

        会话目录只存储会话相关数据，不存储 .bot.md 和 .agents/skills/
        这些配置统一使用 Bot 级 workplace_[bot_id]/ 目录下的

        Args:
            bot_id: Bot ID
            session_id: 会话 ID
            is_group: 是否是群组模式

        Returns:
            会话级 workspace 路径
        """
        bot_dir = self.get_bot_workspace(bot_id)

        if is_group:
            # 群组会话：使用 g_[session_id]/ 目录
            # 处理 session_id 已经带有 g_ 前缀的情况
            if session_id.startswith('g_'):
                session_dir = os.path.join(bot_dir, session_id)
            else:
                session_dir = os.path.join(bot_dir, f"g_{session_id}")
        else:
            # 普通会话：使用 w_[session_id]/ 或 f_[session_id]/ 目录
            # 处理 session_id 已经带有 w_ 或 f_ 前缀的情况
            if session_id.startswith('w_') or session_id.startswith('f_'):
                session_dir = os.path.join(bot_dir, session_id)
            else:
                session_dir = os.path.join(bot_dir, f"w_{session_id}")

        # 只创建会话数据目录（不包含 .bot.md 和 .agents/skills/）
        for subdir in ['logs', 'temp']:
            os.makedirs(os.path.join(session_dir, subdir), exist_ok=True)

        # 创建软链接指向Bot级的.agents目录（让skills能正常工作）
        bot_agents_dir = os.path.join(bot_dir, '.agents')
        session_agents_link = os.path.join(session_dir, '.agents')
        if os.path.exists(bot_agents_dir) and not os.path.exists(session_agents_link):
            try:
                os.symlink(bot_agents_dir, session_agents_link, target_is_directory=True)
                print(f"[Workspace] 创建软链接: {session_agents_link} -> {bot_agents_dir}")
            except Exception as e:
                print(f"[Workspace] 创建软链接失败: {e}")

        return session_dir

    def get_group_workspace(self, session_id: str, member_bot_ids: list = None) -> str:
        """
        获取或创建群组 workspace

        群聊时所有 Bot 共享同一个工作目录：groupspace/g_[session_id]/
        群组目录只存储群聊相关数据，不存储 .bot.md 和 .agents/skills/

        Args:
            session_id: 群组会话 ID
            member_bot_ids: 参与群聊的 Bot ID 列表（仅用于日志记录）

        Returns:
            群组 workspace 路径
        """
        # 处理 session_id 已经带有 g_ 前缀的情况，避免双重前缀
        if session_id.startswith('g_'):
            group_dir = os.path.join(self.base_workplace, "groupspace", session_id)
        else:
            group_dir = os.path.join(self.base_workplace, "groupspace", f"g_{session_id}")

        # 只创建会话数据目录（不包含 .bot.md 和 .agents/skills/）
        for subdir in ['logs', 'temp', 'user_files', 'user_images']:
            os.makedirs(os.path.join(group_dir, subdir), exist_ok=True)

        # 注意：不再创建 .bot.md 和 .agents/skills/，Bot 使用自己 workplace 下的配置

        return group_dir

    def get_bot_ids_for_session(self, session_id: str) -> List[str]:
        """
        获取参与某个会话的所有 Bot ID

        通过查找 workplace_*/w_{session_id}/ 目录来确定

        Returns:
            Bot ID 列表
        """
        bot_ids = []
        for item in os.listdir(self.base_workplace):
            if item.startswith('workplace_'):
                bot_id = item[len('workplace_'):]
                session_dir = os.path.join(self.base_workplace, item, f"w_{session_id}")
                if os.path.exists(session_dir):
                    bot_ids.append(bot_id)
        return bot_ids
