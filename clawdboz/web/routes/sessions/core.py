#!/usr/bin/env python3
"""
Session Core Routes - 会话核心路由

提供用户资料、配置管理、思考模式、会话介绍和 Bot 权限等功能。
"""

import json
import os
import time
from typing import TYPE_CHECKING

from fastapi import Request, Query
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from ...server_core import WebChatServer


def setup_session_core_routes(server: "WebChatServer"):
    """
    设置会话核心路由

    Args:
        server: WebChatServer 实例
    """
    app = server.app
    auth_token = server.auth_token
    base_workplace = server.base_workplace

    @app.get("/api/user/profile")
    async def get_user_profile(token: str = Query(...)):
        """获取用户资料"""
        if token != auth_token:
            return JSONResponse(
                status_code=403,
                content={"success": False, "error": "Invalid token"}
            )

        try:
            user_file = os.path.join(base_workplace, '.user.md')
            result = {
                "name": "用户",
                "bio": "",
                "avatar_color": "from-indigo-500 to-purple-600",
                "avatar_icon": "fa-user"
            }

            if os.path.exists(user_file):
                with open(user_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith('Name:'):
                            result['name'] = line.replace('Name:', '').strip()
                        elif line.startswith('Bio:'):
                            result['bio'] = line.replace('Bio:', '').strip()
                        elif line.startswith('Avatar Color:'):
                            result['avatar_color'] = line.replace('Avatar Color:', '').strip()
                        elif line.startswith('Avatar Icon:'):
                            result['avatar_icon'] = line.replace('Avatar Icon:', '').strip()
                        elif line.startswith('Avatar Image:'):
                            result['avatar_image'] = line.replace('Avatar Image:', '').strip()

            return result
        except Exception as e:
            print(f"[Get User Profile] 错误: {e}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )

    @app.post("/api/user/profile/update")
    async def save_user_profile(request: Request):
        """保存用户资料"""
        try:
            data = await request.json()
            token = data.get('token')

            if token != auth_token:
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "error": "Invalid token"}
                )

            name = data.get('name', '').strip()
            bio = data.get('bio', '').strip()
            avatar_color = data.get('avatar_color', '').strip()
            avatar_icon = data.get('avatar_icon', '').strip()
            avatar_image = data.get('avatar_image', '').strip()

            user_file = os.path.join(base_workplace, '.user.md')

            with open(user_file, 'w', encoding='utf-8') as f:
                f.write(f"# 用户资料\n\n")
                f.write(f"Name: {name}\n")
                f.write(f"Bio: {bio}\n")
                f.write(f"Avatar Color: {avatar_color or 'from-indigo-500 to-purple-600'}\n")
                f.write(f"Avatar Icon: {avatar_icon or 'fa-user'}\n")
                if avatar_image:
                    f.write(f"Avatar Image: {avatar_image}\n")

            return {"success": True}
        except Exception as e:
            print(f"[Save User Profile] 错误: {e}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )

    @app.get("/api/config")
    async def get_config(token: str = Query(...)):
        """获取 config.json 配置"""
        if token != auth_token:
            return JSONResponse(
                status_code=403,
                content={"success": False, "error": "Invalid token"}
            )
        try:
            config_path = os.path.join(os.path.dirname(base_workplace), 'config.json')
            if not os.path.exists(config_path):
                return JSONResponse(
                    status_code=404,
                    content={"success": False, "error": "config.json not found"}
                )
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            return {"success": True, "config": config}
        except Exception as e:
            print(f"[Get Config] 错误: {e}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )

    @app.post("/api/config")
    async def save_config(request: Request, token: str = Query(...)):
        """保存 config.json 配置"""
        if token != auth_token:
            return JSONResponse(
                status_code=403,
                content={"success": False, "error": "Invalid token"}
            )
        try:
            data = await request.json()
            config = data.get("config")
            if config is None:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "Missing config field"}
                )
            config_path = os.path.join(os.path.dirname(base_workplace), 'config.json')
            with open(config_path, 'w', encoding='utf-8') as f:
                json.dump(config, f, indent=2, ensure_ascii=False)
            print(f"[Save Config] 已保存配置到: {config_path}")

            # 同步更新最大@嵌套深度
            chat_config = config.get('chat', {})
            if 'max_mention_depth' in chat_config:
                server._mention_mgr.set_max_mention_depth(chat_config['max_mention_depth'])

            return {"success": True}
        except Exception as e:
            print(f"[Save Config] 错误: {e}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )

    @app.get("/api/sessions/{chat_id}/thinking-mode")
    async def get_thinking_mode(chat_id: str, token: str = Query(...)):
        """
        获取会话的思考模式设置

        Args:
            chat_id: 会话 ID

        Returns:
            {"thinking_mode": true|false}
        """
        if token != auth_token:
            return JSONResponse(
                status_code=403,
                content={"success": False, "error": "Invalid token"}
            )

        try:
            meta = await server._get_session_meta(chat_id)
            return {"thinking_mode": meta.get("thinking_mode", True)}
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )

    @app.post("/api/sessions/{chat_id}/thinking-mode")
    async def set_thinking_mode(chat_id: str, request: Request, token: str = Query(...)):
        """
        设置会话的思考模式

        Args:
            chat_id: 会话 ID
            request: {"thinking_mode": true|false}

        Returns:
            {"success": true}
        """
        if token != auth_token:
            return JSONResponse(
                status_code=403,
                content={"success": False, "error": "Invalid token"}
            )

        try:
            data = await request.json()
            thinking_mode = data.get("thinking_mode", True)

            meta = await server._get_session_meta(chat_id)
            meta["thinking_mode"] = thinking_mode
            meta["updated_at"] = time.time()
            await server._save_session_meta(chat_id, meta)

            print(f"[WebServer] 设置思考模式: {chat_id} -> {thinking_mode}")
            return {"success": True, "thinking_mode": thinking_mode}
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )

    @app.post("/api/sessions/{chat_id}/intro")
    async def send_session_intro(chat_id: str, request: Request, token: str = Query(...)):
        """
        发送会话成员介绍信息

        在新建会话时调用，将会话中所有成员（用户+bots）的介绍信息
        作为系统上下文发送给所有 bots，帮助 bots 了解彼此

        Args:
            chat_id: 会话 ID
            request: 包含成员信息的请求体
            {
                "members": [
                    {"type": "user", "id": "user", "name": "用户名", "bio": "用户介绍"},
                    {"type": "bot", "id": "bot1", "name": "Bot名", "bio": "Bot介绍"}
                ]
            }
        """
        if token != auth_token:
            return JSONResponse(
                status_code=403,
                content={"success": False, "error": "Invalid token"}
            )

        try:
            data = await request.json()
            members = data.get("members", [])

            if not members:
                return {"success": True, "message": "No members to send"}

            # 构建成员介绍消息
            intro_lines = ["**会话成员介绍**\n"]
            for member in members:
                mtype = member.get("type", "bot")
                name = member.get("name", "未知")
                bio = member.get("bio", "")

                if mtype == "user":
                    prefix = "👤 用户"
                else:
                    prefix = "🤖 Bot"

                if bio:
                    intro_lines.append(f"{prefix} **{name}**: {bio}")
                else:
                    intro_lines.append(f"{prefix} **{name}**")

            intro_message = "\n".join(intro_lines)

            # 读取会话元数据，确定是否为群聊以及 bot_ids
            meta_path = server._find_meta_path(chat_id)
            is_group = False
            bot_ids = []
            if os.path.exists(meta_path):
                try:
                    with open(meta_path, 'r', encoding='utf-8') as f:
                        meta = json.load(f)
                    bot_ids = meta.get("bot_ids", [])
                    is_group = meta.get("is_group", len(bot_ids) > 1)
                except Exception as e:
                    print(f"[WebServer] 读取会话元数据失败: {chat_id}, {e}")

            # 保存到历史记录（作为系统消息，不触发 bot 回复）
            await server._add_to_history(
                chat_id,
                "system",
                intro_message,
                is_group=is_group,
                bot_id=bot_ids[0] if bot_ids else None
            )

            # 广播给所有连接的客户端（可选，让前端知道有系统消息）
            await server.broadcast_mcp_message({
                "type": "session_intro",
                "content": intro_message,
                "sender": "system",
                "chat_id": chat_id,
                "save_to_history": False  # 已经手动保存了
            })

            print(f"[WebServer] 已发送会话成员介绍: {chat_id}, {len(members)} 个成员")
            return {"success": True, "message": "Intro sent"}

        except Exception as e:
            print(f"[WebServer] 发送会话介绍失败: {e}")
            import traceback
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )

    @app.get("/api/bot-permissions")
    async def get_bot_permissions(token: str = Query(...), chat_id: str = Query(...)):
        """
        获取群聊的 Bot @ 权限设置

        Args:
            token: 访问令牌
            chat_id: 会话 ID

        Returns:
            {"permissions": {"sender_bot_id": ["target_bot_id", ...]}}
        """
        if token != auth_token:
            return JSONResponse(
                status_code=403,
                content={"success": False, "error": "Invalid token"}
            )

        try:
            # 权限文件保存在群聊目录下
            permissions_file = os.path.join(
                base_workplace,
                "groupspace",
                f"g_{chat_id}",
                ".permissions.json"
            )

            if os.path.exists(permissions_file):
                with open(permissions_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    return {"permissions": data.get("permissions", {})}
            else:
                # 默认空权限
                return {"permissions": {}}

        except Exception as e:
            print(f"[Get Bot Permissions] 错误: {e}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )

    @app.post("/api/bot-permissions")
    async def save_bot_permissions(request: Request):
        """
        保存群聊的 Bot @ 权限设置

        Args:
            request: {
                "token": "...",
                "chat_id": "...",
                "permissions": {"sender_bot_id": ["target_bot_id", ...]}
            }
        """
        try:
            data = await request.json()
            token = data.get('token')
            chat_id = data.get('chat_id')
            permissions = data.get('permissions', {})

            if token != auth_token:
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "error": "Invalid token"}
                )

            # 确保群聊目录存在
            group_dir = os.path.join(base_workplace, "groupspace", f"g_{chat_id}")
            os.makedirs(group_dir, exist_ok=True)

            # 保存权限到文件
            permissions_file = os.path.join(group_dir, ".permissions.json")
            with open(permissions_file, 'w', encoding='utf-8') as f:
                json.dump({
                    "chat_id": chat_id,
                    "permissions": permissions,
                    "updated_at": time.time()
                }, f, ensure_ascii=False, indent=2)

            print(f"[Save Bot Permissions] 已保存: {chat_id}, {permissions}")
            return {"success": True, "message": "权限已保存"}

        except json.JSONDecodeError as je:
            print(f"[Save Bot Permissions] JSON 解析错误: {je}")
            return JSONResponse(
                status_code=400,
                content={"success": False, "error": f"Invalid JSON: {str(je)}"}
            )

        except Exception as e:
            print(f"[Save Bot Permissions] 错误: {e}")
            import traceback
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )
