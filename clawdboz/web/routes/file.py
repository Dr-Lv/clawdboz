#!/usr/bin/env python3
"""
File API Routes - 文件上传下载路由

提供文件上传、下载、目录浏览和终端命令执行功能。
"""

import os
import shutil
import subprocess
import uuid
from typing import TYPE_CHECKING

from fastapi import File, Form, UploadFile, Query, Request
from fastapi.responses import FileResponse, JSONResponse

if TYPE_CHECKING:
    from ..server_core import WebChatServer


def setup_file_routes(server: "WebChatServer"):
    """
    设置文件 API 路由

    Args:
        server: WebChatServer 实例
    """
    app = server.app
    auth_token = server.auth_token
    upload_dir = server.upload_dir
    base_workplace = server.base_workplace

    @app.post("/api/upload")
    async def upload_file(
        file: UploadFile = File(...),
        token: str = Form(...)
    ):
        """
        文件上传接口

        Args:
            file: 上传的文件
            token: 访问令牌

        Returns:
            {"success": true, "file_id": "...", "file_url": "...", ...}
        """
        if token != auth_token:
            return JSONResponse(
                status_code=403,
                content={"success": False, "error": "Invalid token"}
            )

        try:
            # 生成唯一文件名
            file_ext = os.path.splitext(file.filename)[1].lower()
            file_id = f"{uuid.uuid4().hex}{file_ext}"
            file_path = os.path.join(upload_dir, file_id)

            # 保存文件
            content = await file.read()
            with open(file_path, "wb") as f:
                f.write(content)

            file_size = len(content)

            # 判断文件类型
            image_exts = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg'}
            is_image = file_ext in image_exts

            # 将文件复制到 ACP 工作目录，供 Bot 读取
            try:
                if os.path.exists(base_workplace):
                    bot_file_path = os.path.join(base_workplace, file.filename)
                    shutil.copy2(file_path, bot_file_path)
                    print(f"[WebServer] 复制文件到工作目录: {bot_file_path}")
            except Exception as e:
                print(f"[WebServer] 复制文件到工作目录失败: {e}")

            return {
                "success": True,
                "file_id": file_id,
                "file_name": file.filename,
                "file_size": file_size,
                "file_type": "image" if is_image else "file",
                "file_url": f"/uploads/{file_id}",
                "is_image": is_image,
                "bot_path": file.filename  # 给 Bot 的路径（文件名）
            }
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )

    @app.get("/api/file/{file_id}")
    async def download_file(file_id: str, token: str = Query(...)):
        """
        文件下载接口

        Args:
            file_id: 文件ID
            token: 访问令牌
        """
        if token != auth_token:
            return JSONResponse(
                status_code=403,
                content={"success": False, "error": "Invalid token"}
            )

        file_path = os.path.join(upload_dir, file_id)
        if not os.path.exists(file_path):
            return JSONResponse(
                status_code=404,
                content={"success": False, "error": "File not found"}
            )

        return FileResponse(file_path)

    @app.get("/api/fs/list")
    async def list_directory(path: str = Query(""), token: str = Query(...)):
        """
        列出指定目录的内容

        Args:
            path: 相对或绝对目录路径
            token: 访问令牌
        """
        if token != auth_token:
            return JSONResponse(status_code=403, content={"success": False, "error": "Invalid token"})

        target_path = path if os.path.isabs(path) else os.path.join(base_workplace, path)
        target_path = os.path.abspath(target_path)
        # 安全检查：限制在 base_workplace 范围内
        if not target_path.startswith(os.path.abspath(base_workplace)):
            return JSONResponse(status_code=403, content={"success": False, "error": "Access denied"})

        if not os.path.exists(target_path):
            return JSONResponse(status_code=404, content={"success": False, "error": "Path not found"})
        if not os.path.isdir(target_path):
            return JSONResponse(status_code=400, content={"success": False, "error": "Not a directory"})

        try:
            items = []
            for name in sorted(os.listdir(target_path)):
                if name.startswith("."):
                    continue
                item_path = os.path.join(target_path, name)
                items.append({
                    "name": name,
                    "path": item_path,
                    "type": "dir" if os.path.isdir(item_path) else "file"
                })
            parent = os.path.dirname(target_path)
            parent = parent if parent.startswith(os.path.abspath(base_workplace)) else ""
            return {
                "success": True,
                "path": target_path,
                "parent": parent if parent != target_path else "",
                "items": items
            }
        except Exception as e:
            return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

    @app.post("/api/fs/execute")
    async def execute_command(request: Request, token: str = Query(...)):
        """
        在指定目录执行终端命令（白名单限制）

        Args:
            request: JSON body {cmd, cwd}
            token: 访问令牌
        """
        if token != auth_token:
            return JSONResponse(status_code=403, content={"success": False, "error": "Invalid token"})

        try:
            body = await request.json()
            cmd = body.get("cmd", "").strip()
            cwd = body.get("cwd", base_workplace)
        except Exception:
            return JSONResponse(status_code=400, content={"success": False, "error": "Invalid JSON"})

        if not cmd:
            return JSONResponse(status_code=400, content={"success": False, "error": "Empty command"})

        # 安全检查：限制工作目录
        target_cwd = cwd if os.path.isabs(cwd) else os.path.join(base_workplace, cwd)
        target_cwd = os.path.abspath(target_cwd)
        if not target_cwd.startswith(os.path.abspath(base_workplace)):
            return JSONResponse(status_code=403, content={"success": False, "error": "Access denied"})

        # 命令白名单（只读 + 安全操作）
        allowed_prefixes = ("ls", "cat", "pwd", "echo", "head", "tail", "find", "grep", "wc", "file", "tree", "du", "df")
        if not any(cmd.split()[0] == p for p in allowed_prefixes):
            return JSONResponse(status_code=403, content={"success": False, "error": f"Command '{cmd.split()[0]}' not allowed"})

        # 禁止危险字符
        dangerous = (";", "&&", "||", "|", "`", "$", "<", ">")
        if any(d in cmd for d in dangerous):
            return JSONResponse(status_code=403, content={"success": False, "error": "Dangerous characters detected"})

        try:
            result = subprocess.run(
                cmd,
                shell=True,
                cwd=target_cwd,
                capture_output=True,
                text=True,
                timeout=10
            )
            output = result.stdout + (result.stderr if result.stderr else "")
            return {"success": True, "output": output, "returncode": result.returncode}
        except subprocess.TimeoutExpired:
            return JSONResponse(status_code=500, content={"success": False, "error": "Command timeout"})
        except Exception as e:
            return JSONResponse(status_code=500, content={"success": False, "error": str(e)})
