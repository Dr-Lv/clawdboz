#!/usr/bin/env python3
"""
Feishu Bot 集成模块 - 将飞书 Bot 集成到 Web Chat Server

功能：
1. 在 Web Server 中启动 Feishu Bot 的 WebSocket 连接
2. 自动将飞书会话同步到 Web 界面
3. 支持 Web 界面回复飞书消息
"""

import asyncio
import json
import os
import ssl
import sys
import threading
import time
from typing import Dict, Optional, Callable

import lark_oapi as lark
from lark_oapi.ws.client import Client as WSClient, _new_ping_frame
from lark_oapi.ws.exception import ServerUnreachableException


class FeishuBotIntegration:
    """
    Feishu Bot 集成类

    管理 Feishu Bot 的 WebSocket 连接，并将消息同步到 Web Chat
    """

    def __init__(self, bot_id: str, app_id: str, app_secret: str,
                 verification_token: str = '', encrypt_key: str = '',
                 workplace_root: str = None,
                 on_message_callback: Callable = None,
                 on_card_update: Callable = None):
        """
        初始化 Feishu Bot 集成

        Args:
            bot_id: Bot ID
            app_id: 飞书 App ID
            app_secret: 飞书 App Secret
            verification_token: 飞书 Verification Token
            encrypt_key: 飞书 Encrypt Key
            workplace_root: 工作目录根路径
            on_message_callback: 收到消息时的回调函数
            on_card_update: 卡片更新时的回调函数
        """
        self.bot_id = bot_id
        self.app_id = app_id
        self.app_secret = app_secret
        self.verification_token = verification_token
        self.encrypt_key = encrypt_key
        self.workplace_root = workplace_root or os.environ.get('CLAWDBOZ_BOT_WORK_DIR', 'WORKPLACE')
        self.on_message_callback = on_message_callback
        self.on_card_update = on_card_update

        self._ws_client = None
        self._running = False
        self._thread = None

    def start(self):
        """启动 Feishu Bot WebSocket 连接"""
        if self._running:
            print(f"[FeishuBot-{self.bot_id}] 已经在运行")
            return

        self._running = True
        self._thread = threading.Thread(target=self._run_websocket, daemon=True)
        self._thread.start()
        print(f"[FeishuBot-{self.bot_id}] WebSocket 连接已启动")

    def stop(self):
        """停止 Feishu Bot WebSocket 连接"""
        self._running = False
        if self._ws_client:
            try:
                self._ws_client._disconnect()
            except:
                pass
        print(f"[FeishuBot-{self.bot_id}] WebSocket 连接已停止")

    def _run_websocket(self):
        """运行 WebSocket 连接（在独立线程中）"""
        # 禁用 SSL 验证
        ssl._create_default_https_context = ssl._create_unverified_context

        # Monkey-patch websockets.connect
        import websockets
        original_connect = websockets.connect

        async def patched_connect(uri, **kwargs):
            kwargs['ssl'] = ssl._create_unverified_context()
            return await original_connect(uri, **kwargs)

        websockets.connect = patched_connect

        # 创建事件处理器
        event_handler = lark.EventDispatcherHandler.builder(
            self.encrypt_key, self.verification_token
        ).register_p2_im_message_receive_v1(self._on_message).build()

        # 创建并启动 WebSocket 客户端
        self._ws_client = WSClient(
            self.app_id,
            self.app_secret,
            event_handler=event_handler,
            log_level=lark.LogLevel.INFO
        )

        try:
            self._ws_client.start()
        except Exception as e:
            print(f"[FeishuBot-{self.bot_id}] WebSocket 错误: {e}")
            self._running = False

    def _on_message(self, data: lark.im.v1.P2ImMessageReceiveV1):
        """处理收到的飞书消息"""
        try:
            message = data.event.message
            chat_id = message.chat_id
            sender = data.event.sender
            msg_type = message.message_type

            # 获取发送者信息
            sender_name = "未知用户"
            if sender.sender_type == "user":
                sender_name = getattr(sender, 'name', sender.sender_id.user_id)

            # 解析消息内容
            content = json.loads(message.content)
            text = content.get("text", "")

            print(f"[FeishuBot-{self.bot_id}] 收到消息: {sender_name}: {text[:50]}")

            # 检查是否为 Web 同步消息（以 [Web] 开头）
            if text.startswith('[Web] '):
                # Web 同步消息：移除标记，保存但不触发 Bot 回复
                text = text[6:]  # 移除 "[Web] " 前缀
                self._save_message(chat_id, "Web用户", text, is_user=True)
                print(f"[FeishuBot-{self.bot_id}] Web同步消息，已保存，不触发 Bot 回复")
                return

            # 保存消息到历史记录
            self._save_message(chat_id, sender_name, text, is_user=True)

            # 调用回调函数（触发 Bot 回复）
            if self.on_message_callback:
                self.on_message_callback(
                    bot_id=self.bot_id,
                    chat_id=chat_id,
                    sender=sender_name,
                    text=text,
                    feishu_integration=self
                )

        except Exception as e:
            print(f"[FeishuBot-{self.bot_id}] 处理消息失败: {e}")

    def _save_message(self, chat_id: str, sender: str, content: str, is_user: bool = True):
        """保存消息到 session.json"""
        try:
            # 飞书会话使用 f_ 前缀
            session_dir = os.path.join(
                self.workplace_root,
                f'workplace_{self.bot_id}',
                f'f_{chat_id}'
            )
            os.makedirs(session_dir, exist_ok=True)

            session_file = os.path.join(session_dir, 'session.json')

            # 读取现有 session
            session_data = {"meta": {}, "messages": [], "stats": {}}
            if os.path.exists(session_file):
                try:
                    with open(session_file, 'r', encoding='utf-8') as f:
                        session_data = json.load(f)
                except:
                    pass

            # 确保基本结构存在
            if 'meta' not in session_data:
                session_data['meta'] = {}
            if 'messages' not in session_data:
                session_data['messages'] = []
            if 'stats' not in session_data:
                session_data['stats'] = {}

            # 更新 meta
            session_data['meta']['chat_id'] = chat_id
            session_data['meta']['type'] = 'feishu'
            session_data['meta']['bot_id'] = self.bot_id
            session_data['meta']['bot_ids'] = [self.bot_id]  # 用于会话列表归类
            session_data['meta']['mode'] = 'single'
            session_data['meta']['source'] = 'feishu'  # 标识为飞书会话
            session_data['meta']['updated_at'] = time.time()
            if not session_data['meta'].get('created_at'):
                session_data['meta']['created_at'] = time.time()

            # 添加消息
            msg_data = {
                "sender": "user" if is_user else "assistant",
                "content": content,
                "time": time.time()
            }
            session_data['messages'].append(msg_data)

            # 更新统计
            session_data['stats']['total_messages'] = len(session_data['messages'])

            # 保存
            with open(session_file, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)

        except Exception as e:
            print(f"[FeishuBot-{self.bot_id}] 保存消息失败: {e}")

    def send_reply(self, chat_id: str, text: str) -> str:
        """
        发送回复到飞书（使用卡片消息支持 Markdown）

        Args:
            chat_id: 飞书 chat_id
            text: 回复内容（支持 Markdown）

        Returns:
            message_id: 消息 ID
        """
        try:
            from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

            # 创建飞书客户端
            client = lark.Client.builder() \
                .app_id(self.app_id) \
                .app_secret(self.app_secret) \
                .log_level(lark.LogLevel.INFO) \
                .build()

            # 构建卡片消息内容（支持 Markdown）
            card_content = {
                "config": {
                    "wide_screen_mode": True
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": text
                        }
                    }
                ]
            }

            request = CreateMessageRequest.builder() \
                .receive_id_type("chat_id") \
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type("interactive")
                    .content(json.dumps(card_content))
                    .build()
                ) \
                .build()

            response = client.im.v1.message.create(request)

            if response.code == 0:
                print(f"[FeishuBot-{self.bot_id}] 卡片回复已发送: {response.data.message_id}")
                return response.data.message_id
            else:
                print(f"[FeishuBot-{self.bot_id}] 发送失败: {response.msg}")
                return ""

        except Exception as e:
            print(f"[FeishuBot-{self.bot_id}] 发送回复失败: {e}")
            import traceback
            traceback.print_exc()
            return ""


class FeishuBotManager:
    """管理多个 Feishu Bot 集成实例"""

    def __init__(self, workplace_root: str = None):
        self.bots: Dict[str, FeishuBotIntegration] = {}
        self.workplace_root = workplace_root

    def register(self, bot_id: str, app_id: str, app_secret: str,
                 verification_token: str = '', encrypt_key: str = '',
                 on_message_callback: Callable = None) -> FeishuBotIntegration:
        """
        注册 Feishu Bot

        Args:
            bot_id: Bot ID
            app_id: 飞书 App ID
            app_secret: 飞书 App Secret
            verification_token: 飞书 Verification Token
            encrypt_key: 飞书 Encrypt Key
            on_message_callback: 消息回调函数

        Returns:
            FeishuBotIntegration 实例
        """
        if bot_id in self.bots:
            print(f"[FeishuBotManager] Bot '{bot_id}' 已存在，跳过注册")
            return self.bots[bot_id]

        bot = FeishuBotIntegration(
            bot_id=bot_id,
            app_id=app_id,
            app_secret=app_secret,
            verification_token=verification_token,
            encrypt_key=encrypt_key,
            workplace_root=self.workplace_root,
            on_message_callback=on_message_callback
        )

        self.bots[bot_id] = bot
        print(f"[FeishuBotManager] 注册 Bot '{bot_id}'")
        return bot

    def start_all(self):
        """启动所有 Feishu Bot"""
        for bot_id, bot in self.bots.items():
            bot.start()

    def stop_all(self):
        """停止所有 Feishu Bot"""
        for bot_id, bot in self.bots.items():
            bot.stop()

    def get_bot(self, bot_id: str) -> Optional[FeishuBotIntegration]:
        """获取指定 Bot"""
        return self.bots.get(bot_id)
