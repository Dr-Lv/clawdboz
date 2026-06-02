#!/usr/bin/env python3
"""
File API Routes - 文件上传下载路由

提供文件上传、下载、目录浏览、文件预览、终端命令执行和自动补全功能。
"""

import glob
import os
import re
import shutil
import subprocess
import uuid
from typing import TYPE_CHECKING

from fastapi import File, Form, UploadFile, Query, Request
from fastapi.responses import FileResponse, JSONResponse, PlainTextResponse

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
    abs_base = os.path.abspath(base_workplace)

    def _resolve_path(path: str, default: str) -> str:
        """解析路径，返回绝对路径"""
        if not path or path == '.':
            return default
        target = path if os.path.isabs(path) else os.path.join(default, path)
        return os.path.abspath(target)

    def _check_access(target_path: str, allowed_dir: str) -> bool:
        """检查路径是否在允许目录范围内"""
        return target_path.startswith(os.path.abspath(allowed_dir))

    @app.get("/api/version")
    async def get_version(token: str = Query(...)):
        """获取当前本地版本号"""
        if token != auth_token:
            return JSONResponse(status_code=403, content={"success": False, "error": "Invalid token"})
        try:
            version_file = os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "VERSION")
            with open(version_file, "r", encoding="utf-8") as f:
                local_version = f.read().strip()
        except Exception:
            local_version = "5.0.0"
        return {"success": True, "version": local_version}

    def _find_session_dir(session_id: str) -> str:
        """根据 session_id 查找对应的会话工作目录"""
        if not session_id:
            return ""
        # 1. 查找单聊 workplace 下的 w_session_id 或 f_session_id
        if os.path.exists(base_workplace):
            for entry in os.listdir(base_workplace):
                if entry.startswith("workplace_") and entry != 'workplace_system':
                    for prefix in ("w_", "f_"):
                        sp = os.path.join(base_workplace, entry, f"{prefix}{session_id}")
                        if os.path.isdir(sp):
                            return sp
        # 2. 查找群聊 groupspace
        group_dir = os.path.join(base_workplace, "groupspace", f"g_{session_id}")
        if os.path.isdir(group_dir):
            return group_dir
        return ""

    @app.post("/api/upload")
    async def upload_file(
        file: UploadFile = File(...),
        token: str = Form(...)
    ):
        """
        文件上传接口
        """
        if token != auth_token:
            return JSONResponse(
                status_code=403,
                content={"success": False, "error": "Invalid token"}
            )

        try:
            file_ext = os.path.splitext(file.filename)[1].lower()
            file_id = f"{uuid.uuid4().hex}{file_ext}"
            file_path = os.path.join(upload_dir, file_id)

            content = await file.read()
            with open(file_path, "wb") as f:
                f.write(content)

            file_size = len(content)

            image_exts = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg'}
            is_image = file_ext in image_exts

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
                "bot_path": file.filename
            }
        except Exception as e:
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )

    @app.get("/api/file/{file_id}")
    async def download_file(file_id: str, token: str = Query(...)):
        """文件下载接口（upload 上传的文件）"""
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

    @app.get("/api/fs/session-workdir")
    async def get_session_workdir(session_id: str = Query(""), token: str = Query(...)):
        """
        获取指定会话的工作目录

        在 base_workplace 下查找 workplace_*/w_{session_id} 或 groupspace/g_{session_id}
        """
        if token != auth_token:
            return JSONResponse(status_code=403, content={"success": False, "error": "Invalid token"})

        session_dir = _find_session_dir(session_id)
        if session_dir:
            return {"success": True, "path": session_dir}
        return JSONResponse(status_code=404, content={"success": False, "error": "Session directory not found"})

    @app.get("/api/fs/list")
    async def list_directory(path: str = Query(""), session_dir: str = Query(""), token: str = Query(...)):
        """列出指定目录的内容"""
        if token != auth_token:
            return JSONResponse(status_code=403, content={"success": False, "error": "Invalid token"})

        allowed = session_dir if session_dir and os.path.isdir(session_dir) else abs_base
        target_path = _resolve_path(path, allowed)
        if not target_path.startswith(os.path.abspath(allowed)):
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
                    "rel_path": os.path.relpath(item_path, abs_base),
                    "type": "dir" if os.path.isdir(item_path) else "file"
                })
            parent = os.path.dirname(target_path)
            parent = parent if parent.startswith(abs_base) else ""
            return {
                "success": True,
                "path": target_path,
                "parent": parent if parent != target_path else "",
                "items": items
            }
        except Exception as e:
            return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

    @app.get("/api/fs/read")
    async def read_file(path: str = Query(""), token: str = Query(...)):
        """读取文件内容（用于文本预览和图片预览）"""
        if token != auth_token:
            return JSONResponse(status_code=403, content={"success": False, "error": "Invalid token"})

        if not path or path == '.':
            return JSONResponse(status_code=400, content={"success": False, "error": "Path required"})

        target_path = _resolve_path(path, base_workplace)
        if not target_path.startswith(abs_base):
            return JSONResponse(status_code=403, content={"success": False, "error": "Access denied"})

        if not os.path.exists(target_path) or not os.path.isfile(target_path):
            return JSONResponse(status_code=404, content={"success": False, "error": "File not found"})

        try:
            max_size = 100 * 1024
            image_exts = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg'}
            file_ext = os.path.splitext(target_path)[1].lower()
            if file_ext in image_exts:
                return FileResponse(target_path)

            with open(target_path, 'r', encoding='utf-8', errors='replace') as f:
                content = f.read(max_size)
            return PlainTextResponse(content)
        except Exception as e:
            return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

    @app.get("/api/fs/download")
    async def download_fs_file(path: str = Query(""), token: str = Query(...)):
        """下载文件系统中的文件"""
        if token != auth_token:
            return JSONResponse(status_code=403, content={"success": False, "error": "Invalid token"})

        if not path or path == '.':
            return JSONResponse(status_code=400, content={"success": False, "error": "Path required"})

        target_path = _resolve_path(path, base_workplace)
        if not target_path.startswith(abs_base):
            return JSONResponse(status_code=403, content={"success": False, "error": "Access denied"})

        if not os.path.exists(target_path) or not os.path.isfile(target_path):
            return JSONResponse(status_code=404, content={"success": False, "error": "File not found"})

        try:
            filename = os.path.basename(target_path)
            return FileResponse(target_path, filename=filename)
        except Exception as e:
            return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

    @app.post("/api/fs/complete")
    async def complete_path(request: Request, token: str = Query(...)):
        """
        路径自动补全（支持 Tab 键和 * 通配符）

        Request body: {prefix, cwd, session_dir}
        prefix: 当前输入的词
        cwd: 当前工作目录
        session_dir: 会话根目录（安全边界）
        """
        if token != auth_token:
            return JSONResponse(status_code=403, content={"success": False, "error": "Invalid token"})

        try:
            body = await request.json()
            prefix = body.get("prefix", "")
            cwd = body.get("cwd", base_workplace)
            session_dir = body.get("session_dir", "")
        except Exception:
            return JSONResponse(status_code=400, content={"success": False, "error": "Invalid JSON"})

        # 安全检查
        target_cwd = _resolve_path(cwd, base_workplace)
        allowed = session_dir if session_dir and os.path.isdir(session_dir) else abs_base
        if not target_cwd.startswith(os.path.abspath(allowed)):
            return JSONResponse(status_code=403, content={"success": False, "error": "Access denied"})

        if not prefix:
            return {"success": True, "matches": []}

        try:
            # 判断是路径补全还是命令补全
            is_path = ('/' in prefix or prefix.startswith('.') or prefix.startswith('~')
                       or '*' in prefix or prefix.endswith('/'))

            matches = []

            # 先尝试路径补全（即使 prefix 不含 /，也检查 cwd 下是否有匹配文件）
            path_matches = []
            if prefix.startswith('/'):
                search_dir = os.path.dirname(prefix) or '/'
                basename = os.path.basename(prefix)
            elif prefix.startswith('~'):
                search_dir = target_cwd
                basename = prefix
            else:
                if '/' in prefix:
                    search_dir = os.path.join(target_cwd, os.path.dirname(prefix))
                    basename = os.path.basename(prefix)
                else:
                    search_dir = target_cwd
                    basename = prefix

            search_dir = os.path.abspath(search_dir)
            if search_dir.startswith(os.path.abspath(allowed)):
                if '*' in basename:
                    pattern = os.path.join(search_dir, basename)
                else:
                    pattern = os.path.join(search_dir, basename + '*')

                found = glob.glob(pattern)
                for f in sorted(found):
                    if os.path.basename(f).startswith('.'):
                        continue
                    if not f.startswith(os.path.abspath(allowed)):
                        continue
                    display = os.path.basename(f) + ('/' if os.path.isdir(f) else '')
                    path_matches.append(display)

            if path_matches:
                matches = path_matches
            elif not is_path:
                # 命令补全：在 PATH 中查找
                path_env = os.environ.get('PATH', '/usr/bin:/bin')
                seen = set()
                for pdir in path_env.split(':'):
                    if not os.path.isdir(pdir):
                        continue
                    try:
                        for name in os.listdir(pdir):
                            if name.startswith(prefix) and name not in seen:
                                full = os.path.join(pdir, name)
                                if os.path.isfile(full) and os.access(full, os.X_OK):
                                    seen.add(name)
                                    matches.append(name)
                    except Exception:
                        continue
                matches = sorted(matches)[:50]

            return {"success": True, "matches": matches}
        except Exception as e:
            return JSONResponse(status_code=500, content={"success": False, "error": str(e)})

    @app.post("/api/fs/execute")
    async def execute_command(request: Request, token: str = Query(...)):
        """
        在指定目录执行终端命令（限制在 session_dir 范围内）
        """
        if token != auth_token:
            return JSONResponse(status_code=403, content={"success": False, "error": "Invalid token"})

        try:
            body = await request.json()
            cmd = body.get("cmd", "").strip()
            cwd = body.get("cwd", base_workplace)
            session_dir = body.get("session_dir", "")
        except Exception:
            return JSONResponse(status_code=400, content={"success": False, "error": "Invalid JSON"})

        if not cmd:
            return JSONResponse(status_code=400, content={"success": False, "error": "Empty command"})

        # 安全检查：确定 allowed 目录
        allowed = session_dir if session_dir and os.path.isdir(session_dir) else abs_base
        target_cwd = _resolve_path(cwd, allowed)
        if not target_cwd.startswith(os.path.abspath(allowed)):
            return JSONResponse(status_code=403, content={"success": False, "error": "Access denied"})

        # 黑名单命令
        blacklisted = {
            'sudo', 'su', 'passwd', 'mkfs', 'mkfs.ext2', 'mkfs.ext3', 'mkfs.ext4',
            'mkfs.xfs', 'mkfs.vfat', 'mkfs.ntfs', 'dd', 'fdisk', 'parted', 'gdisk',
            'wget', 'curl', 'nc', 'ncat', 'netcat', 'ssh', 'scp', 'sftp', 'ftp',
            'telnet', 'screen', 'tmux', 'nohup'
        }
        cmd_parts = cmd.split()
        first_cmd = cmd_parts[0] if cmd_parts else ""
        if first_cmd in blacklisted:
            return JSONResponse(status_code=403, content={"success": False, "error": f"Command '{first_cmd}' is not allowed"})

        # 禁止交互式 shell 和反弹 shell 的常见模式
        forbidden_patterns = [
            r'bash\s+-i', r'sh\s+-i',
            r'python\d*\s+-c\s+.*import\s+socket',
            r'python\d*\s+-c\s+.*import\s+subprocess',
            r'python\d*\s+-c\s+.*import\s+os\.system',
            r'eval\s*\(', r'exec\s*\(',
        ]
        for pattern in forbidden_patterns:
            if re.search(pattern, cmd):
                return JSONResponse(status_code=403, content={"success": False, "error": "Forbidden pattern detected"})

        # 对 cd 命令做路径限制
        if first_cmd == 'cd':
            if len(cmd_parts) < 2:
                return {"success": True, "output": "", "cwd": target_cwd}
            target_dir = cmd_parts[1]
            if target_dir.startswith('/'):
                new_path = os.path.abspath(target_dir)
            else:
                new_path = os.path.abspath(os.path.join(target_cwd, target_dir))
            if not new_path.startswith(os.path.abspath(allowed)):
                return JSONResponse(status_code=403, content={"success": False, "error": "Access denied: cannot navigate outside workspace"})
            if not os.path.isdir(new_path):
                return JSONResponse(status_code=400, content={"success": False, "error": f"Not a directory: {target_dir}"})
            return {"success": True, "output": "", "cwd": new_path}

        # 其他命令：检查是否包含允许范围外的绝对路径
        abs_paths = re.findall(r'(?:^|\s)(/[a-zA-Z0-9_./-]+)', cmd)
        for abs_path in abs_paths:
            resolved = os.path.abspath(abs_path)
            if not resolved.startswith(os.path.abspath(allowed)):
                return JSONResponse(status_code=403, content={"success": False, "error": f"Access denied: path '{abs_path}' is outside workspace"})

        try:
            result = subprocess.run(
                ["bash", "-c", cmd],
                cwd=target_cwd,
                capture_output=True,
                text=True,
                timeout=30
            )
            output = result.stdout + (result.stderr if result.stderr else "")
            return {"success": True, "output": output, "returncode": result.returncode}
        except subprocess.TimeoutExpired:
            return JSONResponse(status_code=500, content={"success": False, "error": "Command timeout (30s)"})
        except Exception as e:
            return JSONResponse(status_code=500, content={"success": False, "error": str(e)})
