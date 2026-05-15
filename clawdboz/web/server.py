#!/usr/bin/env python3
"""
WebChatServer - FastAPI WebSocket 聊天服务器 (v3.0)
支持单聊、群聊、流式输出、会话级 workspace 隔离

这是重构后的入口文件，使用模块化组件。
"""

import asyncio
import json
import os
import secrets
import sys
import threading
import time
from pathlib import Path
from typing import Dict, Optional

# 延迟导入 FastAPI，未安装时给出友好提示
try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import JSONResponse
    import uvicorn
except ImportError:
    print("[ERROR] 缺少 web 依赖，请安装: pip install clawdboz[web]")
    print("       或: pip install fastapi uvicorn websockets")
    sys.exit(1)

from .workspace import WorkspaceManager
from .chat.history import ChatHistoryManager
from .chat.acp import ACPClientManager
from .chat.mentions import MentionManager
from .chat.core import ChatCore
from .routes.websocket import WebSocketManager
from .routes.internal import setup_internal_routes
from .routes.bots import setup_bots_routes
from .routes.moments import setup_moments_routes
from .routes.file import setup_file_routes
from .routes.sessions.meta import setup_session_meta_routes
from .routes.sessions.core import setup_session_core_routes
from .routes.sessions.scheduler import setup_session_scheduler_routes
from .routes.feishu import setup_feishu_routes
from ..remote.config import RemoteConfig
from ..remote.manager import RemoteBotManager
from .routes.search import router as search_router


def _get_default_workplace():
    """获取默认的 WORKPLACE 路径"""
    return os.path.abspath('WORKPLACE')


class WebChatServer:
    """
    Web 聊天服务器 (v3.0) - 支持会话级 workspace 隔离

    提供 WebSocket 接口供前端连接，支持：
    - 单聊：一个 Bot 回复
    - 群聊：多个 Bot 同时回复（带上下文）
    - 流式输出：实时显示思考过程
    - Token 鉴权：简单的访问控制
    - MCP 工具调用：支持定时任务发送消息/文件到 Web Chat
    - 会话级隔离：每个 session 拥有独立的 ACP session 和 workspace
    """

    def __init__(self, bots: Dict[str, object], port: int = 8080, auth_token: str = None,
                 base_workplace: str = None):
        """
        初始化 Web 服务器

        Args:
            bots: {"bot_id": bot_instance, ...}
            port: 服务端口
            auth_token: 访问密码，None 则自动生成
            base_workplace: 基础 workplace 目录路径（默认使用临时目录）
        """
        self.bots = bots
        self.port = port
        self.auth_token = auth_token or secrets.token_urlsafe(16)
        self.app = FastAPI(title="Clawdboz Web Chat")

        # 基础 workplace 目录
        if base_workplace is None:
            base_workplace = _get_default_workplace()
        self.base_workplace = os.path.abspath(base_workplace)

        # 记录服务器启动时的基准目录
        self._base_dir = os.path.abspath(os.getcwd())

        # 设置全局环境变量
        os.environ['MOMENTS_WORKPLACE'] = self.base_workplace
        print(f"[WebChatServer] 设置 MOMENTS_WORKPLACE={self.base_workplace}")

        # 提取 Bot 配置用于创建 workspace
        bot_configs = {}
        for bot_id, bot in bots.items():
            bot_configs[bot_id] = {
                'system_prompt': getattr(bot, '_system_prompt', ''),
                'app_id': getattr(bot, 'app_id', ''),
                'app_secret': getattr(bot, 'app_secret', ''),
            }

            # 启动 Bot 心跳
            if hasattr(bot, '_bot') and bot._bot:
                bot._bot._bot_id = bot_id
                if hasattr(bot._bot, '_start_heart_beat'):
                    if hasattr(bot._bot, '_stop_heart_beat'):
                        bot._bot._stop_heart_beat()
                    bot._bot._start_heart_beat()
                    print(f"[WebServer] 已启动 Bot {bot_id} 的心跳线程")

        # 初始化管理器
        self._workspace_mgr = WorkspaceManager(base_workplace, bot_configs)
        self._history_mgr = ChatHistoryManager(base_workplace, bots)
        self._acp_mgr = ACPClientManager(base_workplace, bots, self._workspace_mgr)
        self._mention_mgr = MentionManager(base_workplace, bots)

        # 从 config.json 读取并设置最大@嵌套深度
        try:
            config_path = os.path.join(os.path.dirname(base_workplace), 'config.json')
            if os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                chat_config = config.get('chat', {})
                if 'max_mention_depth' in chat_config:
                    self._mention_mgr.set_max_mention_depth(chat_config['max_mention_depth'])
        except Exception as e:
            print(f"[WebServer] 读取 config.json 中的 max_mention_depth 失败: {e}")

        # 设置历史记录引用
        self._mention_mgr.set_chat_history(self._history_mgr._chat_history)

        # 初始化聊天核心
        self._chat_core = ChatCore(
            bots, base_workplace,
            self._workspace_mgr, self._history_mgr,
            self._mention_mgr, self._acp_mgr
        )

        # 初始化 WebSocket 管理器
        self._ws_mgr = WebSocketManager(
            self.auth_token, bots,
            self._chat_core, self._history_mgr, self._mention_mgr,
            server=self  # 传入server实例以支持远程bot
        )

        # MCP 服务器实例
        self._mcp_server = None

        # 初始化 Feishu Bot 集成
        self._feishu_manager = None
        self._init_feishu_bots()

        # 初始化远程 Bot 管理器
        self._remote_bot_mgr: Optional[RemoteBotManager] = None
        self._init_remote_bots()

        # 文件上传目录
        self.upload_dir = os.path.join(os.path.dirname(__file__), "uploads")
        os.makedirs(self.upload_dir, exist_ok=True)

        # 设置路由
        self._setup_routes()

    def set_mcp_server(self, mcp_server):
        """设置 MCP 服务器实例"""
        self._mcp_server = mcp_server
        if mcp_server:
            mcp_server.set_web_chat_server(self)

    def _init_feishu_bots(self):
        """初始化 Feishu Bot 集成"""
        print(f"[WebServer] 初始化 Feishu Bot 集成，共 {len(self.bots)} 个 Bot")
        try:
            from .feishu_integration import FeishuBotManager

            self._feishu_manager = FeishuBotManager(workplace_root=self.base_workplace)

            # 从每个 Bot 的配置中提取飞书凭证
            for bot_id, bot in self.bots.items():
                print(f"[WebServer] 检查 Bot '{bot_id}' 的飞书配置...")
                feishu_config = self._get_feishu_config(bot)
                print(f"[WebServer] Bot '{bot_id}' 飞书配置: {feishu_config}")
                if feishu_config:
                    self._feishu_manager.register(
                        bot_id=bot_id,
                        app_id=feishu_config['app_id'],
                        app_secret=feishu_config['app_secret'],
                        verification_token=feishu_config.get('verification_token', ''),
                        encrypt_key=feishu_config.get('encrypt_key', ''),
                        on_message_callback=self._on_feishu_message
                    )

            # 启动所有 Feishu Bot
            self._feishu_manager.start_all()

            # 设置 Feishu 管理器到 ChatCore
            self._chat_core.set_feishu_manager(self._feishu_manager)

        except Exception as e:
            print(f"[WebServer] 初始化 Feishu Bot 失败: {e}")
            import traceback
            traceback.print_exc()

    def _get_feishu_config(self, bot) -> Optional[Dict]:
        """从 Bot 实例获取飞书配置"""
        try:
            bot_id = getattr(bot, '_bot_id', 'default')
            bot_work_dir = getattr(bot, '_work_dir', None)

            # 优先从 .bot.md 读取飞书配置（因为 config.json 会被重置）
            bot_md_path = None
            if bot_work_dir and os.path.exists(bot_work_dir):
                bot_md_path = os.path.join(bot_work_dir, '.bot.md')

            if bot_md_path and os.path.exists(bot_md_path):
                feishu_cfg = {}
                with open(bot_md_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith('Feishu App ID:'):
                            app_id = line.replace('Feishu App ID:', '').strip()
                            if app_id:
                                feishu_cfg['app_id'] = app_id
                        elif line.startswith('Feishu App Secret:'):
                            app_secret = line.replace('Feishu App Secret:', '').strip()
                            if app_secret:
                                feishu_cfg['app_secret'] = app_secret
                        elif line.startswith('Verification Token:'):
                            token = line.replace('Verification Token:', '').strip()
                            if token:
                                feishu_cfg['verification_token'] = token
                        elif line.startswith('Encrypt Key:'):
                            key = line.replace('Encrypt Key:', '').strip()
                            if key:
                                feishu_cfg['encrypt_key'] = key

                if feishu_cfg.get('app_id') and feishu_cfg.get('app_secret'):
                    print(f"[WebServer] 从 .bot.md 读取到飞书配置: {bot_id}")
                    return feishu_cfg

            # 其次从 config.json (bots.{bot_id}.feishu) 读取
            config_path = None
            if bot_work_dir and os.path.exists(bot_work_dir):
                config_path = os.path.join(bot_work_dir, 'config.json')

            if config_path and os.path.exists(config_path):
                with open(config_path, 'r', encoding='utf-8') as f:
                    cfg = json.load(f)
                bots_config = cfg.get('bots', {})
                if bot_id in bots_config:
                    feishu_cfg = bots_config[bot_id].get('feishu', {})
                    if feishu_cfg.get('app_id') and feishu_cfg.get('app_secret'):
                        return feishu_cfg

            # 最后从 Bot 实例属性读取
            app_id = getattr(bot, 'app_id', None) or getattr(bot, '_app_id', None)
            app_secret = getattr(bot, 'app_secret', None) or getattr(bot, '_app_secret', None)

            if app_id and app_secret and app_id != 'webchat-bot':
                return {
                    'app_id': app_id,
                    'app_secret': app_secret,
                    'verification_token': getattr(bot, 'verification_token', ''),
                    'encrypt_key': getattr(bot, 'encrypt_key', '')
                }

            return None
        except Exception as e:
            print(f"[WebServer] 获取飞书配置失败: {e}")
            return None

    def _init_remote_bots(self):
        """初始化远程 Bot 功能"""
        try:
            # 加载远程功能配置
            config_path = os.path.join(os.path.dirname(self.base_workplace), 'config.json')
            remote_config = RemoteConfig.load_from_config_file(Path(config_path))

            print(f"[WebServer] 远程配置加载: enabled={remote_config.enabled}, registry={remote_config.registry_url}")

            if remote_config.enabled:
                print(f"[WebServer] 初始化远程 Bot 管理 (registry={remote_config.registry_url})")

                # 生成实例 ID（使用 hostname + port）
                import socket
                hostname = socket.gethostname()
                instance_id = f"{hostname}-{self.port}"
                self.instance_id = instance_id

                self._remote_bot_mgr = RemoteBotManager(
                    instance_id=instance_id,
                    config=remote_config,
                    base_workplace=self.base_workplace,
                    bots=self.bots
                )
                # Pass dependencies needed for bot calls
                self._remote_bot_mgr.set_dependencies(
                    acp_mgr=self._chat_core._acp_mgr,
                    workspace_mgr=self._chat_core._workspace_mgr
                )

                # 设置远程 Bot 管理器到 ChatCore
                self._chat_core.set_remote_bot_manager(self._remote_bot_mgr)

                # 设置远程 Bot 管理器到 MentionManager（支持群聊@远程Bot）
                self._mention_mgr.set_remote_bot_manager(self._remote_bot_mgr)

                print(f"[WebServer] 设置远程 Bot 管理器启动任务...")
                self._remote_startup_called = False
                # 注册启动事件
                @self.app.on_event("startup")
                async def startup_remote_manager():
                    if self._remote_startup_called:
                        print(f"[WebServer] Startup event triggered again, skipping duplicate start")
                        return
                    self._remote_startup_called = True
                    print(f"[WebServer] Startup event triggered, starting remote manager...")
                    await self._start_remote_bot_manager()

                # 注册关闭事件
                @self.app.on_event("shutdown")
                async def shutdown_remote_manager():
                    await self._stop_remote_bot_manager()

                print(f"[WebServer] 远程 Bot 管理器将在服务器启动后自动启动")

            else:
                print(f"[WebServer] 远程 Bot 功能未启用")

        except Exception as e:
            print(f"[WebServer] 初始化远程 Bot 失败: {e}")
            import traceback
            traceback.print_exc()

    async def _start_remote_bot_manager(self):
        """启动远程 Bot 管理器"""
        print(f"[WebServer] _start_remote_bot_manager called, _remote_bot_mgr={self._remote_bot_mgr}")
        if self._remote_bot_mgr:
            await self._remote_bot_mgr.start()
        else:
            print(f"[WebServer] ERROR: _remote_bot_mgr is None!")

    async def _stop_remote_bot_manager(self):
        """停止远程 Bot 管理器"""
        if self._remote_bot_mgr:
            await self._remote_bot_mgr.stop()

    def _on_feishu_message(self, bot_id: str, chat_id: str, sender: str, text: str, feishu_integration):
        """处理飞书消息回调"""
        print(f"[WebServer] 飞书消息: Bot={bot_id}, Chat={chat_id}, Sender={sender}")

        # 使用 feishu_{chat_id} 格式作为会话 ID
        session_id = f"feishu_{chat_id}"

        # 广播到所有 WebSocket 连接（通知前端有新消息）
        import asyncio
        asyncio.create_task(self._broadcast_feishu_message({
            'type': 'feishu_message',
            'bot_id': bot_id,
            'chat_id': session_id,
            'sender': sender,
            'text': text,
            'session_type': 'feishu'
        }))

        # 调用 Bot 进行回复
        asyncio.create_task(self._handle_feishu_bot_reply(
            bot_id, chat_id, sender, text, feishu_integration
        ))

    async def _handle_feishu_bot_reply(self, bot_id: str, chat_id: str, sender: str, text: str, feishu_integration):
        """处理飞书消息的 Bot 回复"""
        try:
            # 使用 f_ 前缀标识飞书会话
            session_id = f"f_{chat_id}"

            # 获取 Bot 实例
            bot = self.bots.get(bot_id)
            if not bot:
                print(f"[WebServer] Bot {bot_id} 不存在")
                return

            # 获取历史记录
            history = await self._load_session_history(session_id, is_group=False, bot_id=bot_id)

            # 收集 Bot 回复内容
            full_reply = ""

            async def send_chunk(chunk_text: str, is_thinking: bool = False):
                """收集 Bot 回复内容（每个 chunk 包含完整内容，不是增量）"""
                nonlocal full_reply
                if not is_thinking:
                    full_reply = chunk_text  # 直接使用最新 chunk（包含完整内容）

            # 调用 Bot 进行回复
            print(f"[WebServer] 调用 Bot {bot_id} 回复飞书消息...")
            result = await self._chat_core._call_bot_chat(
                bot=bot,
                message=text,
                send_chunk=send_chunk,
                history=history,
                bot_id=bot_id,
                session_id=session_id,
                is_group=False,
                thinking_mode=True
            )

            # 获取完整回复（如果 send_chunk 没有更新，使用 result）
            if not full_reply and result:
                full_reply = result
            if not full_reply:
                full_reply = "抱歉，我无法处理您的请求。"

            print(f"[WebServer] Bot 回复内容: {full_reply[:100]}...")

            # 保存 Bot 回复到历史记录
            await self._add_to_history(session_id, bot_id, full_reply, bot_id=bot_id, is_group=False)

            # 发送回复到飞书
            feishu_integration.send_reply(chat_id, full_reply)

            # 广播 Bot 回复到 Web UI
            await self._broadcast_feishu_message({
                'type': 'feishu_message',
                'bot_id': bot_id,
                'chat_id': chat_id,
                'sender': bot_id,
                'text': full_reply,
                'session_type': 'feishu'
            })

        except Exception as e:
            print(f"[WebServer] 处理飞书 Bot 回复失败: {e}")
            import traceback
            traceback.print_exc()

    async def _broadcast_feishu_message(self, data: dict):
        """广播飞书消息到所有 WebSocket 客户端"""
        await self._ws_mgr.broadcast_message(data)

    async def broadcast_mcp_message(self, data: dict):
        """
        广播 MCP 消息到所有连接的客户端

        Args:
            data: 消息数据
        """
        await self._ws_mgr.broadcast_message(data)

    # ========== 向后兼容的代理方法 / 属性 ==========
    # 路由模块（routes/*.py）中仍通过 server.xxx 调用旧方法，
    # 这里统一委托到新的模块化组件。

    @property
    def _chat_history_lock(self):
        return self._history_mgr._chat_history_lock

    @property
    def _chat_history(self):
        return self._history_mgr._chat_history

    async def _load_session_history(self, chat_id: str, is_group: bool = False, bot_id: str = None):
        return await self._history_mgr.load_session_history(chat_id, is_group=is_group, bot_id=bot_id)

    async def _save_session_history(self, chat_id: str, is_group: bool = False,
                                    bot_id: str = None, bot_ids: list = None, name: str = None):
        return await self._history_mgr.save_session_history(
            chat_id, is_group=is_group, bot_id=bot_id, bot_ids=bot_ids, name=name
        )

    async def _add_to_history(self, chat_id: str, sender: str, content: str,
                              bot_id: str = None, is_group: bool = None):
        return await self._history_mgr.add_to_history(
            chat_id, sender, content, bot_id=bot_id, is_group=is_group
        )

    def _find_session_path(self, chat_id: str) -> str:
        """查找会话的 session.json 路径（支持群聊、单聊和飞书会话）

        新格式：使用 session.json 替代 meta.json
        向后兼容：如果 session.json 不存在，检查旧的 meta.json
        飞书会话：使用 f_ 前缀（如 f_session_id）
        """
        # 优先检查 session.json
        # 1. 群聊
        group_session = os.path.join(self.base_workplace, "groupspace", f"g_{chat_id}", "session.json")
        if os.path.exists(group_session):
            return group_session

        # 2. 单聊（web 界面创建，w_ 前缀）
        # 遍历文件系统中所有 workplace_* 目录（包括远程 bot）
        if os.path.exists(self.base_workplace):
            for entry in os.listdir(self.base_workplace):
                if entry.startswith("workplace_") and entry != 'workplace_system':
                    bot_id = entry[len("workplace_"):]
                    single_session = os.path.join(self.base_workplace, f"workplace_{bot_id}", f"w_{chat_id}", "session.json")
                    if os.path.exists(single_session):
                        return single_session

        # 3. 飞书会话（f_ 前缀）
        if os.path.exists(self.base_workplace):
            for entry in os.listdir(self.base_workplace):
                if entry.startswith("workplace_") and entry != 'workplace_system':
                    bot_id = entry[len("workplace_"):]
                    feishu_session = os.path.join(self.base_workplace, f"workplace_{bot_id}", f"f_{chat_id}", "session.json")
                    if os.path.exists(feishu_session):
                        return feishu_session

        # 向后兼容：检查旧的 meta.json
        group_meta = os.path.join(self.base_workplace, "groupspace", f"g_{chat_id}", "meta.json")
        if os.path.exists(group_meta):
            return group_meta
        if os.path.exists(self.base_workplace):
            for entry in os.listdir(self.base_workplace):
                if entry.startswith("workplace_") and entry != 'workplace_system':
                    bot_id = entry[len("workplace_"):]
                    single_meta = os.path.join(self.base_workplace, f"workplace_{bot_id}", f"w_{chat_id}", "meta.json")
                    if os.path.exists(single_meta):
                        return single_meta
                    feishu_meta = os.path.join(self.base_workplace, f"workplace_{bot_id}", f"f_{chat_id}", "meta.json")
                    if os.path.exists(feishu_meta):
                        return feishu_meta

        # 默认返回 session.json 路径（用于创建新文件）
        return group_session

    # 保留旧方法名以兼容现有代码
    _find_meta_path = _find_session_path

    def _find_session_path_for_bot(self, chat_id: str, bot_id: str) -> str:
        """查找指定 bot 的 session.json 路径

        与 _find_session_path 不同，此方法直接定位到 workplace_{bot_id}/w_{chat_id}/session.json
        """
        return os.path.join(self.base_workplace, f"workplace_{bot_id}", f"w_{chat_id}", "session.json")

    async def _get_session_meta(self, chat_id: str) -> dict:
        """获取会话的元数据"""
        session_path = self._find_session_path(chat_id)

        if not os.path.exists(session_path):
            # 修复：如果 _find_session_path 返回的群聊路径不存在，尝试查找 workplace 中的 session
            # 这处理了远程 bot 的单聊 session 被保存到 workplace 但 _find_session_path 找不到的情况
            if chat_id.startswith('session_'):
                for entry in os.listdir(self.base_workplace):
                    if entry.startswith('workplace_') and entry != 'workplace_system':
                        bot_id = entry[len('workplace_'):]
                        wp_session = self._find_session_path_for_bot(chat_id, bot_id)
                        if os.path.exists(wp_session):
                            session_path = wp_session
                            break

            if not os.path.exists(session_path):
                return {"id": chat_id}

        try:
            with open(session_path, 'r', encoding='utf-8') as f:
                data = json.load(f)

            # 新格式：包含 meta 字段
            if isinstance(data, dict) and 'meta' in data:
                return data['meta']

            # 旧格式（meta.json）：直接返回
            return data
        except Exception as e:
            print(f"[_get_session_meta] 读取失败: {session_path}, {e}")
            return {"id": chat_id}

    async def _save_session_meta(self, chat_id: str, meta: dict):
        """保存会话的元数据到 session.json"""
        session_path = self._find_session_path(chat_id)

        # 修复：如果 meta 中有 bot_ids 且是单聊，使用 workplace 路径而不是默认的群聊路径
        # 这防止了远程 bot 的单聊元数据被错误保存到 groupspace 目录
        bot_ids = meta.get("bot_ids", [])
        if len(bot_ids) == 1:
            bot_id = bot_ids[0]
            expected_path = self._find_session_path_for_bot(chat_id, bot_id)
            # 如果该 bot 的 workplace 目录存在，使用 workplace 路径
            bot_workplace = os.path.join(self.base_workplace, f"workplace_{bot_id}")
            if os.path.exists(bot_workplace):
                session_path = expected_path

        # 如果路径是旧的 meta.json，转换为 session.json
        if session_path.endswith('meta.json'):
            session_path = session_path.replace('meta.json', 'session.json')

        try:
            os.makedirs(os.path.dirname(session_path), exist_ok=True)

            # 读取现有 session.json（如果有）
            session_data = {"meta": {}, "messages": [], "stats": {}}
            if os.path.exists(session_path):
                with open(session_path, 'r', encoding='utf-8') as f:
                    session_data = json.load(f)

            # 更新 meta 部分
            session_data["meta"] = meta

            # 保存完整 session.json
            with open(session_path, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)
        except Exception as e:
            print(f"[_save_session_meta] 保存失败: {session_path}, {e}")
            raise

    async def _single_chat_with_context(self, ws: WebSocket, bot_id: str, message: str,
                                        chat_id: str = "default", is_group: bool = False,
                                        thinking_mode: bool = True, context_history: list = None):
        return await self._chat_core.single_chat_with_context(
            ws, bot_id, message, chat_id,
            is_group=is_group, thinking_mode=thinking_mode, context_history=context_history
        )

    async def _check_and_trigger_mention_cascade(self, ws: WebSocket, sender_bot_id: str,
                                                  message: str, chat_id: str,
                                                  thinking_mode: bool = True):
        return await self._chat_core._group_handler._check_and_trigger_mention_cascade(
            ws, sender_bot_id, message, chat_id, thinking_mode=thinking_mode
        )

    def _get_mention_context_history(self, chat_id: str, sender_bot_id: str,
                                     message: str, target_bot_id: str) -> list:
        return self._mention_mgr.get_mention_context_history(
            chat_id, sender_bot_id, message, target_bot_id
        )

    def _setup_routes(self):
        """设置路由"""
        # 获取静态文件目录
        static_dir = os.path.join(os.path.dirname(__file__), "static")
        if os.path.exists(static_dir):
            self.app.mount("/static", StaticFiles(directory=static_dir), name="static")

        # 文件上传目录
        self.app.mount("/uploads", StaticFiles(directory=self.upload_dir), name="uploads")

        # WebSocket 路由
        @self.app.websocket("/ws/chat")
        async def chat_ws(websocket: WebSocket, token: str = Query(...)):
            await self._ws_mgr.handle_chat_ws(websocket, token)

        @self.app.websocket("/ws/remote")
        async def remote_ws(websocket: WebSocket, token: str = Query(...)):
            """Handle P2P WebSocket connections from remote instances"""
            # Token 鉴权
            if token != self.auth_token:
                await websocket.close(code=4001, reason="Invalid token")
                return

            await websocket.accept()

            # If remote bot manager exists, handle the connection
            if self._remote_bot_mgr:
                await self._remote_bot_mgr.handle_remote_ws(websocket)
            else:
                await websocket.close(code=4002, reason="Remote bot functionality not available")

        # 当前实例信息（供前端动态获取 instance_id，替代硬编码）
        @self.app.get("/api/instance")
        async def get_instance_info():
            return {
                "success": True,
                "instance_id": getattr(self, 'instance_id', None),
                "port": self.port,
                "name": "Suntom's Instance"
            }

        # 初始化其他路由模块
        setup_internal_routes(self)
        setup_bots_routes(self)
        setup_moments_routes(self)
        setup_file_routes(self)
        setup_session_meta_routes(self)
        setup_session_core_routes(self)
        setup_session_scheduler_routes(self)
        setup_feishu_routes(self)

        # 远程功能路由
        if self._remote_bot_mgr:
            from .routes.remote import setup_remote_routes
            from .routes.remote_fs import router as remote_fs_router
            setup_remote_routes(self)
            self.app.include_router(remote_fs_router)
            print(f"[WebServer] 已注册远程 Bot 管理 API")
            print(f"[WebServer] 已注册远程文件访问 API")

        # 统一搜索路由
        try:
            from .routes.search import setup_search_routes
            search_router = setup_search_routes(self)
            self.app.include_router(search_router)
            print(f"[WebServer] 已注册本地搜索 API")
        except Exception as e:
            print(f"[WebServer] 注册搜索路由失败: {e}")


    def run(self, blocking: bool = False, ssl_cert: str = None, ssl_key: str = None):
        """
        启动服务器

        Args:
            blocking: 是否阻塞运行（默认后台线程）
            ssl_cert: SSL 证书路径
            ssl_key: SSL 密钥路径
        """
        print(f"[WebServer] run() called with blocking={blocking}, ssl_cert={ssl_cert}")
        config_kwargs = {
            "app": self.app,
            "host": "0.0.0.0",
            "port": self.port,
            "log_level": "warning",
            "access_log": False
        }
        if ssl_cert and ssl_key:
            config_kwargs["ssl_certfile"] = ssl_cert
            config_kwargs["ssl_keyfile"] = ssl_key

        config = uvicorn.Config(**config_kwargs)
        server = uvicorn.Server(config)

        if blocking:
            print(f"\n🌐 Web Chat 已启动")
            print(f"   URL: http://localhost:{self.port}/static/index.html?token={self.auth_token}")
            print(f"   Token: {self.auth_token}\n")

            # 远程管理器由 @app.on_event("startup") 自动启动，
            # 避免在临时事件循环中创建 WebSocket 连接（会导致注册中心 race condition）
            print(f"[WebServer] About to call server.run()...")
            server.run()
        else:
            # 后台线程启动
            def start():
                server.run()

            thread = threading.Thread(target=start, daemon=True)
            thread.start()

            print(f"\n🌐 Web Chat 已启动")
            print(f"   URL: http://localhost:{self.port}/static/index.html?token={self.auth_token}")
            print(f"   Token: {self.auth_token}\n")


# 保持向后兼容的别名
WebChatServer = WebChatServer
