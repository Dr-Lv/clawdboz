#!/usr/bin/env python3
"""
Session Meta Routes - 会话元数据路由

提供会话列表、获取、创建、删除和清空等管理功能。

新版本：使用 session.json 合并 history.json 和 meta.json
保持向后兼容：如果 session.json 不存在，自动迁移旧数据
"""

import json
import os
import shutil
import time
from typing import TYPE_CHECKING

from fastapi import Request, Query
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from ...server_core import WebChatServer


def _load_session_file(session_path: str) -> dict:
    """加载 session.json 文件（支持向后兼容）

    1. 如果 session.json 存在，直接读取
    2. 如果 session.json 不存在，尝试合并 history.json 和 meta.json
    3. 如果都不存在，返回空结构
    """
    if os.path.exists(session_path):
        try:
            with open(session_path, 'r', encoding='utf-8') as f:
                return json.load(f)
        except Exception as e:
            print(f"[_load_session_file] 读取 session.json 失败: {e}")

    # 向后兼容：尝试读取旧文件
    legacy_history_path = session_path.replace('session.json', 'history.json')
    legacy_meta_path = session_path.replace('session.json', 'meta.json')

    result = {"meta": {}, "messages": [], "stats": {}}

    # 读取旧 history.json
    if os.path.exists(legacy_history_path):
        try:
            with open(legacy_history_path, 'r', encoding='utf-8') as f:
                history_data = json.load(f)
            if isinstance(history_data, dict) and 'messages' in history_data:
                result["messages"] = history_data["messages"]
                # 迁移其他字段到 meta
                for key in ['bot_ids', 'name']:
                    if key in history_data:
                        result["meta"][key] = history_data[key]
            elif isinstance(history_data, list):
                result["messages"] = history_data
        except Exception as e:
            print(f"[_load_session_file] 读取旧 history.json 失败: {e}")

    # 读取旧 meta.json
    if os.path.exists(legacy_meta_path):
        try:
            with open(legacy_meta_path, 'r', encoding='utf-8') as f:
                meta_data = json.load(f)
            result["meta"].update(meta_data)
        except Exception as e:
            print(f"[_load_session_file] 读取旧 meta.json 失败: {e}")

    return result


def _get_session_info_from_dir(session_dir: str) -> dict:
    """从会话目录读取会话信息

    优先读取 session.json，如果不存在则尝试旧格式
    """
    session_path = os.path.join(session_dir, 'session.json')

    # 检查 session.json 是否存在
    if os.path.exists(session_path):
        try:
            with open(session_path, 'r', encoding='utf-8') as f:
                session_data = json.load(f)

            meta = session_data.get('meta', {})
            messages = session_data.get('messages', [])

            return {
                'bot_ids': meta.get('bot_ids', []),
                'name': meta.get('name', ''),
                'messages': messages,
                'source': meta.get('source', 'web'),
                'exists': True
            }
        except Exception as e:
            print(f"[_get_session_info] 读取 session.json 失败: {session_dir}, {e}")

    # 向后兼容：尝试旧格式
    try:
        history_path = os.path.join(session_dir, 'history.json')
        meta_path = os.path.join(session_dir, 'meta.json')

        bot_ids = []
        name = ""
        messages = []

        # 读取 meta.json
        source = "web"
        if os.path.exists(meta_path):
            with open(meta_path, 'r', encoding='utf-8') as f:
                meta_data = json.load(f)
            bot_ids = meta_data.get("bot_ids", [])
            name = meta_data.get("name", "")
            source = meta_data.get("source", "web")

        # 读取 history.json
        if os.path.exists(history_path):
            with open(history_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
            messages = data.get("messages", [])
            # 如果 meta 中没有，尝试从 history 读取
            if not bot_ids:
                bot_ids = data.get("bot_ids", [])
            if not name:
                name = data.get("name", "")

        return {
            'bot_ids': bot_ids,
            'name': name,
            'messages': messages,
            'source': source,
            'exists': os.path.exists(history_path) or os.path.exists(meta_path)
        }
    except Exception as e:
        print(f"[_get_session_info] 读取旧格式失败: {session_dir}, {e}")

    return {'bot_ids': [], 'name': '', 'messages': [], 'exists': False}


def setup_session_meta_routes(server: "WebChatServer"):
    """
    设置会话元数据路由

    Args:
        server: WebChatServer 实例
    """
    app = server.app
    auth_token = server.auth_token
    base_workplace = server.base_workplace
    bots = server.bots

    @app.get("/api/sessions")
    async def list_sessions(token: str = Query(...)):
        """
        获取所有保存的会话列表（用于前端恢复会话）

        Returns:
            {
                "sessions": [
                    {
                        "id": "session-xxx",
                        "bot_ids": ["bot1", "bot2"],
                        "name": "会话名称",
                        "last_message": "...",
                        "updated_at": 1234567890
                    }
                ]
            }
        """
        if token != auth_token:
            return JSONResponse(
                status_code=403,
                content={"success": False, "error": "Invalid token"}
            )

        try:
            sessions_dict = {}

            # 1. 从 groupspace 目录读取群聊会话
            groupspace_dir = os.path.join(base_workplace, 'groupspace')
            if os.path.isdir(groupspace_dir):
                for dirname in os.listdir(groupspace_dir):
                    if dirname.startswith('g_session_'):
                        chat_id = dirname[2:]  # 移除 'g_' 前缀
                        session_dir = os.path.join(groupspace_dir, dirname)

                        # 使用统一的方法读取会话信息
                        info = _get_session_info_from_dir(session_dir)

                        if not info['exists']:
                            continue

                        messages = info['messages']
                        bot_ids = info['bot_ids']
                        name = info['name']

                        # 从 session.json 读取 source
                        session_source = info.get('source', 'web')
                        if messages:
                            last_msg = messages[-1]
                            sessions_dict[chat_id] = {
                                "id": chat_id,
                                "bot_ids": bot_ids,
                                "name": name,
                                "last_message": last_msg.get("content", "")[:50],
                                "updated_at": last_msg.get("time", 0),
                                "message_count": len(messages),
                                "source": session_source
                            }
                        else:
                            # 尝试从目录修改时间获取
                            stat = os.stat(session_dir)
                            sessions_dict[chat_id] = {
                                "id": chat_id,
                                "bot_ids": bot_ids,
                                "name": name,
                                "last_message": "",
                                "updated_at": stat.st_mtime,
                                "message_count": 0,
                                "source": session_source
                            }

            # 2. 从所有 workplace_* 目录读取单聊会话（web 会话 w_ 前缀）
            for entry in os.listdir(base_workplace):
                if not entry.startswith('workplace_') or entry == 'workplace_system':
                    continue
                bot_work_dir = os.path.join(base_workplace, entry)
                if not os.path.isdir(bot_work_dir):
                    continue
                bot_id = entry[len('workplace_'):]

                for dirname in os.listdir(bot_work_dir):
                    if dirname.startswith('w_session_') or dirname.startswith('f_'):
                        # w_ 前缀：web 会话；f_ 前缀：飞书会话
                        chat_id = dirname[2:]  # 移除 'w_' 或 'f_' 前缀

                        # 防御性检查：如果该 session 在 groupspace 中存在且是真正的群聊，跳过 workplace 数据
                        # 修复：groupspace 中的文件可能是 _save_session_meta 误保存的单聊数据，需要检查
                        group_session_path = os.path.join(base_workplace, "groupspace", f"g_{chat_id}", "session.json")
                        group_meta_path = os.path.join(base_workplace, "groupspace", f"g_{chat_id}", "meta.json")
                        is_real_group = False
                        if os.path.exists(group_session_path):
                            group_data = _load_session_file(group_session_path)
                            group_bot_ids = group_data.get("meta", {}).get("bot_ids", [])
                            group_messages = group_data.get("messages", [])
                            # 真正的群聊：有多个 bot，或有实际消息
                            if len(group_bot_ids) > 1 or len(group_messages) > 0:
                                is_real_group = True
                        elif os.path.exists(group_meta_path):
                            # 旧格式 meta.json 存在，说明是真正的群聊
                            is_real_group = True

                        if is_real_group:
                            continue

                        session_dir = os.path.join(bot_work_dir, dirname)
                        info = _get_session_info_from_dir(session_dir)

                        if not info['exists']:
                            continue

                        messages = info['messages']
                        name = info['name']
                        session_source = info.get('source', 'web')

                        if messages:
                            last_msg = messages[-1]
                            sessions_dict[chat_id] = {
                                "id": chat_id,
                                "bot_ids": [bot_id],
                                "name": name or f"与 {bot_id} 的对话",
                                "last_message": last_msg.get("content", "")[:50],
                                "updated_at": last_msg.get("time", 0),
                                "message_count": len(messages),
                                "source": session_source
                            }
                        else:
                            stat = os.stat(session_dir)
                            sessions_dict[chat_id] = {
                                "id": chat_id,
                                "bot_ids": [bot_id],
                                "name": name or f"与 {bot_id} 的对话",
                                "last_message": "",
                                "updated_at": stat.st_mtime,
                                "message_count": 0,
                                "source": session_source
                            }

            # 按时间倒序排列
            sessions = list(sessions_dict.values())
            sessions.sort(key=lambda x: x["updated_at"], reverse=True)

            return {"sessions": sessions}
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )

    @app.get("/api/sessions/{chat_id}")
    async def get_session(chat_id: str, token: str = Query(...)):
        """
        获取指定会话的完整信息（包含聊天记录和元数据）
        """
        if token != auth_token:
            return JSONResponse(
                status_code=403,
                content={"success": False, "error": "Invalid token"}
            )

        try:
            # 收集所有来源的历史记录
            all_messages = []

            # 1. 从 groupspace 读取
            group_history = await server._load_session_history(chat_id, is_group=True)
            all_messages.extend(group_history)

            # 2. 从所有 workplace_* 读取（兼容旧数据和单聊数据分散的情况）
            if os.path.exists(base_workplace):
                for entry in os.listdir(base_workplace):
                    if entry.startswith("workplace_") and entry != 'workplace_system':
                        bot_id = entry[len("workplace_"):]
                        wh = await server._load_session_history(chat_id, is_group=False, bot_id=bot_id)
                        if wh:
                            all_messages.extend(wh)

            # 3. 去重并排序
            seen = set()
            unique_messages = []
            for m in all_messages:
                key = (m.get("sender"), m.get("content"), m.get("time"))
                if key not in seen:
                    seen.add(key)
                    unique_messages.append(m)
            unique_messages.sort(key=lambda x: x.get("time", 0))

            # 读取元数据（bot_ids, name）
            bot_ids = []
            name = ""
            is_group = False
            try:
                # 优先从 session.json 读取
                session_paths = []
                # groupspace session.json
                g_session = os.path.join(base_workplace, "groupspace", f"g_{chat_id}", "session.json")
                if g_session not in session_paths:
                    session_paths.append(g_session)
                # 动态查找所有 workplace_*/w_{chat_id}/session.json
                if os.path.exists(base_workplace):
                    for entry in os.listdir(base_workplace):
                        if entry.startswith("workplace_") and entry != 'workplace_system':
                            sp = os.path.join(base_workplace, entry, f"w_{chat_id}", "session.json")
                            if sp not in session_paths:
                                session_paths.append(sp)

                for sp in session_paths:
                    if os.path.exists(sp):
                        session_data = _load_session_file(sp)
                        meta = session_data.get("meta", {})
                        sp_bot_ids = meta.get("bot_ids", [])
                        sp_name = meta.get("name", "")
                        sp_messages = session_data.get("messages", [])

                        # 对于 groupspace 中的文件，检查是否是真正的群聊
                        # 修复：groupspace 中可能是 _save_session_meta 误保存的单聊数据
                        if sp.startswith(os.path.join(base_workplace, "groupspace")):
                            if len(sp_bot_ids) > 1 or len(sp_messages) > 0:
                                # 真正的群聊
                                bot_ids = sp_bot_ids
                                name = sp_name
                                is_group = len(bot_ids) > 1
                                break
                            else:
                                # 可能是误保存的单聊数据（空的 groupspace 文件），继续查找 workplace
                                continue
                        else:
                            # workplace 中的文件，直接使用
                            bot_ids = sp_bot_ids
                            name = sp_name
                            is_group = len(bot_ids) > 1
                            break

                # 如果从 session.json 没找到，尝试旧格式
                if not bot_ids and unique_messages:
                    # 尝试 groupspace 旧文件
                    legacy_session_path = os.path.join(base_workplace, "groupspace", f"g_{chat_id}", "session.json")
                    legacy_data = _load_session_file(legacy_session_path)
                    bot_ids = legacy_data.get("meta", {}).get("bot_ids", [])
                    name = legacy_data.get("meta", {}).get("name", "")

                    # 尝试 workplace 旧文件
                    if not bot_ids:
                        for entry in os.listdir(base_workplace):
                            if entry.startswith("workplace_"):
                                legacy_path = os.path.join(base_workplace, entry, f"w_{chat_id}", "session.json")
                                legacy_data = _load_session_file(legacy_path)
                                bot_ids = legacy_data.get("meta", {}).get("bot_ids", [])
                                name = legacy_data.get("meta", {}).get("name", "")
                                if bot_ids:
                                    break
                    is_group = len(bot_ids) > 1
            except Exception as e:
                print(f"[Get Session] 读取元数据失败: {e}")

            return {
                "id": chat_id,
                "name": name,
                "bot_ids": bot_ids,
                "is_group": is_group,
                "messages": unique_messages
            }
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )

    @app.delete("/api/sessions/{chat_id}")
    async def delete_session(chat_id: str, token: str = Query(...)):
        """删除指定会话的历史记录和对应的工作目录"""
        if token != auth_token:
            return JSONResponse(
                status_code=403,
                content={"success": False, "error": "Invalid token"}
            )

        try:
            # 1. 删除历史记录文件（session.json 和旧格式）
            session_path = os.path.join(
                base_workplace, 'groupspace', f'g_{chat_id}', 'session.json'
            )
            if os.path.exists(session_path):
                os.remove(session_path)
                print(f"[WebServer] 删除会话文件: {session_path}")

            # 同时删除旧格式文件
            for filename in ['history.json', 'meta.json']:
                old_path = os.path.join(base_workplace, 'groupspace', f'g_{chat_id}', filename)
                if os.path.exists(old_path):
                    os.remove(old_path)
                    print(f"[WebServer] 删除旧格式文件: {old_path}")

            # 2. 从内存中移除
            async with server._chat_history_lock:
                if chat_id in server._chat_history:
                    del server._chat_history[chat_id]

            # 3. 删除对应的工作目录
            # 单聊目录: workplace_[bot_id]/w_[chat_id]/
            # 群聊目录: groupspace/g_[chat_id]/
            deleted_dirs = []

            for entry in os.listdir(base_workplace):
                if not entry.startswith('workplace_') or entry == 'workplace_system':
                    continue
                bot_work_dir = os.path.join(base_workplace, entry)
                if not os.path.isdir(bot_work_dir):
                    continue
                bot_id = entry[len('workplace_'):]

                # 尝试删除单聊 session 目录
                session_dir = os.path.join(bot_work_dir, f"w_{chat_id}")
                if os.path.exists(session_dir):
                    shutil.rmtree(session_dir)
                    deleted_dirs.append(session_dir)

                # 尝试删除群聊 session 目录 (g_ 前缀) - 可能是软链接
                group_session_dir = os.path.join(bot_work_dir, f"g_{chat_id}")
                if os.path.islink(group_session_dir):
                    os.remove(group_session_dir)
                    deleted_dirs.append(group_session_dir)
                elif os.path.exists(group_session_dir):
                    shutil.rmtree(group_session_dir)
                    deleted_dirs.append(group_session_dir)

                # 尝试删除飞书 session 目录 (f_ 前缀)
                feishu_session_dir = os.path.join(bot_work_dir, f"f_{chat_id}")
                if os.path.exists(feishu_session_dir):
                    shutil.rmtree(feishu_session_dir)
                    deleted_dirs.append(feishu_session_dir)

            # 删除 workplace_system 中可能存在的错误数据
            system_session_dir = os.path.join(
                base_workplace,
                "workplace_system",
                f"w_{chat_id}"
            )
            if os.path.exists(system_session_dir):
                shutil.rmtree(system_session_dir)
                deleted_dirs.append(system_session_dir)

            # 删除群聊共享目录
            group_dir = os.path.join(base_workplace, "groupspace", f"g_{chat_id}")
            if os.path.exists(group_dir):
                shutil.rmtree(group_dir)
                deleted_dirs.append(group_dir)

            if deleted_dirs:
                print(f"[WebServer] 删除会话 {chat_id} 的工作目录: {len(deleted_dirs)} 个")

            return {"success": True, "deleted_dirs": len(deleted_dirs)}
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )

    @app.post("/api/sessions/{chat_id}/clear")
    async def clear_session(chat_id: str, token: str = Query(...)):
        """清空指定会话的聊天记录（保留会话元数据）"""
        if token != auth_token:
            return JSONResponse(
                status_code=403,
                content={"success": False, "error": "Invalid token"}
            )

        try:
            # 从 session.json 读取会话类型和 bot_ids
            session_path = os.path.join(base_workplace, "groupspace", f"g_{chat_id}", "session.json")

            # 向后兼容：检查旧格式
            if not os.path.exists(session_path):
                session_path = os.path.join(base_workplace, "groupspace", f"g_{chat_id}", "meta.json")

            is_group = False
            bot_id = None
            bot_ids = []
            if os.path.exists(session_path):
                with open(session_path, 'r', encoding='utf-8') as f:
                    if session_path.endswith('session.json'):
                        session_data = json.load(f)
                        meta = session_data.get("meta", {})
                    else:
                        meta = json.load(f)
                bot_ids = meta.get("bot_ids", [])
                is_group = meta.get("is_group", len(bot_ids) > 1)
                if not is_group and bot_ids:
                    bot_id = bot_ids[0]

            # 清空内存中的历史记录
            async with server._chat_history_lock:
                if chat_id in server._chat_history:
                    server._chat_history[chat_id] = []

            # 持久化空历史记录（保留 session.json 文件但 messages 为空）
            await server._save_session_history(chat_id, is_group=is_group, bot_id=bot_id, bot_ids=bot_ids)

            print(f"[WebServer] 已清空会话记录: {chat_id}")
            return {"success": True, "message": "Session cleared"}
        except Exception as e:
            print(f"[WebServer] 清空会话失败: {chat_id}, {e}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )

    @app.post("/api/sessions")
    async def create_session(request: Request, token: str = Query(...)):
        """创建或更新会话记录（用于前端新建会话）"""
        if token != auth_token:
            return JSONResponse(
                status_code=403,
                content={"success": False, "error": "Invalid token"}
            )

        try:
            data = await request.json()
            chat_id = data.get("id")
            bot_ids = data.get("bot_ids", [])
            name = data.get("name", "")
            source = data.get("source", "web")  # 会话来源：web 或 feishu

            print(f"[create_session] Received data: chat_id={chat_id}, bot_ids={bot_ids}, name={name}, source={source}")

            if not chat_id:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "Missing session id"}
                )

            # 创建空的会话历史记录
            async with server._chat_history_lock:
                if chat_id not in server._chat_history:
                    server._chat_history[chat_id] = []

            # 判断单聊还是群聊
            is_group = len(bot_ids) > 1

            # 保存到文件（创建空记录）
            await server._save_session_history(chat_id, is_group=is_group, bot_id=bot_ids[0] if bot_ids else None, bot_ids=bot_ids, name=name)

            # 保存会话元数据到 session.json
            if is_group:
                # 群聊：保存到 groupspace
                session_dir = os.path.join(base_workplace, "groupspace", f"g_{chat_id}")
            else:
                # 单聊：保存到 workplace_{bot_id}
                bot_id = bot_ids[0] if bot_ids else (list(bots.keys())[0] if bots else None)
                if not bot_id:
                    return JSONResponse(
                        status_code=400,
                        content={"success": False, "error": "No bot available"}
                    )
                session_dir = os.path.join(base_workplace, f"workplace_{bot_id}", f"w_{chat_id}")

            os.makedirs(session_dir, exist_ok=True)

            now = time.time()
            session_path = os.path.join(session_dir, "session.json")

            # 读取现有 session.json（如果有）
            session_data = {"meta": {}, "messages": [], "stats": {}}
            if os.path.exists(session_path):
                with open(session_path, 'r', encoding='utf-8') as f:
                    session_data = json.load(f)

            # 更新 meta
            session_data["meta"].update({
                "id": chat_id,
                "bot_ids": bot_ids,
                "name": name,
                "chat_type": "group" if is_group else "single",
                "is_group": is_group,
                "source": source,
                "updated_at": now
            })
            if "created_at" not in session_data["meta"]:
                session_data["meta"]["created_at"] = now

            with open(session_path, 'w', encoding='utf-8') as f:
                json.dump(session_data, f, ensure_ascii=False, indent=2)

            # 为群聊创建软链接到每个 Bot 的 workplace
            if is_group:
                print(f"[WebServer] 开始为群聊 {chat_id} 创建 Bot 软链接")
                for bot_id in bot_ids:
                    bot_work_dir = os.path.join(base_workplace, f"workplace_{bot_id}")
                    if os.path.exists(bot_work_dir):
                        link_path = os.path.join(bot_work_dir, f"g_{chat_id}")
                        try:
                            # 如果已存在，先删除
                            if os.path.exists(link_path) or os.path.islink(link_path):
                                if os.path.islink(link_path):
                                    os.remove(link_path)
                                else:
                                    shutil.rmtree(link_path)
                            # 创建软链接
                            os.symlink(session_dir, link_path, target_is_directory=True)
                            print(f"[WebServer] 为 Bot {bot_id} 创建软链接: {link_path}")
                        except Exception as e:
                            print(f"[WebServer] 为 Bot {bot_id} 创建软链接失败: {e}")

            print(f"[WebServer] 创建{'群聊' if is_group else '单聊'}记录: {chat_id}, bots: {bot_ids}, name: {name}")
            return {"success": True, "id": chat_id}
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )
