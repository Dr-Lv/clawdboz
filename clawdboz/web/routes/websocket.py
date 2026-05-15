#!/usr/bin/env python3
"""
WebSocket Routes - WebSocket 路由模块

提供 WebSocket 聊天接口和消息处理功能。
支持单聊、群聊、流式输出和 Token 鉴权。
"""

from fastapi import WebSocket, WebSocketDisconnect, Query
from typing import Dict, Set
import asyncio


class WebSocketManager:
    """WebSocket 连接管理器

    管理 WebSocket 连接的建立、消息处理和断开。
    """

    def __init__(self, auth_token: str, bots: Dict[str, object],
                 chat_core, history_mgr, mention_mgr, server=None):
        """初始化 WebSocket 管理器

        Args:
            auth_token: 访问令牌
            bots: Bot 实例字典
            chat_core: ChatCore 实例
            history_mgr: ChatHistoryManager 实例
            mention_mgr: MentionManager 实例
            server: WebChatServer 实例（可选，用于远程bot支持）
        """
        self.auth_token = auth_token
        self.bots = bots
        self._chat_core = chat_core
        self._history_mgr = history_mgr
        self._mention_mgr = mention_mgr
        self._server = server

        # 当前活跃的 WebSocket 连接
        self._active_connections: Set[WebSocket] = set()

        # 设置 ChatCore 的广播回调（排除指定连接的广播）
        print(f"[WebSocketManager] 设置广播回调，chat_core has callback: {hasattr(self._chat_core, '_broadcast_callback')}")
        if hasattr(self._chat_core, '_broadcast_callback'):
            self._chat_core._broadcast_callback = self.broadcast_message_exclude
            print(f"[WebSocketManager] 广播回调已设置: {self._chat_core._broadcast_callback}")

    async def handle_chat_ws(self, websocket: WebSocket, token: str = Query(...)):
        """WebSocket 聊天接口

        消息协议:
        - 客户端发送: {"mode": "single|group", "bots": ["id1"], "message": "..."}
        - 服务端返回: {"type": "start|chunk|done|error", "bot_id": "...", ...}

        Args:
            websocket: WebSocket 连接
            token: 访问令牌
        """
        # Token 鉴权
        if token != self.auth_token:
            await websocket.close(code=4001, reason="Invalid token")
            return

        await websocket.accept()
        self._active_connections.add(websocket)

        try:
            while True:
                # 接收客户端消息
                print(f"[WebSocketManager] Waiting for message...")
                data = await websocket.receive_json()
                print(f"[WebSocketManager] Received message: {data}")
                await self._handle_message(websocket, data)
        except WebSocketDisconnect:
            print(f"[WebSocketManager] WebSocket disconnected")
        except Exception as e:
            print(f"[WebSocketManager] WebSocket 错误: {e}")
            import traceback
            traceback.print_exc()
        finally:
            self._active_connections.discard(websocket)

    async def _handle_message(self, ws: WebSocket, data: dict):
        """处理聊天消息

        Args:
            ws: WebSocket 连接
            data: 客户端消息 {"mode": "single|group", "bots": ["id"],
                  "message": "...", "chat_id": "...", "thinking_mode": true}
        """
        mode = data.get("mode", "single")
        bot_ids = data.get("bots", [])
        # 去重，防止前端发送重复的 bot_id
        bot_ids = list(dict.fromkeys(bot_ids))
        message = data.get("message", "")
        chat_id = data.get("chat_id") or "default"
        thinking_mode = data.get("thinking_mode", True)
        is_hidden = data.get("is_hidden", False)

        if not message:
            await ws.send_json({
                "type": "error",
                "error": "缺少必要参数: message"
            })
            return

        # 验证所有 Bot 存在
        for bot_id in bot_ids:
            print(f"[WebSocketManager] Checking if bot exists: {bot_id}")
            exists = self._bot_exists(bot_id)
            print(f"[WebSocketManager] Bot exists check result: {exists}")
            if not exists:
                await ws.send_json({
                    "type": "error",
                    "error": f"Bot '{bot_id}' 不存在"
                })
                return

        # 检查用户是否发送了 Bot @mention 授权指令
        all_bot_ids = list(self.bots.keys())
        await self._mention_mgr.check_authorization(message, chat_id, all_bot_ids)

        # 如果没有指定 bot，只保存消息不回复
        if not bot_ids:
            await self._history_mgr.add_to_history(chat_id, "user", message, is_group=True)
            return

        # 单聊或群聊
        print(f"[WebSocketManager] 路由消息: mode={mode}, chat_id={chat_id}, bot_ids={bot_ids}, is_hidden={is_hidden}")
        if mode == "single":
            await self._chat_core.single_chat(
                ws, bot_ids[0], message, chat_id, thinking_mode=thinking_mode, is_hidden=is_hidden
            )
        else:
            print(f"[WebSocketManager] 调用 group_chat")
            await self._chat_core.group_chat(
                ws, bot_ids, message, chat_id, thinking_mode=thinking_mode, is_hidden=is_hidden
            )
            print(f"[WebSocketManager] group_chat 完成")

    def _bot_exists(self, bot_id: str) -> bool:
        """检查 Bot 是否存在（包括远程bot）

        Args:
            bot_id: Bot ID

        Returns:
            是否存在
        """
        # 检查本地bot
        if bot_id in self.bots:
            return True

        # 检查远程bot（通过 server 实例）
        if self._server and hasattr(self._server, '_remote_bot_mgr'):
            remote_mgr = self._server._remote_bot_mgr
            if remote_mgr and remote_mgr.is_remote_bot(bot_id):
                # 检查是否在已添加的远程bot列表中
                added_bots = remote_mgr.get_added_remote_bots()
                return any(bot['full_bot_id'] == bot_id for bot in added_bots)

        return False

    async def broadcast_message(self, data: dict):
        """广播消息到所有连接的客户端

        Args:
            data: 消息数据
        """
        await self._do_broadcast(data)

    async def broadcast_message_exclude(self, data: dict, exclude_ws: WebSocket = None):
        """广播消息到所有连接的客户端（排除指定连接）

        Args:
            data: 消息数据
            exclude_ws: 要排除的 WebSocket 连接
        """
        await self._do_broadcast(data, exclude_ws)

    async def _do_broadcast(self, data: dict, exclude_ws: WebSocket = None):
        """执行广播

        Args:
            data: 消息数据
            exclude_ws: 要排除的 WebSocket 连接（可选）
        """
        # 隐藏消息不广播到前端
        if data.get('is_hidden'):
            print(f"[WebSocketManager] 隐藏消息，跳过广播: {data.get('type')}")
            return

        print(f"[WebSocketManager] 广播消息: type={data.get('type')}, connections={len(self._active_connections)}, exclude={exclude_ws is not None}")

        if not self._active_connections:
            print(f"[WebSocketManager] 消息无客户端接收: {data.get('type')}")
            return

        disconnected = set()
        sent_count = 0
        for ws in self._active_connections:
            # 跳过排除的连接
            if ws is exclude_ws:
                print(f"[WebSocketManager] 跳过排除的连接")
                continue
            try:
                await ws.send_json(data)
                sent_count += 1
            except Exception as e:
                print(f"[WebSocketManager] 发送消息失败: {e}")
                disconnected.add(ws)

        print(f"[WebSocketManager] 广播完成: 发送给 {sent_count} 个客户端")

        # 清理断开连接
        for ws in disconnected:
            self._active_connections.discard(ws)

    def get_active_connections_count(self) -> int:
        """获取当前活跃连接数

        Returns:
            活跃连接数
        """
        return len(self._active_connections)

    def update_bots(self, bots: Dict[str, object]):
        """更新 Bot 字典

        Args:
            bots: 新的 Bot 字典
        """
        self.bots = bots
        self._chat_core.update_bots(bots)
        self._mention_mgr.update_bots(bots)

    async def send_to_connection(self, ws: WebSocket, data: dict) -> bool:
        """发送消息到指定连接

        Args:
            ws: WebSocket 连接
            data: 消息数据

        Returns:
            是否发送成功
        """
        try:
            await ws.send_json(data)
            return True
        except Exception as e:
            print(f"[WebSocketManager] 发送消息到指定连接失败: {e}")
            self._active_connections.discard(ws)
            return False
