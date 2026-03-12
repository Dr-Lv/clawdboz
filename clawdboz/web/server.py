#!/usr/bin/env python3
"""
WebChatServer - FastAPI WebSocket 聊天服务器 (v3.0)
支持单聊、群聊、流式输出、会话级 workspace 隔离
"""

import asyncio
import json
import os
import secrets
import shutil
import sys
import threading
import time
import uuid
from typing import Dict, Optional, Set, Tuple

def _get_default_workplace():
    """获取默认的 WORKPLACE 路径
    
    默认使用当前工作目录下的 WORKPLACE，与 BotManager 保持一致。
    这样用户在任何目录下运行代码，都会在该目录创建 WORKPLACE。
    """
    return os.path.abspath('WORKPLACE')


class WorkspaceManager:
    """
    Workspace 管理器
    
    实现新的多级 workspace 架构：
    - workplace_[bot_id]/           # Bot 级 workspace（共享资源）
      - logs/
      - user_files/
      - user_images/
      - .kimi/skills/               # Bot 级 skills
      - w_[session_id]/             # 会话级 workspace
        - .kimi/skills/             # 会话级 skills
        - .bots.md                  # 会话级系统提示词
        - .session_memory.md        # 会话级记忆
      - w_[session_id]_group/       # 群组 workspace（带 _group 后缀）
        - g_[session_id]/ -> w_[session_id]/  # 符号链接到其他成员的会话目录
    
    Args:
        base_workplace: 基础 workplace 目录路径
        bot_configs: Bot 配置字典 {bot_id: config}
    """
    
    def __init__(self, base_workplace: str, bot_configs: Dict[str, dict] = None):
        self.base_workplace = os.path.abspath(base_workplace)
        self.bot_configs = bot_configs or {}
        self._ensure_directories()
    
    def _ensure_directories(self):
        """确保基础目录结构存在"""
        os.makedirs(self.base_workplace, exist_ok=True)
    
    def get_bot_workspace(self, bot_id: str) -> str:
        """
        获取或创建 Bot 级 workspace
        
        Returns:
            Bot 级 workspace 路径
        """
        bot_dir = os.path.join(self.base_workplace, f"workplace_{bot_id}")
        
        # 创建基础目录结构
        for subdir in ['logs', 'user_files', 'user_images', '.kimi/skills']:
            os.makedirs(os.path.join(bot_dir, subdir), exist_ok=True)
        
        # 创建 Bot 级 .bots.md（如果不存在）
        bots_md_path = os.path.join(bot_dir, '.bots.md')
        if not os.path.exists(bots_md_path):
            # 从 Bot 配置获取 system_prompt
            system_prompt = self.bot_configs.get(bot_id, {}).get('system_prompt', '')
            if system_prompt:
                with open(bots_md_path, 'w', encoding='utf-8') as f:
                    f.write(f"# Bot 配置\n\n{system_prompt}\n")
        
        return bot_dir
    
    def get_session_workspace(self, bot_id: str, session_id: str, is_group: bool = False) -> str:
        """
        获取或创建会话级 workspace
        
        会话目录只存储会话相关数据，不存储 .bots.md 和 .kimi/skills/
        这些配置统一使用 Bot 级 workplace_[bot_id]/ 目录下的
        
        Args:
            bot_id: Bot ID
            session_id: 会话 ID
            is_group: 是否是群组模式
            
        Returns:
            会话级 workspace 路径
        """
        bot_dir = self.get_bot_workspace(bot_id)
        
        if is_group:
            # 群组会话：使用 g_[session_id]/ 目录
            session_dir = os.path.join(bot_dir, f"g_{session_id}")
        else:
            # 普通会话：使用 w_[session_id]/ 目录
            session_dir = os.path.join(bot_dir, f"w_{session_id}")
        
        # 只创建会话数据目录（不包含 .bots.md 和 .kimi/skills/）
        for subdir in ['logs', 'temp']:
            os.makedirs(os.path.join(session_dir, subdir), exist_ok=True)
        
        # 注意：不再创建 .bots.md 和 .kimi/skills/，使用 Bot 级的
        
        return session_dir
    
    def get_group_workspace(self, session_id: str, member_bot_ids: list = None) -> str:
        """
        获取或创建群组 workspace
        
        群聊时所有 Bot 共享同一个工作目录：groupspace/g_[session_id]/
        群组目录只存储群聊相关数据，不存储 .bots.md 和 .kimi/skills/
        
        Args:
            session_id: 群组会话 ID
            member_bot_ids: 参与群聊的 Bot ID 列表（仅用于日志记录）
            
        Returns:
            群组 workspace 路径
        """
        group_dir = os.path.join(self.base_workplace, "groupspace", f"g_{session_id}")
        
        # 只创建会话数据目录（不包含 .bots.md 和 .kimi/skills/）
        for subdir in ['logs', 'temp', 'user_files', 'user_images']:
            os.makedirs(os.path.join(group_dir, subdir), exist_ok=True)
        
        # 注意：不再创建 .bots.md 和 .kimi/skills/，Bot 使用自己 workplace 下的配置
        
        return group_dir
    
    def get_bot_ids_for_session(self, session_id: str) -> list:
        """
        获取参与某个会话的所有 Bot ID
        
        通过查找 workplace_*/w_{session_id}/ 目录来确定
        
        Returns:
            Bot ID 列表
        """
        bot_ids = []
        for item in os.listdir(self.base_workplace):
            if item.startswith('workplace_'):
                bot_id = item[len('workplace_'):]
                session_dir = os.path.join(self.base_workplace, item, f"w_{session_id}")
                if os.path.exists(session_dir):
                    bot_ids.append(bot_id)
        return bot_ids

# 延迟导入 FastAPI，未安装时给出友好提示
try:
    from fastapi import FastAPI, WebSocket, WebSocketDisconnect, Query, File, UploadFile, Form, Request
    from fastapi.staticfiles import StaticFiles
    from fastapi.responses import FileResponse, JSONResponse
    import uvicorn
except ImportError:
    print("[ERROR] 缺少 web 依赖，请安装: pip install clawdboz[web]")
    print("       或: pip install fastapi uvicorn websockets")
    sys.exit(1)


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
    
    新架构：
    - 每个 frontend session 对应一个独立的 ACP session
    - Workspace 层级：workplace_[bot_id]/w_[session_id]/
    - 群聊共享 workspace：groupspace/g_[session_id]/
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
        
        # 基础 workplace 目录（默认使用项目根目录下的 WORKPLACE）
        if base_workplace is None:
            base_workplace = _get_default_workplace()
        self.base_workplace = os.path.abspath(base_workplace)
        
        # 提取 Bot 配置用于创建 workspace
        bot_configs = {}
        for bot_id, bot in bots.items():
            bot_configs[bot_id] = {
                'system_prompt': getattr(bot, '_system_prompt', ''),
                'app_id': getattr(bot, 'app_id', ''),
                'app_secret': getattr(bot, 'app_secret', ''),
            }
        
        # Workspace 管理器
        self._workspace_mgr = WorkspaceManager(base_workplace, bot_configs)
        
        # 会话级 ACPClient 管理：{(session_id, bot_id): ACPClient}
        # 每个 frontend session + bot 组合对应一个独立的 ACP session
        self._session_acp_clients: Dict[Tuple[str, str], object] = {}
        self._session_acp_lock = asyncio.Lock()
        
        # 并发锁：每个 (session_id, bot_id) 一个锁
        # 这允许同一 Bot 在不同 session 中并发处理，但同一 session 内串行
        self._locks: Dict[Tuple[str, str], asyncio.Lock] = {}
        self._locks_lock = asyncio.Lock()
        
        # 当前活跃的 WebSocket 连接
        self._active_connections: Set[WebSocket] = set()
        
        # MCP 服务器实例
        self._mcp_server = None
        
        # 文件上传目录
        self.upload_dir = os.path.join(os.path.dirname(__file__), "uploads")
        os.makedirs(self.upload_dir, exist_ok=True)
        
        # 群聊历史记录缓存：{chat_id: [{"sender": "user|bot_id", "content": "..."}, ...]}
        self._chat_history: Dict[str, list] = {}
        self._chat_history_lock = asyncio.Lock()
        self._max_history = 30  # 最多保留 30 条记录
        
        # 会话持久化目录
        self._sessions_dir = os.path.join(self.base_workplace, ".sessions")
        os.makedirs(self._sessions_dir, exist_ok=True)
        
        self._setup_routes()
    
    def set_mcp_server(self, mcp_server):
        """设置 MCP 服务器实例"""
        self._mcp_server = mcp_server
        if mcp_server:
            mcp_server.set_web_chat_server(self)
    
    async def broadcast_mcp_message(self, data: dict):
        """
        广播 MCP 消息到所有连接的客户端
        用于定时任务等场景发送消息到 Web Chat
        
        Args:
            data: 消息数据，格式为 {"type": "mcp_message|mcp_file|mcp_notify", ...}
        """
        if not self._active_connections:
            print(f"[WebServer] MCP 消息无客户端接收: {data.get('type')}")
            return
            
        disconnected = set()
        for ws in self._active_connections:
            try:
                await ws.send_json(data)
            except Exception as e:
                print(f"[WebServer] 发送 MCP 消息失败: {e}")
                disconnected.add(ws)
        
        # 清理断开连接
        for ws in disconnected:
            self._active_connections.discard(ws)
    
    async def _get_or_create_session_acp_client(self, session_id: str, bot_id: str, 
                                                  is_group: bool = False) -> Optional[object]:
        """
        获取或创建会话级的 ACPClient
        
        这是实现会话级隔离的核心方法。每个 (session_id, bot_id) 组合
        对应一个独立的 ACP session，确保上下文不会在不同 session 之间混合。
        
        群聊模式下，所有 Bot 共享同一个 workspace：groupspace/g_[session_id]/
        
        Args:
            session_id: 前端会话 ID
            bot_id: Bot ID
            is_group: 是否是群组模式
            
        Returns:
            ACPClient 实例，或 None（如果创建失败）
        """
        key = (session_id, bot_id)
        
        async with self._session_acp_lock:
            # 检查是否已存在
            if key in self._session_acp_clients:
                client = self._session_acp_clients[key]
                # 检查连接是否还活跃
                if hasattr(client, 'process') and client.process and client.process.poll() is None:
                    return client
                else:
                    # 客户端已断开，移除
                    print(f"[WebServer] ACPClient {key} 已断开，重新创建")
                    del self._session_acp_clients[key]
            
            # 创建新的 ACPClient
            try:
                from ..acp_client import ACPClient
                
                # 确定工作目录
                if is_group:
                    # 群聊模式：所有 Bot 共享同一个群组 workspace
                    session_work_dir = self._workspace_mgr.get_group_workspace(session_id)
                    print(f"[WebServer] 群聊模式，使用共享 workspace: {session_work_dir}")
                else:
                    # 单聊模式：每个 Bot 有自己的会话 workspace
                    session_work_dir = self._workspace_mgr.get_session_workspace(
                        bot_id, session_id, is_group=False
                    )
                
                # 获取 Bot workplace（用于加载 .bots.md 和 skills）
                bot_work_dir = self._workspace_mgr.get_bot_workspace(bot_id)
                
                # 获取 Bot 实例
                bot = self.bots.get(bot_id)
                
                # 获取 Bot 的 system_prompt
                system_prompt = None
                if bot:
                    system_prompt = getattr(bot, '_system_prompt', None)
                
                print(f"[WebServer] 创建 ACPClient: session={session_id}, bot={bot_id}")
                print(f"[WebServer]   工作目录: {session_work_dir}")
                print(f"[WebServer]   配置目录: {bot_work_dir}")
                
                # 创建 ACPClient，传入：
                # - session_work_dir: 当前会话的工作目录（用于读写文件）
                # - bot_work_dir: Bot 配置目录（用于加载 .bots.md 和 skills）
                client = ACPClient(
                    bot_ref=bot,
                    session_work_dir=session_work_dir,
                    bot_work_dir=bot_work_dir,
                    system_prompt=system_prompt
                )
                
                self._session_acp_clients[key] = client
                print(f"[WebServer] ACPClient 创建成功: session_id={client.session_id}")
                return client
                
            except Exception as e:
                print(f"[WebServer] 创建会话级 ACPClient 失败: {e}")
                import traceback
                traceback.print_exc()
                return None
    
    async def _cleanup_session_acp_client(self, session_id: str, bot_id: str = None):
        """
        清理会话级的 ACPClient
        
        Args:
            session_id: 前端会话 ID
            bot_id: 如果指定，只清理该 Bot 的客户端；否则清理该 session 的所有客户端
        """
        async with self._session_acp_lock:
            keys_to_remove = []
            for key in self._session_acp_clients:
                if key[0] == session_id:
                    if bot_id is None or key[1] == bot_id:
                        keys_to_remove.append(key)
            
            for key in keys_to_remove:
                client = self._session_acp_clients[key]
                try:
                    # 关闭 ACP 连接
                    if hasattr(client, 'close'):
                        client.close()
                    elif hasattr(client, 'process') and client.process:
                        client.process.terminate()
                except Exception as e:
                    print(f"[WebServer] 关闭 ACPClient {key} 失败: {e}")
                del self._session_acp_clients[key]
                print(f"[WebServer] 已清理 ACPClient: {key}")
    
    async def _get_lock(self, session_id: str, bot_id: str) -> asyncio.Lock:
        """
        获取 (session_id, bot_id) 组合的并发锁
        
        这允许同一 Bot 在不同 session 中并发处理，但同一 session 内串行。
        
        Args:
            session_id: 前端会话 ID
            bot_id: Bot ID
            
        Returns:
            asyncio.Lock 实例
        """
        key = (session_id, bot_id)
        
        async with self._locks_lock:
            if key not in self._locks:
                self._locks[key] = asyncio.Lock()
            return self._locks[key]
        
    def _setup_routes(self):
        """设置路由"""
        # 获取静态文件目录
        static_dir = os.path.join(os.path.dirname(__file__), "static")
        if os.path.exists(static_dir):
            self.app.mount("/static", StaticFiles(directory=static_dir), name="static")
        
        # 上传文件目录（提供下载）
        self.app.mount("/uploads", StaticFiles(directory=self.upload_dir), name="uploads")
        
        @self.app.post("/api/upload")
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
            if token != self.auth_token:
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "error": "Invalid token"}
                )
            
            try:
                # 生成唯一文件名
                file_ext = os.path.splitext(file.filename)[1].lower()
                file_id = f"{uuid.uuid4().hex}{file_ext}"
                file_path = os.path.join(self.upload_dir, file_id)
                
                # 保存文件
                content = await file.read()
                with open(file_path, "wb") as f:
                    f.write(content)
                
                file_size = len(content)
                
                # 判断文件类型
                image_exts = {'.jpg', '.jpeg', '.png', '.gif', '.webp', '.bmp', '.svg'}
                is_image = file_ext in image_exts
                
                # 将文件复制到 ACP 工作目录，供 Bot 读取
                # 注意：ACP 使用的是项目目录下的 WORKPLACE，而不是临时目录
                try:
                    workplace_path = _get_workplace_path()
                    if os.path.exists(workplace_path):
                        import shutil
                        bot_file_path = os.path.join(workplace_path, file.filename)
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
        
        @self.app.get("/api/file/{file_id}")
        async def download_file(file_id: str, token: str = Query(...)):
            """
            文件下载接口
            
            Args:
                file_id: 文件ID
                token: 访问令牌
            """
            if token != self.auth_token:
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "error": "Invalid token"}
                )
            
            file_path = os.path.join(self.upload_dir, file_id)
            if not os.path.exists(file_path):
                return JSONResponse(
                    status_code=404,
                    content={"success": False, "error": "File not found"}
                )
            
            return FileResponse(file_path)
        
        @self.app.post("/api/mcp/broadcast")
        async def mcp_broadcast(data: dict):
            """
            MCP 消息广播接口
            供 MCP 服务器调用，将消息/文件/通知发送到前端
            
            Args:
                data: 消息数据，格式为 {"type": "mcp_message|mcp_file|mcp_notify", ...}
            """
            token = data.pop('_token', '')
            if token != self.auth_token:
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "error": "Invalid token"}
                )
            
            try:
                await self.broadcast_mcp_message(data)
                return {"success": True}
            except Exception as e:
                return JSONResponse(
                    status_code=500,
                    content={"success": False, "error": str(e)}
                )
        
        @self.app.get("/")
        async def root():
            """根路径，返回基本信息"""
            return {
                "name": "Clawdboz Web Chat",
                "version": "3.0.0",
                "bots": list(self.bots.keys()),
                "websocket": f"ws://localhost:{self.port}/ws/chat?token=<your_token>"
            }
        
        @self.app.get("/api/bots")
        async def list_bots():
            """获取 Bot 列表"""
            return {
                "bots": [
                    {
                        "id": bid,
                        "name": getattr(bot, '_bot_id', bid),
                        "work_dir": getattr(bot, '_work_dir', 'unknown')
                    }
                    for bid, bot in self.bots.items()
                ]
            }
        
        @self.app.get("/api/sessions")
        async def list_sessions(token: str = Query(...)):
            """
            获取所有保存的会话列表（用于前端恢复会话）
            
            Returns:
                {
                    "sessions": [
                        {
                            "id": "session-xxx",
                            "last_message": "...",
                            "updated_at": 1234567890
                        }
                    ]
                }
            """
            if token != self.auth_token:
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "error": "Invalid token"}
                )
            
            try:
                sessions = []
                for filename in os.listdir(self._sessions_dir):
                    if filename.endswith('.json'):
                        chat_id = filename[:-5]  # 移除 .json
                        file_path = os.path.join(self._sessions_dir, filename)
                        
                        # 读取文件获取最后更新时间
                        try:
                            with open(file_path, 'r', encoding='utf-8') as f:
                                history = json.load(f)
                            
                            # 返回所有会话，包括空会话
                            if history:
                                last_msg = history[-1]
                                sessions.append({
                                    "id": chat_id,
                                    "last_message": last_msg.get("content", "")[:50],
                                    "updated_at": last_msg.get("time", 0),
                                    "message_count": len(history)
                                })
                            else:
                                # 空会话，使用文件修改时间
                                stat = os.stat(file_path)
                                sessions.append({
                                    "id": chat_id,
                                    "last_message": "",
                                    "updated_at": stat.st_mtime,
                                    "message_count": 0
                                })
                        except Exception as e:
                            print(f"[WebServer] 读取会话文件失败: {filename}, {e}")
                
                # 按时间倒序排列
                sessions.sort(key=lambda x: x["updated_at"], reverse=True)
                
                return {"sessions": sessions}
            except Exception as e:
                return JSONResponse(
                    status_code=500,
                    content={"success": False, "error": str(e)}
                )
        
        @self.app.get("/api/sessions/{chat_id}")
        async def get_session(chat_id: str, token: str = Query(...)):
            """
            获取指定会话的完整聊天记录
            
            Args:
                chat_id: 会话 ID
                
            Returns:
                {
                    "id": "session-xxx",
                    "messages": [
                        {"sender": "user", "content": "...", "time": 1234567890}
                    ]
                }
            """
            if token != self.auth_token:
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "error": "Invalid token"}
                )
            
            try:
                history = await self._load_session_history(chat_id)
                return {
                    "id": chat_id,
                    "messages": history
                }
            except Exception as e:
                return JSONResponse(
                    status_code=500,
                    content={"success": False, "error": str(e)}
                )
        
        @self.app.delete("/api/sessions/{chat_id}")
        async def delete_session(chat_id: str, token: str = Query(...)):
            """删除指定会话的历史记录和对应的工作目录"""
            if token != self.auth_token:
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "error": "Invalid token"}
                )
            
            try:
                # 1. 删除会话记录文件
                file_path = self._get_session_file_path(chat_id)
                if os.path.exists(file_path):
                    os.remove(file_path)
                
                # 2. 从内存中移除
                async with self._chat_history_lock:
                    if chat_id in self._chat_history:
                        del self._chat_history[chat_id]
                
                # 3. 删除对应的工作目录
                # 单聊目录: workplace_[bot_id]/w_[chat_id]/
                # 群聊目录: groupspace/g_[chat_id]/
                deleted_dirs = []
                
                for bot_id in self.bots.keys():
                    # 尝试删除单聊 session 目录
                    session_dir = os.path.join(
                        self.base_workplace, 
                        f"workplace_{bot_id}", 
                        f"w_{chat_id}"
                    )
                    if os.path.exists(session_dir):
                        import shutil
                        shutil.rmtree(session_dir)
                        deleted_dirs.append(session_dir)
                    
                    # 尝试删除群聊 session 目录 (g_ 前缀)
                    group_session_dir = os.path.join(
                        self.base_workplace,
                        f"workplace_{bot_id}",
                        f"g_{chat_id}"
                    )
                    if os.path.exists(group_session_dir):
                        import shutil
                        shutil.rmtree(group_session_dir)
                        deleted_dirs.append(group_session_dir)
                
                # 删除群聊共享目录
                group_dir = os.path.join(self.base_workplace, "groupspace", f"g_{chat_id}")
                if os.path.exists(group_dir):
                    import shutil
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
        
        @self.app.post("/api/sessions")
        async def create_session(request: Request, token: str = Query(...)):
            """创建或更新会话记录（用于前端新建会话）"""
            if token != self.auth_token:
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "error": "Invalid token"}
                )
            
            try:
                data = await request.json()
                chat_id = data.get("id")
                bot_ids = data.get("bot_ids", [])
                
                if not chat_id:
                    return JSONResponse(
                        status_code=400,
                        content={"success": False, "error": "Missing session id"}
                    )
                
                # 创建空的会话历史记录
                async with self._chat_history_lock:
                    if chat_id not in self._chat_history:
                        self._chat_history[chat_id] = []
                
                # 保存到文件（创建空记录）
                await self._save_session_history(chat_id)
                
                print(f"[WebServer] 创建会话记录: {chat_id}, bots: {bot_ids}")
                return {"success": True, "id": chat_id}
            except Exception as e:
                return JSONResponse(
                    status_code=500,
                    content={"success": False, "error": str(e)}
                )
        
        @self.app.websocket("/ws/chat")
        async def chat_ws(websocket: WebSocket, token: str = Query(...)):
            """
            WebSocket 聊天接口
            
            消息协议:
            - 客户端发送: {"mode": "single|group", "bots": ["id1"], "message": "..."}
            - 服务端返回: {"type": "start|chunk|done|error", "bot_id": "...", ...}
            """
            # Token 鉴权
            if token != self.auth_token:
                await websocket.close(code=4001, reason="Invalid token")
                return
            
            await websocket.accept()
            self._active_connections.add(websocket)
            
            try:
                while True:
                    # 接收客户端消息
                    data = await websocket.receive_json()
                    await self._handle_message(websocket, data)
            except WebSocketDisconnect:
                pass
            except Exception as e:
                print(f"[WebServer] WebSocket 错误: {e}")
            finally:
                self._active_connections.discard(websocket)
    
    async def _handle_message(self, ws: WebSocket, data: dict):
        """
        处理聊天消息
        
        Args:
            ws: WebSocket 连接
            data: 客户端消息 {"mode": "single|group", "bots": ["id"], "message": "...", "chat_id": "..."}
        """
        mode = data.get("mode", "single")
        bot_ids = data.get("bots", [])
        message = data.get("message", "")
        chat_id = data.get("chat_id") or "default"  # 处理 null 或空字符串
        
        if not bot_ids or not message:
            await ws.send_json({
                "type": "error",
                "error": "缺少必要参数: bots 或 message"
            })
            return
        
        # 验证所有 Bot 存在
        for bot_id in bot_ids:
            if bot_id not in self.bots:
                await ws.send_json({
                    "type": "error",
                    "error": f"Bot '{bot_id}' 不存在"
                })
                return
        
        # 单聊或群聊
        if mode == "single":
            await self._single_chat(ws, bot_ids[0], message, chat_id)
        else:
            await self._group_chat(ws, bot_ids, message, chat_id)
    
    async def _get_chat_history(self, chat_id: str) -> list:
        """获取聊天历史记录"""
        async with self._chat_history_lock:
            return self._chat_history.get(chat_id, []).copy()
    
    async def _add_to_history(self, chat_id: str, sender: str, content: str):
        """添加记录到聊天历史并持久化到文件"""
        async with self._chat_history_lock:
            if chat_id not in self._chat_history:
                self._chat_history[chat_id] = []
            self._chat_history[chat_id].append({
                "sender": sender,
                "content": content,
                "time": time.time()
            })
            # 限制历史记录数量
            if len(self._chat_history[chat_id]) > self._max_history:
                self._chat_history[chat_id] = self._chat_history[chat_id][-self._max_history:]
            
            # 持久化到文件
            await self._save_session_history(chat_id)
    
    def _get_session_file_path(self, chat_id: str) -> str:
        """获取会话历史文件的保存路径"""
        # 使用 chat_id 作为文件名（进行安全编码）
        safe_name = chat_id.replace('/', '_').replace('\\', '_')
        return os.path.join(self._sessions_dir, f"{safe_name}.json")
    
    async def _save_session_history(self, chat_id: str):
        """将会话历史保存到文件"""
        try:
            file_path = self._get_session_file_path(chat_id)
            history = self._chat_history.get(chat_id, [])
            
            # 异步写入文件
            loop = asyncio.get_event_loop()
            await loop.run_in_executor(None, self._write_json_file, file_path, history)
        except Exception as e:
            print(f"[WebServer] 保存会话历史失败: {e}")
    
    def _write_json_file(self, file_path: str, data: list):
        """同步写入 JSON 文件（在线程池中执行）"""
        with open(file_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, ensure_ascii=False, indent=2)
    
    async def _load_session_history(self, chat_id: str) -> list:
        """从文件加载会话历史"""
        try:
            file_path = self._get_session_file_path(chat_id)
            if not os.path.exists(file_path):
                return []
            
            # 异步读取文件
            loop = asyncio.get_event_loop()
            return await loop.run_in_executor(None, self._read_json_file, file_path)
        except Exception as e:
            print(f"[WebServer] 加载会话历史失败: {e}")
            return []
    
    def _read_json_file(self, file_path: str) -> list:
        """同步读取 JSON 文件（在线程池中执行）"""
        with open(file_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    
    async def _load_all_sessions(self) -> Dict[str, list]:
        """加载所有保存的会话"""
        sessions = {}
        try:
            if not os.path.exists(self._sessions_dir):
                return sessions
            
            for filename in os.listdir(self._sessions_dir):
                if filename.endswith('.json'):
                    chat_id = filename[:-5]  # 移除 .json 后缀
                    history = await self._load_session_history(chat_id)
                    if history:
                        sessions[chat_id] = history
        except Exception as e:
            print(f"[WebServer] 加载所有会话失败: {e}")
        
        return sessions
    
    async def _single_chat(self, ws: WebSocket, bot_id: str, message: str, chat_id: str = "default", is_group: bool = False):
        """
        单聊：一个 Bot 回复（v3.0 - 支持会话级隔离）
        
        Args:
            ws: WebSocket 连接
            bot_id: Bot ID
            message: 用户消息
            chat_id: 聊天会话 ID（同时也是 session_id）
            is_group: 是否是群聊模式（用于控制是否保存历史记录）
        """
        print(f"[WebServer] _single_chat 开始: bot_id={bot_id}, chat_id={chat_id}, is_group={is_group}, message={message[:50]}")
        bot = self.bots[bot_id]
        
        # 获取会话级的锁（允许同一 Bot 在不同 session 中并发）
        lock = await self._get_lock(chat_id, bot_id)
        
        # 生成消息唯一标识
        msg_id = str(uuid.uuid4())
        seq = 0
        
        # 发送开始标记
        print(f"[WebServer] 发送 start 消息")
        await ws.send_json({
            "type": "start",
            "msg_id": msg_id,
            "seq": seq,
            "bot_id": bot_id,
            "bot_name": getattr(bot, '_bot_id', bot_id)
        })
        
        async def send_chunk(text: str, is_thinking: bool = False):
            """发送流式内容"""
            nonlocal seq
            seq += 1
            try:
                await ws.send_json({
                    "type": "chunk",
                    "msg_id": msg_id,
                    "seq": seq,
                    "bot_id": bot_id,
                    "content": text,
                    "is_thinking": is_thinking
                })
            except Exception as e:
                # 客户端断开连接，不再发送
                print(f"[WebServer] 发送 chunk 失败（客户端可能已断开）: {e}")
                raise  # 重新抛出以便上层处理
        
        # 加锁执行，防止同一 session 内的并发冲突
        print(f"[WebServer] 获取锁 (session={chat_id}, bot={bot_id})...")
        async with lock:
            print(f"[WebServer] 锁已获取，调用 _call_bot_chat")
            try:
                # 先保存用户消息到历史记录（确保即使生成过程中切换会话也能看到用户消息）
                if not is_group:
                    await self._add_to_history(chat_id, "user", message)
                
                # 获取历史记录（只要不是默认chat_id就获取）
                history = await self._get_chat_history(chat_id) if chat_id and chat_id != "default" else []
                print(f"[WebServer] 获取到历史记录: {len(history)} 条")
                
                # 调用 chat，传入 session_id 实现会话级隔离
                result = await self._call_bot_chat(
                    bot, message, send_chunk, 
                    history=history, bot_id=bot_id,
                    session_id=chat_id, is_group=is_group
                )
                print(f"[WebServer] _call_bot_chat 返回: {result[:100] if result else 'None'}...")
                
                # 保存 bot 回复到历史记录
                if not is_group:
                    await self._add_to_history(chat_id, bot_id, result)
                
                # 发送完成标记
                seq += 1
                print(f"[WebServer] 发送 done 消息")
                try:
                    await ws.send_json({
                        "type": "done",
                        "msg_id": msg_id,
                        "seq": seq,
                        "bot_id": bot_id,
                        "final": result
                    })
                except Exception as e:
                    print(f"[WebServer] 发送 done 失败（客户端可能已断开）: {e}")
                
                return result
            except Exception as e:
                print(f"[WebServer] _call_bot_chat 异常: {e}")
                import traceback
                traceback.print_exc()
                seq += 1
                try:
                    await ws.send_json({
                        "type": "error",
                        "msg_id": msg_id,
                        "seq": seq,
                        "bot_id": bot_id,
                        "error": str(e)
                    })
                except Exception as e2:
                    print(f"[WebServer] 发送 error 失败（客户端可能已断开）: {e2}")
                return None
    
    async def _group_chat(self, ws: WebSocket, bot_ids: list, message: str, chat_id: str = "default"):
        """
        群聊：多个 Bot 同时回复（共享上下文）v3.0
        
        在群聊模式下：
        1. 所有 Bot 共享同一个群组 workspace：groupspace/g_[session_id]/
        2. 不再创建符号链接，所有 Bot 直接使用该目录
        
        Args:
            ws: WebSocket 连接
            bot_ids: Bot ID 列表
            message: 用户消息
            chat_id: 聊天会话 ID
        """
        print(f"[WebServer] _group_chat 开始: chat_id={chat_id}, bots={bot_ids}, message={message[:50]}")
        
        # 先保存用户消息到历史
        await self._add_to_history(chat_id, "user", message)
        
        # 创建群组 workspace（所有 Bot 共享）
        try:
            group_dir = self._workspace_mgr.get_group_workspace(chat_id, member_bot_ids=bot_ids)
            print(f"[WebServer] 群组 workspace: {group_dir}")
        except Exception as e:
            print(f"[WebServer] 创建群组 workspace 失败: {e}")
        
        # 并发启动所有 Bot（都带上群聊标记，避免重复保存历史）
        # 群聊时所有 Bot 共享同一个 workspace
        tasks = [
            self._single_chat(ws, bot_id, message, chat_id, is_group=True)
            for bot_id in bot_ids
        ]
        results = await asyncio.gather(*tasks)
        
        # 所有 Bot 回复完成后，保存所有回复到历史
        for bot_id, result in zip(bot_ids, results):
            if result:
                await self._add_to_history(chat_id, bot_id, result)
    
    def _build_context_prompt(self, history: list, current_message: str, bot_id: str) -> str:
        """
        构建带上下文的 prompt
        
        Args:
            history: 历史记录列表
            current_message: 当前用户消息
            bot_id: 当前 Bot ID
            
        Returns:
            构建好的 prompt
        """
        if not history:
            return current_message
        
        context_parts = ["以下是最近聊天记录上下文：\n"]
        for msg in history[-self._max_history:]:
            sender = msg.get('sender', 'unknown')
            content = msg.get('content', '')
            
            if sender == "user":
                context_parts.append(f"用户: {content}")
            elif sender == bot_id:
                context_parts.append(f"你(Bot): {content}")
            else:
                context_parts.append(f"其他Bot({sender}): {content}")
        
        context_parts.append(f"\n用户当前消息：{current_message}\n\n请基于上下文回复用户的消息。")
        return "\n".join(context_parts)
    
    async def _call_bot_chat(self, bot: object, message: str, send_chunk, 
                              history: list = None, bot_id: str = None,
                              session_id: str = "default", is_group: bool = False) -> str:
        """
        调用 Bot 的聊天接口（v3.0 - 支持会话级隔离）
        
        使用 session 级的 ACPClient，确保不同会话之间的上下文不会混合。
        
        Args:
            bot: Bot 实例（LarkBot 或 simple_bot.Bot）
            message: 用户消息
            send_chunk: 异步回调函数，用于发送流式内容
            history: 历史记录列表（群聊模式下）
            bot_id: Bot ID
            session_id: 前端会话 ID（用于创建 session 级的 ACP session）
            is_group: 是否是群组模式
            
        Returns:
            完整的回复内容
        """
        loop = asyncio.get_event_loop()
        collected_chunks = []
        
        def on_chunk(text: str):
            """同步回调：收集内容并通过异步方式发送"""
            collected_chunks.append(text)
            # 使用 run_coroutine_threadsafe 从同步回调调用异步函数
            asyncio.run_coroutine_threadsafe(send_chunk(text), loop)
        
        # 获取实际的 Bot 实例
        actual_bot = bot
        if hasattr(bot, '_bot'):  # simple_bot.Bot 包装类
            actual_bot = bot._bot
        
        # 构建带上下文的 prompt
        if history:
            final_prompt = self._build_context_prompt(history, message, bot_id)
            print(f"[WebServer] 使用上下文 prompt，历史记录数: {len(history)}")
        else:
            final_prompt = message
        
        # 在线程池中执行同步的 chat 方法
        def do_chat():
            """在线程中执行 Bot 调用"""
            # 确定工作目录
            if is_group:
                # 群聊模式：使用共享的群组 workspace
                session_work_dir = self._workspace_mgr.get_group_workspace(session_id)
            else:
                # 单聊模式：使用 Bot 自己的会话 workspace
                session_work_dir = self._workspace_mgr.get_session_workspace(
                    bot_id, session_id, is_group=False
                )
            
            original_dir = os.getcwd()
            os.chdir(session_work_dir)
            
            try:
                # 获取会话级的 ACPClient
                # 注意：这里使用 run_coroutine_threadsafe 从同步线程调用异步方法
                future = asyncio.run_coroutine_threadsafe(
                    self._get_or_create_session_acp_client(session_id, bot_id, is_group=is_group),
                    loop
                )
                acp_client = future.result(timeout=10)  # 最多等待10秒
                
                if acp_client is None:
                    return "[无法创建 ACP 会话]"
                
                print(f"[WebServer] 使用会话级 ACPClient: session={session_id}, bot={bot_id}")
                
                # 调用 ACP 客户端的 chat 方法
                result = acp_client.chat(final_prompt, on_chunk=on_chunk, timeout=180)
                return result
                
            except Exception as e:
                print(f"[WebServer] chat 调用失败: {e}")
                import traceback
                traceback.print_exc()
                return f"[调用失败: {e}]"
            finally:
                os.chdir(original_dir)
        
        # 执行并返回结果
        result = await loop.run_in_executor(None, do_chat)
        return result if result else "[无回复]"
    
    def run(self, blocking: bool = False):
        """
        启动服务器
        
        Args:
            blocking: 是否阻塞运行（默认后台线程）
        """
        config = uvicorn.Config(
            self.app,
            host="0.0.0.0",
            port=self.port,
            log_level="warning",
            access_log=False
        )
        server = uvicorn.Server(config)
        
        if blocking:
            print(f"\n🌐 Web Chat 已启动")
            print(f"   URL: http://localhost:{self.port}/static/index.html?token={self.auth_token}")
            print(f"   Token: {self.auth_token}\n")
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
