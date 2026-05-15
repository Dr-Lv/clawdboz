#!/usr/bin/env python3
"""
Session Scheduler Routes - 会话定时任务路由

提供定时任务的获取、创建、更新、删除功能。
数据保存到对应会话的 scheduler_tasks.json 文件中。
"""

import json
import os
import time
from typing import TYPE_CHECKING

from fastapi import Request, Query
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from ...server_core import WebChatServer


def get_scheduler_tasks_path(base_workplace: str, chat_id: str, is_group: bool = True, bot_id: str = None) -> str:
    """
    获取定时任务文件路径

    Args:
        base_workplace: 基础 workplace 路径
        chat_id: 会话 ID
        is_group: 是否为群聊
        bot_id: Bot ID（单聊时使用）

    Returns:
        scheduler_tasks.json 文件路径
    """
    if is_group:
        # 群聊：groupspace/g_{chat_id}/scheduler_tasks.json
        return os.path.join(base_workplace, 'groupspace', f'g_{chat_id}', 'scheduler_tasks.json')
    else:
        # 单聊：workplace_{bot_id}/w_{chat_id}/scheduler_tasks.json
        if bot_id:
            return os.path.join(base_workplace, f'workplace_{bot_id}', f'w_{chat_id}', 'scheduler_tasks.json')
        return None


def load_scheduler_tasks(tasks_path: str) -> dict:
    """加载定时任务数据"""
    if not tasks_path or not os.path.exists(tasks_path):
        return {"task_id_counter": 1, "tasks": {}}

    try:
        with open(tasks_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[Scheduler] 加载任务失败: {e}")
        return {"task_id_counter": 1, "tasks": {}}


def save_scheduler_tasks(tasks_path: str, data: dict):
    """保存定时任务数据"""
    try:
        os.makedirs(os.path.dirname(tasks_path), exist_ok=True)
        with open(tasks_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
        return True
    except Exception as e:
        print(f"[Scheduler] 保存任务失败: {e}")
        return False


def setup_session_scheduler_routes(server: "WebChatServer"):
    """
    设置会话定时任务路由

    Args:
        server: WebChatServer 实例
    """
    app = server.app
    auth_token = server.auth_token
    base_workplace = server.base_workplace

    @app.get("/api/sessions/scheduler/tasks")
    async def get_scheduler_tasks(
        chat_id: str = Query(...),
        is_group: bool = Query(True),
        bot_id: str = Query(None),
        token: str = Query(...)
    ):
        """获取会话的定时任务列表"""
        if token != auth_token:
            return JSONResponse(
                status_code=403,
                content={"success": False, "error": "Invalid token"}
            )

        try:
            tasks_path = get_scheduler_tasks_path(base_workplace, chat_id, is_group, bot_id)
            if not tasks_path:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "Invalid bot_id for single chat"}
                )

            data = load_scheduler_tasks(tasks_path)

            # 转换为列表格式返回
            tasks_list = []
            for task_id, task in data.get("tasks", {}).items():
                tasks_list.append({
                    "id": task.get("id"),
                    "description": task.get("description", ""),
                    "time_interval": task.get("time_interval", 0),
                    "execute_time": task.get("execute_time", 0),
                    "status": task.get("status", "pending"),
                    "bot_id": task.get("bot_id"),
                    "chat_id": task.get("chat_id")
                })

            return {
                "success": True,
                "tasks": tasks_list
            }

        except Exception as e:
            print(f"[Scheduler API] 获取任务失败: {e}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )

    @app.post("/api/sessions/scheduler/tasks/save")
    async def save_scheduler_tasks_api(request: Request):
        """保存定时任务（创建或更新）"""
        try:
            data = await request.json()
            token = data.get('token')

            if token != auth_token:
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "error": "Invalid token"}
                )

            chat_id = data.get('chat_id')
            is_group = data.get('is_group', True)
            bot_id = data.get('bot_id')
            task = data.get('task', {})

            if not chat_id:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "Missing chat_id"}
                )

            tasks_path = get_scheduler_tasks_path(base_workplace, chat_id, is_group, bot_id)
            if not tasks_path:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "Invalid bot_id for single chat"}
                )

            # 加载现有任务
            tasks_data = load_scheduler_tasks(tasks_path)

            task_id = task.get('id')

            if task_id and task_id in tasks_data.get("tasks", {}):
                # 更新现有任务
                tasks_data["tasks"][task_id].update({
                    "description": task.get('description', ''),
                    "time_interval": task.get('time_interval', 0),
                    "execute_time": task.get('execute_time', time.time()),
                    "status": task.get('status', 'pending'),
                    "bot_id": task.get('bot_id', bot_id),
                    "chat_id": chat_id
                })
            else:
                # 创建新任务
                if not task_id:
                    task_id = str(tasks_data.get("task_id_counter", 1))
                    tasks_data["task_id_counter"] = tasks_data.get("task_id_counter", 1) + 1

                tasks_data["tasks"][task_id] = {
                    "id": task_id,
                    "description": task.get('description', ''),
                    "time_interval": task.get('time_interval', 0),
                    "execute_time": task.get('execute_time', time.time()),
                    "status": task.get('status', 'pending'),
                    "bot_id": task.get('bot_id', bot_id),
                    "chat_id": chat_id
                }

            # 保存
            if save_scheduler_tasks(tasks_path, tasks_data):
                return {
                    "success": True,
                    "task": tasks_data["tasks"][task_id]
                }
            else:
                return JSONResponse(
                    status_code=500,
                    content={"success": False, "error": "Failed to save tasks"}
                )

        except Exception as e:
            print(f"[Scheduler API] 保存任务失败: {e}")
            import traceback
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )

    @app.post("/api/sessions/scheduler/tasks/delete")
    async def delete_scheduler_task(request: Request):
        """删除定时任务"""
        try:
            data = await request.json()
            token = data.get('token')

            if token != auth_token:
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "error": "Invalid token"}
                )

            chat_id = data.get('chat_id')
            is_group = data.get('is_group', True)
            bot_id = data.get('bot_id')
            task_id = data.get('task_id')

            if not chat_id or not task_id:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "Missing chat_id or task_id"}
                )

            tasks_path = get_scheduler_tasks_path(base_workplace, chat_id, is_group, bot_id)
            if not tasks_path:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "Invalid bot_id for single chat"}
                )

            # 加载现有任务
            tasks_data = load_scheduler_tasks(tasks_path)

            if task_id in tasks_data.get("tasks", {}):
                del tasks_data["tasks"][task_id]

                if save_scheduler_tasks(tasks_path, tasks_data):
                    return {"success": True}
                else:
                    return JSONResponse(
                        status_code=500,
                        content={"success": False, "error": "Failed to save tasks"}
                    )
            else:
                return JSONResponse(
                    status_code=404,
                    content={"success": False, "error": "Task not found"}
                )

        except Exception as e:
            print(f"[Scheduler API] 删除任务失败: {e}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )

    @app.post("/api/sessions/scheduler/tasks/toggle")
    async def toggle_scheduler_task(request: Request):
        """启用/禁用定时任务"""
        try:
            data = await request.json()
            token = data.get('token')

            if token != auth_token:
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "error": "Invalid token"}
                )

            chat_id = data.get('chat_id')
            is_group = data.get('is_group', True)
            bot_id = data.get('bot_id')
            task_id = data.get('task_id')
            enabled = data.get('enabled', True)

            if not chat_id or not task_id:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "Missing chat_id or task_id"}
                )

            tasks_path = get_scheduler_tasks_path(base_workplace, chat_id, is_group, bot_id)
            if not tasks_path:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "Invalid bot_id for single chat"}
                )

            # 加载现有任务
            tasks_data = load_scheduler_tasks(tasks_path)

            if task_id in tasks_data.get("tasks", {}):
                tasks_data["tasks"][task_id]["status"] = "pending" if enabled else "paused"

                if save_scheduler_tasks(tasks_path, tasks_data):
                    return {
                        "success": True,
                        "status": tasks_data["tasks"][task_id]["status"]
                    }
                else:
                    return JSONResponse(
                        status_code=500,
                        content={"success": False, "error": "Failed to save tasks"}
                    )
            else:
                return JSONResponse(
                    status_code=404,
                    content={"success": False, "error": "Task not found"}
                )

        except Exception as e:
            print(f"[Scheduler API] 切换任务状态失败: {e}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )
