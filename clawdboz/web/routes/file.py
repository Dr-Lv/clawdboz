#!/usr/bin/env python3
"""
File API Routes - 文件上传下载路由

提供文件上传和下载功能。
"""

import os
import shutil
import uuid
from typing import TYPE_CHECKING

from fastapi import File, Form, UploadFile, Query
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
