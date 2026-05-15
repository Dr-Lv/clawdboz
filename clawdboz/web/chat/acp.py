#!/usr/bin/env python3
"""
ACP Client Manager - ACP 客户端管理模块

提供会话级 ACPClient 的管理功能，确保不同会话之间的上下文隔离。
支持群聊和单聊两种模式的 ACP 客户端管理。
"""

import asyncio
import os
from typing import Dict, Optional, Tuple


class ACPClientManager:
    """ACP 客户端管理器

    管理会话级 ACPClient 的创建、获取和清理。
    每个 (session_id, bot_id) 组合对应一个独立的 ACP session。
    """

    def __init__(self, base_workplace: str, bots: Dict[str, object], workspace_mgr):
        """初始化 ACP 客户端管理器

        Args:
            base_workplace: 基础 workplace 目录路径
            bots: Bot 实例字典 {bot_id: bot_instance}
            workspace_mgr: WorkspaceManager 实例
        """
        self.base_workplace = base_workplace
        self.bots = bots
        self._workspace_mgr = workspace_mgr

        # 会话级 ACPClient 管理：{(session_id, bot_id): {'client': ACPClient, 'system_prompt': str}}
        self._session_acp_clients: Dict[Tuple[str, str], dict] = {}
        self._session_acp_lock = asyncio.Lock()

    async def get_or_create_client(self, session_id: str, bot_id: str,
                                   is_group: bool = False) -> Optional[object]:
        """获取或创建会话级的 ACPClient

        这是实现会话级隔离的核心方法。每个 (session_id, bot_id) 组合
        对应一个独立的 ACP session，确保上下文不会在不同 session 之间混合。

        群聊模式下，所有 Bot 共享同一个 workspace：groupspace/g_[session_id]/

        Args:
            session_id: 前端会话 ID
            bot_id: Bot ID
            is_group: 是否是群组模式

        Returns:
            ACPClient 实例，或 None（如果创建失败）
        """
        key = (session_id, bot_id)

        # 计算当前期望的 system_prompt 和 acp_client_id
        bot = self.bots.get(bot_id)
        expected_system_prompt = getattr(bot, '_system_prompt', None) if bot else None
        expected_acp_client_id = getattr(bot, '_acp_client_id', None) if bot else None

        async with self._session_acp_lock:
            # 检查是否已存在
            if key in self._session_acp_clients:
                client_info = self._session_acp_clients[key]
                # 兼容旧格式：直接存 client 对象
                if not isinstance(client_info, dict):
                    client_info = {'client': client_info, 'system_prompt': None, 'acp_client_id': None}
                    self._session_acp_clients[key] = client_info

                client = client_info['client']
                old_system_prompt = client_info.get('system_prompt')
                old_acp_client_id = client_info.get('acp_client_id')

                # 检查连接是否还活跃
                is_alive = hasattr(client, 'process') and client.process and client.process.poll() is None
                # 检查 system_prompt 是否变化
                prompt_changed = old_system_prompt != expected_system_prompt
                # 检查 acp_client_id 是否变化
                acp_client_changed = old_acp_client_id != expected_acp_client_id

                if is_alive and not prompt_changed and not acp_client_changed:
                    return client
                else:
                    if prompt_changed:
                        print(f"[ACPManager] ACPClient {key} system_prompt 已变化，重新创建")
                    elif acp_client_changed:
                        print(f"[ACPManager] ACPClient {key} acp_client_id 已变化 ({old_acp_client_id} -> {expected_acp_client_id})，重新创建")
                    else:
                        print(f"[ACPManager] ACPClient {key} 已断开，重新创建")
                    # 关闭旧客户端
                    try:
                        if hasattr(client, 'close'):
                            client.close()
                        elif hasattr(client, 'process') and client.process:
                            client.process.terminate()
                    except Exception as e:
                        print(f"[ACPManager] 关闭旧 ACPClient {key} 失败: {e}")
                    del self._session_acp_clients[key]

            # 创建新的 ACPClient
            try:
                from ...communication.acp_client import ACPClient

                # 确定工作目录
                if is_group:
                    # 群聊模式：所有 Bot 共享同一个群组 workspace
                    session_work_dir = self._workspace_mgr.get_group_workspace(session_id)
                    print(f"[ACPManager] 群聊模式，使用共享 workspace: {session_work_dir}")
                else:
                    # 单聊模式：每个 Bot 有自己的会话 workspace
                    session_work_dir = self._workspace_mgr.get_session_workspace(
                        bot_id, session_id, is_group=False
                    )

                # 获取 Bot workplace（用于加载 .bot.md 和 skills）
                bot_work_dir = self._workspace_mgr.get_bot_workspace(bot_id)

                print(f"[ACPManager] 创建 ACPClient: session={session_id}, bot={bot_id}")
                print(f"[ACPManager]   工作目录: {session_work_dir}")
                print(f"[ACPManager]   配置目录: {bot_work_dir}")

                # 获取 Bot 指定的 ACP 客户端 ID
                bot_acp_client_id = getattr(bot, '_acp_client_id', None) if bot else None
                if bot_acp_client_id:
                    print(f"[ACPManager] Bot {bot_id} 指定使用 ACP 客户端: {bot_acp_client_id}")

                # 创建 ACPClient，传入：
                # - session_work_dir: 当前会话的工作目录（用于读写文件）
                # - bot_work_dir: Bot 配置目录（用于加载 .bot.md 和 skills）
                # - acp_client_id: Bot 指定的 ACP 客户端 ID
                client = ACPClient(
                    bot_ref=bot,
                    session_work_dir=session_work_dir,
                    bot_work_dir=bot_work_dir,
                    system_prompt=expected_system_prompt,
                    acp_client_id=bot_acp_client_id
                )

                self._session_acp_clients[key] = {
                    'client': client,
                    'system_prompt': expected_system_prompt,
                    'acp_client_id': bot_acp_client_id
                }
                print(f"[ACPManager] ACPClient 创建成功: session_id={client.session_id}")
                return client

            except Exception as e:
                print(f"[ACPManager] 创建会话级 ACPClient 失败: {e}")
                import traceback
                traceback.print_exc()
                return None

    async def cleanup_client(self, session_id: str, bot_id: str = None):
        """清理会话级的 ACPClient

        Args:
            session_id: 前端会话 ID
            bot_id: 如果指定，只清理该 Bot 的客户端；否则清理该 session 的所有客户端
        """
        async with self._session_acp_lock:
            keys_to_remove = []
            for key in self._session_acp_clients:
                if key[0] == session_id:
                    if bot_id is None or key[1] == bot_id:
                        keys_to_remove.append(key)

            for key in keys_to_remove:
                client_info = self._session_acp_clients[key]
                client = client_info['client'] if isinstance(client_info, dict) else client_info
                try:
                    # 关闭 ACP 连接
                    if hasattr(client, 'close'):
                        client.close()
                    elif hasattr(client, 'process') and client.process:
                        client.process.terminate()
                except Exception as e:
                    print(f"[ACPManager] 关闭 ACPClient {key} 失败: {e}")
                del self._session_acp_clients[key]
                print(f"[ACPManager] 已清理 ACPClient: {key}")

    async def get_client(self, session_id: str, bot_id: str) -> Optional[object]:
        """获取已存在的 ACPClient（不创建新的）

        Args:
            session_id: 前端会话 ID
            bot_id: Bot ID

        Returns:
            ACPClient 实例，或 None（如果不存在）
        """
        key = (session_id, bot_id)
        async with self._session_acp_lock:
            client_info = self._session_acp_clients.get(key)
            if client_info:
                client = client_info['client'] if isinstance(client_info, dict) else client_info
                # 检查连接是否还活跃
                if hasattr(client, 'process') and client.process and client.process.poll() is None:
                    return client
                else:
                    # 客户端已断开，移除
                    del self._session_acp_clients[key]
            return None

    async def cleanup_all_clients(self):
        """清理所有 ACPClient"""
        async with self._session_acp_lock:
            keys_to_remove = list(self._session_acp_clients.keys())

            for key in keys_to_remove:
                client_info = self._session_acp_clients[key]
                client = client_info['client'] if isinstance(client_info, dict) else client_info
                try:
                    # 关闭 ACP 连接
                    if hasattr(client, 'close'):
                        client.close()
                    elif hasattr(client, 'process') and client.process:
                        client.process.terminate()
                except Exception as e:
                    print(f"[ACPManager] 关闭 ACPClient {key} 失败: {e}")
                del self._session_acp_clients[key]
                print(f"[ACPManager] 已清理 ACPClient: {key}")

    def update_bots(self, bots: Dict[str, object]):
        """更新 Bot 字典

        Args:
            bots: 新的 Bot 字典
        """
        self.bots = bots

    def get_active_clients_count(self) -> int:
        """获取当前活跃的 ACPClient 数量

        Returns:
            活跃客户端数量
        """
        return len(self._session_acp_clients)

    def get_active_sessions(self) -> list:
        """获取当前活跃的会话 ID 列表

        Returns:
            会话 ID 列表
        """
        return list(set(key[0] for key in self._session_acp_clients.keys()))
