#!/usr/bin/env python3
"""
Feishu Integration Routes - 飞书集成路由

提供飞书消息同步、事件处理等功能。
"""

import json
import os
import time
from typing import TYPE_CHECKING

from fastapi import Request, Query
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from ..server_core import WebChatServer


def setup_feishu_routes(server: "WebChatServer"):
    """
    设置飞书集成 API 路由

    Args:
        server: WebChatServer 实例
    """
    app = server.app
    auth_token = server.auth_token
    base_workplace = server.base_workplace
    bots = server.bots
    _chat_core = server._chat_core
    _history_mgr = server._history_mgr
    _ws_mgr = server._ws_mgr
    _feishu_manager = getattr(server, '_feishu_manager', None)

    @app.post("/api/feishu/webhook")
    async def feishu_webhook(request: Request):
        """
        飞书 Webhook 回调接口

        接收飞书事件推送，同步到 Web 会话
        """
        try:
            data = await request.json()

            # 处理飞书 URL 验证挑战
            if data.get('type') == 'url_verification':
                return JSONResponse({
                    "challenge": data.get('challenge')
                })

            # 获取事件内容
            header = data.get('header', {})
            event = data.get('event', {})

            event_type = header.get('event_type')
            app_id = header.get('app_id')

            # 只处理消息事件
            if event_type == 'im.message.receive_v1':
                message = event.get('message', {})
                sender = event.get('sender', {})

                chat_id = message.get('chat_id')
                message_type = message.get('message_type')
                content = message.get('content', '{}')
                sender_id = sender.get('sender_id', {}).get('union_id')
                sender_name = sender.get('sender_id', {}).get('user_id', '未知用户')

                # 解析消息内容
                try:
                    content_obj = json.loads(content)
                    text = content_obj.get('text', '')
                except:
                    text = content

                # 查找对应的 Bot
                target_bot = None
                for bot_id, bot in bots.items():
                    if hasattr(bot, 'app_id') and bot.app_id == app_id:
                        target_bot = bot
                        break

                if not target_bot:
                    # 从配置文件查找
                    for bot_id in os.listdir(base_workplace):
                        if bot_id.startswith('workplace_'):
                            bot_real_id = bot_id[len('workplace_'):]
                            bot_md_path = os.path.join(base_workplace, bot_id, '.bot.md')
                            if os.path.exists(bot_md_path):
                                with open(bot_md_path, 'r', encoding='utf-8') as f:
                                    for line in f:
                                        if line.startswith('Feishu App ID:'):
                                            bot_app_id = line.replace('Feishu App ID:', '').strip()
                                            if bot_app_id == app_id:
                                                target_bot = bots.get(bot_real_id)
                                                break

                if not target_bot:
                    return JSONResponse(
                        status_code=404,
                        content={"success": False, "error": "Bot not found"}
                    )

                # 查找或创建会话
                session_id = f"feishu_{chat_id}"

                # 确定是否是群聊
                chat_type = message.get('chat_type', 'private')
                is_group = chat_type == 'group'

                # 检查会话是否已存在
                from ..routes.sessions.meta import _get_session_info_from_dir
                if is_group:
                    session_dir = os.path.join(base_workplace, 'groupspace', f'g_{session_id}')
                else:
                    session_dir = os.path.join(base_workplace, f'workplace_{target_bot._bot_id if hasattr(target_bot, "_bot_id") else "default"}', f'w_{session_id}')

                session_exists = os.path.exists(os.path.join(session_dir, 'session.json'))

                # 如果会话不存在，创建会话元数据
                if not session_exists:
                    os.makedirs(session_dir, exist_ok=True)
                    session_path = os.path.join(session_dir, 'session.json')
                    now = time.time()
                    session_data = {
                        "meta": {
                            "id": session_id,
                            "name": f"飞书会话 {chat_id[:8]}",
                            "bot_ids": [target_bot._bot_id] if hasattr(target_bot, '_bot_id') else ['default'],
                            "chat_type": "group" if is_group else "single",
                            "is_group": is_group,
                            "source": "feishu",
                            "feishu_chat_id": chat_id,
                            "created_at": now,
                            "updated_at": now
                        },
                        "messages": [],
                        "stats": {}
                    }
                    with open(session_path, 'w', encoding='utf-8') as f:
                        json.dump(session_data, f, ensure_ascii=False, indent=2)
                    print(f"[Feishu Webhook] 创建新会话: {session_id}")

                # 保存消息到历史记录
                bot_id_for_session = target_bot._bot_id if hasattr(target_bot, '_bot_id') else 'default'
                await _history_mgr.add_to_history(
                    chat_id=session_id,
                    sender=f"feishu_user_{sender_id}",
                    content=text,
                    bot_id=bot_id_for_session,
                    is_group=is_group
                )

                # 构建 WebSocket 消息
                ws_message = {
                    "type": "message",
                    "chat_id": session_id,
                    "sender": f"飞书用户 ({sender_name})",
                    "content": text,
                    "timestamp": time.time(),
                    "source": "feishu"
                }

                # 广播给所有连接的客户端
                await _ws_mgr.broadcast_message(ws_message)

                return {"success": True}

            return {"success": True}

        except Exception as e:
            print(f"[Feishu Webhook] 处理失败: {e}")
            import traceback
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )

    @app.get("/api/feishu/bots")
    async def get_feishu_bots(token: str = Query(...)):
        """获取已配置飞书的 Bot 列表"""
        if token != auth_token:
            return JSONResponse(
                status_code=403,
                content={"success": False, "error": "Invalid token"}
            )

        try:
            feishu_bots = []

            for bot_id in bots:
                bot = bots[bot_id]
                bot_work_dir = os.path.join(base_workplace, f"workplace_{bot_id}")
                bot_md_path = os.path.join(bot_work_dir, '.bot.md')

                feishu_config = {
                    "id": bot_id,
                    "name": getattr(bot, 'name', bot_id),
                    "has_feishu": False
                }

                if os.path.exists(bot_md_path):
                    with open(bot_md_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            if line.startswith('Feishu App ID:'):
                                feishu_config['feishu_app_id'] = line.replace('Feishu App ID:', '').strip()
                                feishu_config['has_feishu'] = True
                            elif line.startswith('Feishu App Secret:'):
                                feishu_config['has_secret'] = True

                feishu_bots.append(feishu_config)

            return {"success": True, "bots": feishu_bots}

        except Exception as e:
            print(f"[Feishu API] 获取列表失败: {e}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )

    @app.post("/api/feishu/send")
    async def send_feishu_message(request: Request, token: str = Query(...)):
        """
        从 Web 发送消息到飞书

        请求体: {"chat_id": "feishu_xxx", "message": "消息内容", "bot_id": "bot_id"}
        """
        if token != auth_token:
            return JSONResponse(
                status_code=403,
                content={"success": False, "error": "Invalid token"}
            )

        try:
            data = await request.json()
            chat_id = data.get('chat_id')
            message = data.get('message')
            bot_id = data.get('bot_id')

            if not chat_id or not message:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "Missing chat_id or message"}
                )

            # 检查是否为飞书会话
            print(f"[Feishu API] 收到发送请求: chat_id={chat_id}, bot_id={bot_id}")

            # 支持两种格式：feishu_{chat_id} 或 {chat_id}
            if chat_id.startswith("feishu_"):
                feishu_chat_id = chat_id[len("feishu_"):]
            else:
                # 检查是否存在对应的飞书会话目录 (f_{chat_id})
                feishu_session_exists = False
                for bot_id_check in bots.keys():
                    feishu_dir = os.path.join(base_workplace, f"workplace_{bot_id_check}", f"f_{chat_id}")
                    if os.path.exists(feishu_dir):
                        feishu_session_exists = True
                        break

                if not feishu_session_exists:
                    print(f"[Feishu API] 拒绝: 未找到飞书会话目录 f_{chat_id}")
                    return JSONResponse(
                        status_code=400,
                        content={"success": False, "error": "Not a Feishu session"}
                    )
                feishu_chat_id = chat_id
            # 如果没有指定 bot_id，尝试从会话元数据获取
            if not bot_id:
                from ..routes.sessions.meta import _get_session_info_from_dir
                session_info = _get_session_info_from_dir(chat_id, base_workplace)
                if session_info and session_info.get('bot_ids'):
                    bot_id = session_info['bot_ids'][0]

            if not bot_id:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "Bot ID not found"}
                )

            # 检查 Feishu 集成是否可用
            if not _feishu_manager:
                return JSONResponse(
                    status_code=500,
                    content={"success": False, "error": "Feishu integration not available"}
                )

            # 获取 Feishu Bot 实例
            feishu_bot = _feishu_manager.get_bot(bot_id)
            if not feishu_bot:
                return JSONResponse(
                    status_code=404,
                    content={"success": False, "error": f"Feishu bot '{bot_id}' not found"}
                )

            # 发送消息到飞书，添加 User： 前缀标记来源
            marked_message = f"User：{message}"
            message_id = feishu_bot.send_reply(feishu_chat_id, marked_message)

            if message_id:
                return {"success": True, "message_id": message_id}
            else:
                return JSONResponse(
                    status_code=500,
                    content={"success": False, "error": "Failed to send message to Feishu"}
                )

        except Exception as e:
            print(f"[Feishu API] 发送消息失败: {e}")
            import traceback
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )
