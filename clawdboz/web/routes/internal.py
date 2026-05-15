#!/usr/bin/env python3
"""
Internal API Routes - 内部 API 路由

提供内部消息发送、定时任务触发、调试接口等功能。
"""

import json
import os
import sys
import time
from typing import TYPE_CHECKING

from fastapi import Request, Query
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from ..server_core import WebChatServer


def setup_internal_routes(server: "WebChatServer"):
    """
    设置内部 API 路由

    Args:
        server: WebChatServer 实例
    """
    app = server.app
    auth_token = server.auth_token
    base_workplace = server.base_workplace
    bots = server.bots

    @app.post("/api/server/restart")
    async def restart_server(request: Request):
        """重启 Web 服务器"""
        try:
            data = await request.json()
            token = data.get('token')
            if token != auth_token:
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "error": "Invalid token"}
                )

            import subprocess
            pid = os.getpid()
            port = server.port
            base_dir = getattr(server, '_base_dir', os.getcwd())

            # 使用当前 Python 解释器和绝对路径
            python_exe = sys.executable
            web_server_path = os.path.join(base_dir, "web_server.py")
            log_path = os.path.join(base_dir, "web_server.log")

            # 判断启动方式：优先 web_server.py，否则回退到 clawdboz CLI
            if os.path.exists(web_server_path):
                # 开发模式：通过 web_server.py 启动
                restart_cmd = (
                    f"sleep 1 && kill -9 {pid} && "
                    f"cd {base_dir} && nohup {python_exe} {web_server_path} --port {port} > {log_path} 2>&1 &"
                )
            else:
                # 生产模式：通过 clawdboz CLI 启动
                # 查找 clawdboz 命令路径（优先当前虚拟环境）
                clawdboz_exe = None
                # 尝试与当前进程相同的目录
                current_clawdboz = os.path.join(os.path.dirname(python_exe), "clawdboz")
                if os.path.exists(current_clawdboz):
                    clawdboz_exe = current_clawdboz
                else:
                    # 尝试 PATH 中的 clawdboz
                    import shutil
                    clawdboz_exe = shutil.which("clawdboz")

                if not clawdboz_exe:
                    return JSONResponse(
                        status_code=500,
                        content={"success": False, "error": "找不到 web_server.py 或 clawdboz 命令，无法重启"}
                    )

                restart_cmd = (
                    f"sleep 1 && kill -9 {pid} && "
                    f"cd {base_dir} && nohup {clawdboz_exe} web --port {port} > {log_path} 2>&1 &"
                )

            # 记录命令用于调试
            print(f"[Restart] 执行重启命令: {restart_cmd}")

            # 执行重启命令
            process = subprocess.Popen(
                restart_cmd,
                shell=True,
                stdout=subprocess.PIPE,
                stderr=subprocess.PIPE,
                text=True
            )

            return {"success": True, "message": "服务器正在重启，请稍后刷新页面"}
        except Exception as e:
            import traceback
            error_details = f"{str(e)}\n{traceback.format_exc()}"
            print(f"[Restart] 重启失败: {error_details}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e), "details": error_details}
            )

    @app.post("/api/mcp/broadcast")
    async def mcp_broadcast(data: dict):
        """
        MCP 消息广播接口
        供 MCP 服务器调用，将消息/文件/通知发送到前端

        Args:
            data: 消息数据，格式为 {"type": "mcp_message|mcp_file|mcp_notify", ...}
        """
        token = data.pop('_token', '')
        if token != auth_token:
            return JSONResponse(
                status_code=403,
                content={"success": False, "error": "Invalid token"}
            )

        try:
            await server.broadcast_mcp_message(data)
            return {"success": True}
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )

    @app.post("/api/internal/send-message")
    async def internal_send_message(request: Request):
        """
        内部消息发送接口
        供 webchat-sender skill 调用，将消息发送到 Web Chat

        Args:
            request: 包含消息数据的请求体
            {
                "content": "消息内容",
                "sender": "bot_id",
                "chat_id": "session_id",
                "is_group": false,
                "bot_ids": ["bot1", "bot2"],
                "is_system": false,
                "save_to_history": true,
                "_token": "auth_token"
            }
        """
        try:
            data = await request.json()
            token = data.pop('_token', '')

            if token != auth_token:
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "error": "Invalid token", "code": "UNAUTHORIZED"}
                )

            sender = data.get('sender', 'bot')
            is_hidden = sender == 'user_hidden'  # 隐藏消息标记

            # 转换为 broadcast_mcp_message 格式
            broadcast_data = {
                "type": "mcp_message" if not data.get('is_system') else "mcp_notify",
                "content": data.get('content', ''),
                "sender": sender,
                "chat_id": data.get('chat_id'),
                "is_group": data.get('is_group', False),
                "bot_ids": data.get('bot_ids', []),
                "save_to_history": data.get('save_to_history', True) and not is_hidden,
                "is_hidden": is_hidden  # 标记是否为隐藏消息
            }

            # 处理文件消息
            if data.get('type') == 'mcp_file' or data.get('file_url'):
                broadcast_data['type'] = 'mcp_file'
                broadcast_data['file_name'] = data.get('file_name', 'file')
                broadcast_data['file_url'] = data.get('file_url', '')
                broadcast_data['file_size'] = data.get('file_size', 0)

            # 只有非隐藏消息才广播到 WebSocket（前端显示）
            if not is_hidden:
                await server.broadcast_mcp_message(broadcast_data)
            else:
                print(f"[Internal Send Message] 隐藏消息，不广播到前端: chat_id={data.get('chat_id')}")

            # 保存到历史记录（如果需要且不是隐藏消息）
            if data.get('save_to_history', True) and not is_hidden and data.get('chat_id'):
                await server._add_to_history(
                    data.get('chat_id'),
                    sender,
                    data.get('content', ''),
                    is_group=data.get('is_group', False),
                    bot_id=sender
                )

            return {
                "success": True,
                "message": "消息已发送",
                "data": {
                    "chat_id": data.get('chat_id'),
                    "sender": data.get('sender')
                }
            }

        except Exception as e:
            print(f"[Internal Send Message] 错误: {e}")
            import traceback
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e), "code": "INTERNAL_ERROR"}
            )

    @app.post("/api/internal/trigger-scheduled-task")
    async def trigger_scheduled_task(request: Request):
        """
        内部接口：触发定时任务执行
        供 bot.py 定时任务调用，实现：
        1. 以 system 身份保存消息到历史记录（前端隐藏）
        2. 触发指定 bot 回复（走正常的群聊/单聊流程）

        Args:
            request: {
                "chat_id": "会话ID",
                "bot_id": "要触发的bot ID",
                "description": "任务描述",
                "is_group": true/false,
                "_token": "认证token"
            }
        """
        try:
            data = await request.json()
            token = data.pop('_token', '')

            if token != auth_token:
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "error": "Invalid token", "code": "UNAUTHORIZED"}
                )

            chat_id = data.get('chat_id')
            bot_id = data.get('bot_id')
            description = data.get('description', '')
            is_group = data.get('is_group', False)

            if not chat_id or not bot_id:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "缺少 chat_id 或 bot_id", "code": "MISSING_PARAMS"}
                )

            print(f"[Scheduled Task Trigger] 触发定时任务: chat_id={chat_id}, bot_id={bot_id}, is_group={is_group}")

            # 检查 Bot 是否存在
            if bot_id not in bots:
                return JSONResponse(
                    status_code=404,
                    content={"success": False, "error": f"Bot '{bot_id}' 不存在", "code": "BOT_NOT_FOUND"}
                )

            # 构建 system 消息内容
            # 群聊：@bot 任务描述；单聊：任务描述
            if is_group:
                system_message = f"@{bot_id} {description}"
            else:
                system_message = description

            # 1. 以 system 身份保存消息到历史记录（前端会自动隐藏）
            await server._add_to_history(chat_id, "system", system_message, is_group=is_group)
            print(f"[Scheduled Task Trigger] 已保存 system 消息到历史记录: {system_message[:50]}...")

            # 2. 获取该聊天的 WebSocket 连接
            ws = None
            thinking_mode = True
            if hasattr(server, 'active_connections') and chat_id in server.active_connections:
                ws = server.active_connections[chat_id]
                thinking_mode = server.session_thinking_mode.get(chat_id, True)
                print(f"[Scheduled Task Trigger] 找到活跃 WebSocket 连接")
            else:
                print(f"[Scheduled Task Trigger] 未找到活跃 WebSocket 连接")

            # 3. 走正常的消息处理流程
            # 获取 bot 对象
            bot = bots.get(bot_id)
            if not bot:
                return JSONResponse(
                    status_code=404,
                    content={"success": False, "error": f"Bot '{bot_id}' 不存在", "code": "BOT_NOT_FOUND"}
                )

            # 获取被@的上下文历史（从本次@追溯到上一次被@）
            mention_context = server._get_mention_context_history(
                chat_id, "system", system_message, bot_id
            )
            print(f"[Scheduled Task Trigger] mention_context: {len(mention_context)} 条消息")

            # 构建增强消息（带系统提示）
            if is_group:
                enhanced_message = f"@{bot_id} {description}\n\n[系统提示：这是定时任务触发，请基于上述对话上下文执行相关操作。]"
            else:
                enhanced_message = f"{description}\n\n[系统提示：这是定时任务触发，请基于上述对话上下文执行相关操作。]"

            print(f"[Scheduled Task Trigger] 触发 Bot 回复: bot_id={bot_id}, is_group={is_group}")

            # 使用 _single_chat_with_context 走正常的单聊流程（支持上下文）
            result = await server._single_chat_with_context(
                ws, bot_id, enhanced_message, chat_id,
                is_group=is_group, thinking_mode=thinking_mode,
                context_history=mention_context
            )

            print(f"[Scheduled Task Trigger] Bot 回复结果: {result[:100] if result else 'None'}...")

            # 群聊模式下 _single_chat_with_context 不会保存历史，需要手动保存
            if is_group and result:
                await server._add_to_history(chat_id, bot_id, result, is_group=True)
                print(f"[Scheduled Task Trigger] 已保存 Bot 回复到群聊历史")

            # 检查是否触发了级联回复（仅群聊）
            if is_group and result:
                print(f"[Scheduled Task Trigger] 检查级联回复...")
                await server._check_and_trigger_mention_cascade(
                    ws, bot_id, result, chat_id, thinking_mode=thinking_mode
                )

            return {
                "success": True,
                "message": "定时任务已触发",
                "data": {
                    "chat_id": chat_id,
                    "bot_id": bot_id,
                    "is_group": is_group
                }
            }

        except Exception as e:
            print(f"[Scheduled Task Trigger] 错误: {e}")
            import traceback
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e), "code": "INTERNAL_ERROR"}
            )

    @app.post("/api/debug/trigger-task")
    async def debug_trigger_task(request: Request):
        """
        调试接口：触发定时任务执行流程
        模拟定时任务执行，让指定 Bot 发送消息"1"

        Args:
            request: 包含 chat_id 和 bot_id 的请求
        """
        try:
            token = request.query_params.get('token', '')
            if token != auth_token:
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "error": "Invalid token"}
                )

            chat_id = request.query_params.get('chat_id')
            bot_id = request.query_params.get('bot_id')

            if not chat_id or not bot_id:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "缺少 chat_id 或 bot_id"}
                )

            print(f"[Debug Trigger] 触发定时任务调试: chat_id={chat_id}, bot_id={bot_id}")

            # 检查 Bot 是否存在
            if bot_id not in bots:
                return JSONResponse(
                    status_code=404,
                    content={"success": False, "error": f"Bot '{bot_id}' 不存在"}
                )

            # 获取会话元数据（支持群聊和单聊）
            # 使用新的 session.json 格式，向后兼容 meta.json
            bot_ids = [bot_id]
            is_group = False
            meta = {}

            # 1. 先检查群聊目录的 session.json
            session_path = os.path.join(base_workplace, "groupspace", f"g_{chat_id}", "session.json")
            if not os.path.exists(session_path):
                # 向后兼容：检查旧格式 meta.json
                session_path = os.path.join(base_workplace, "groupspace", f"g_{chat_id}", "meta.json")

            if os.path.exists(session_path):
                try:
                    with open(session_path, 'r', encoding='utf-8') as f:
                        data = json.load(f)
                    # 新格式：包含 meta 字段
                    if isinstance(data, dict) and 'meta' in data:
                        meta = data['meta']
                    else:
                        # 旧格式：直接是 meta 数据
                        meta = data
                    bot_ids = meta.get("bot_ids", [bot_id])
                    is_group = len(bot_ids) > 1
                except Exception as e:
                    print(f"[Debug Trigger] 读取群聊元数据失败: {e}")
            else:
                # 2. 检查单聊目录的 session.json
                single_session_path = os.path.join(base_workplace, f"workplace_{bot_id}", f"w_{chat_id}", "session.json")
                if not os.path.exists(single_session_path):
                    # 向后兼容：检查旧格式 meta.json
                    single_session_path = os.path.join(base_workplace, f"workplace_{bot_id}", f"w_{chat_id}", "meta.json")

                if os.path.exists(single_session_path):
                    try:
                        with open(single_session_path, 'r', encoding='utf-8') as f:
                            data = json.load(f)
                        # 新格式：包含 meta 字段
                        if isinstance(data, dict) and 'meta' in data:
                            meta = data['meta']
                        else:
                            # 旧格式：直接是 meta 数据
                            meta = data
                        bot_ids = meta.get("bot_ids", [bot_id])
                        is_group = False
                    except Exception as e:
                        print(f"[Debug Trigger] 读取单聊元数据失败: {e}")

            # 确定数据目录（群聊/单聊）
            if is_group:
                data_dir = os.path.join(base_workplace, "groupspace", f"g_{chat_id}")
            else:
                data_dir = os.path.join(base_workplace, f"workplace_{bot_id}", f"w_{chat_id}")

            print(f"[Debug Trigger] 数据目录: {data_dir}, is_group={is_group}, bot_ids={bot_ids}")

            # 切换到数据目录并更新 session.json
            original_dir = os.getcwd()
            os.makedirs(data_dir, exist_ok=True)
            os.chdir(data_dir)

            try:
                # 更新或创建 session.json（新格式，合并了 history.json 和 meta.json）
                session_file = os.path.join(data_dir, 'session.json')
                session_data = {"meta": {}, "messages": [], "stats": {}}

                if os.path.exists(session_file):
                    try:
                        with open(session_file, 'r', encoding='utf-8') as f:
                            session_data = json.load(f)
                    except:
                        pass
                else:
                    # 向后兼容：尝试读取旧的 meta.json
                    legacy_meta_file = os.path.join(data_dir, 'meta.json')
                    if os.path.exists(legacy_meta_file):
                        try:
                            with open(legacy_meta_file, 'r', encoding='utf-8') as f:
                                session_data["meta"] = json.load(f)
                        except:
                            pass

                now = time.time()
                session_data["meta"].update({
                    'id': chat_id,
                    'bot_ids': bot_ids,
                    'chat_type': 'group' if is_group else 'single',
                    'is_group': is_group,
                    'updated_at': now
                })
                if 'created_at' not in session_data["meta"]:
                    session_data["meta"]['created_at'] = now

                with open(session_file, 'w', encoding='utf-8') as f:
                    json.dump(session_data, f, ensure_ascii=False, indent=2)
                print(f"[Debug Trigger] 更新 session.json: {session_file}")

                # 调用 webchat_sender 发送消息
                sys.path.insert(0, os.path.join(base_workplace, f'workplace_{bot_id}', '.agents', 'skills', 'webchat-sender'))

                try:
                    from webchat_sender import send_message
                    result = send_message("1", chat_id=chat_id, is_system=False, bot_id=bot_id)
                    print(f"[Debug Trigger] 发送结果: {result}")

                    if result.get('success'):
                        return {
                            "success": True,
                            "message": f"Bot {bot_id} 已发送消息 '1'",
                            "data": {
                                "chat_id": chat_id,
                                "bot_id": bot_id,
                                "is_group": is_group,
                                "bot_ids": bot_ids,
                                "data_dir": data_dir
                            }
                        }
                    else:
                        return JSONResponse(
                            status_code=500,
                            content={"success": False, "error": result.get('message', '发送失败')}
                        )
                except Exception as e:
                    print(f"[Debug Trigger] 发送消息失败: {e}")
                    import traceback
                    traceback.print_exc()
                    return JSONResponse(
                        status_code=500,
                        content={"success": False, "error": f"发送消息失败: {str(e)}"}
                    )
                finally:
                    sys.path.pop(0)
            finally:
                os.chdir(original_dir)

        except Exception as e:
            print(f"[Debug Trigger] 错误: {e}")
            import traceback
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )

    @app.post("/api/internal/sandbox-chat")
    async def sandbox_chat(request: Request):
        """
        沙箱容器 AI 代理接口
        供 Docker 沙箱容器调用，由主进程代为执行 ACP AI 调用

        Args:
            request: {
                "prompt": "完整提示词（含系统上下文）",
                "bot_id": "可选，指定 bot",
                "_token": "认证 token"
            }

        Returns:
            {"success": true, "reply": "AI 回复内容"}
        """
        try:
            data = await request.json()
            token = data.pop('_token', '')
            if token != auth_token:
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "error": "Invalid token"}
                )

            prompt = data.get('prompt', '')
            bot_id = data.get('bot_id')
            if not prompt:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "Missing prompt"}
                )

            # 导入 ACPClient（主进程有完整的 kimi/opencode 配置）
            from clawdboz.communication.acp_client import ACPClient

            # 创建 ACPClient，如果指定了 bot_id 则使用该 bot 的客户端配置
            acp_client_id = None
            if bot_id and bot_id in bots:
                bot = bots[bot_id]
                # 尝试获取 bot 的 acp_client_id（从 config.json 或 bot 对象）
                if hasattr(bot, 'acp_client_id'):
                    acp_client_id = bot.acp_client_id

            client = ACPClient(acp_client_id=acp_client_id)
            reply = client.chat(prompt, timeout=120, include_thinking_in_result=False)

            return {
                "success": True,
                "reply": reply if reply else "[No reply]"
            }

        except Exception as e:
            print(f"[SandboxChat] 错误: {e}")
            import traceback
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )

    @app.get("/")
    async def root():
        """根路径，返回主页面"""
        from fastapi.responses import FileResponse
        static_dir = os.path.join(os.path.dirname(__file__), "..", "static")
        index_path = os.path.join(static_dir, "index.html")
        if os.path.exists(index_path):
            return FileResponse(index_path)
        return {
            "name": "Clawdboz Web Chat",
            "version": "3.0.0",
            "bots": list(bots.keys()),
            "websocket": f"ws://localhost:{server.port}/ws/chat?token=<your_token>"
        }
