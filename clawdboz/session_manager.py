#!/usr/bin/env python3
"""
SessionManager - 会话管理器
支持会话级隔离：
- 每个会话独立的 ACP Session
- 每个会话独立的工作目录
- 支持群聊共享目录（groupspace）
"""

import os
import json
import shutil
import threading
from typing import Dict, Optional, List
from pathlib import Path


class Session:
    """会话实例"""
    
    def __init__(self, session_id: str, bot_id: str, session_type: str = "single",
                 base_workplace: str = None, is_group: bool = False):
        """
        初始化会话
        
        Args:
            session_id: 会话ID（前端生成的）
            bot_id: Bot ID
            session_type: 会话类型 single/group
            base_workplace: 基础工作目录路径
            is_group: 是否是群聊
        """
        self.session_id = session_id
        self.bot_id = bot_id
        self.session_type = session_type
        self.is_group = is_group
        self.base_workplace = base_workplace
        
        # ACP 客户端（延迟初始化）
        self.acp_client = None
        
        # 工作目录路径
        self.work_dir = self._get_work_dir()
        
        # 创建目录结构
        self._setup_workspace()
    
    def _get_work_dir(self) -> str:
        """获取工作目录路径"""
        if self.is_group:
            # 群聊：groupspace/g_[session_id]
            return os.path.join(self.base_workplace, "groupspace", f"g_{self.session_id}")
        else:
            # 单聊：workplace_[bot_id]/w_[session_id]
            bot_workspace = os.path.join(self.base_workplace, f"workplace_{self.bot_id}")
            return os.path.join(bot_workspace, f"w_{self.session_id}")
    
    def _setup_workspace(self):
        """设置工作目录结构"""
        # 创建基础目录
        dirs = [
            self.work_dir,
            os.path.join(self.work_dir, "logs"),
            os.path.join(self.work_dir, "user_files"),
            os.path.join(self.work_dir, "user_images"),
            os.path.join(self.work_dir, ".kimi", "skills"),
            os.path.join(self.work_dir, "memory"),  # 会话级记忆
        ]
        
        for d in dirs:
            os.makedirs(d, exist_ok=True)
        
        # 如果是群聊，创建成员软连接（在群成员加入时创建）
        
        # 创建会话级配置
        self._create_session_config()
    
    def _create_session_config(self):
        """创建会话级配置文件"""
        config = {
            "session_id": self.session_id,
            "bot_id": self.bot_id,
            "session_type": self.session_type,
            "is_group": self.is_group,
            "work_dir": self.work_dir,
            "paths": {
                "workplace": self.work_dir,
                "user_images": os.path.join(self.work_dir, "user_images"),
                "user_files": os.path.join(self.work_dir, "user_files"),
                "skills_dir": os.path.join(self.work_dir, ".kimi", "skills"),
                "memory_dir": os.path.join(self.work_dir, "memory"),
                "mcp_config": os.path.join(self.work_dir, ".kimi", "mcp.json"),
            },
            "logs": {
                "debug_log": os.path.join(self.work_dir, "logs", "session_debug.log"),
                "feishu_api_log": os.path.join(self.work_dir, "logs", "feishu_api.log"),
            }
        }
        
        config_path = os.path.join(self.work_dir, "session_config.json")
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
    
    def init_acp_client(self, system_prompt: str = None):
        """初始化 ACP 客户端（每个会话独立的）"""
        if self.acp_client is not None:
            return
        
        # 延迟导入避免循环
        from .acp_client import ACPClient
        
        # 创建会话级 ACP 客户端
        self.acp_client = ACPClient(
            bot_ref=None,  # 不使用 bot 引用，直接管理
            session_work_dir=self.work_dir,
            system_prompt=system_prompt
        )
    
    def chat(self, message: str, on_chunk=None, timeout: int = 180):
        """发送消息（使用会话级 ACP）"""
        if self.acp_client is None:
            self.init_acp_client()
        
        return self.acp_client.chat(message, on_chunk=on_chunk, timeout=timeout)
    
    def link_to_group(self, group_session_id: str, group_work_dir: str):
        """将当前会话链接到群聊目录（创建软连接）"""
        if not self.is_group:
            # 创建软连接到群聊目录
            group_link = os.path.join(self.work_dir, "group_link")
            if os.path.exists(group_link):
                os.remove(group_link)
            os.symlink(group_work_dir, group_link, target_is_directory=True)
            
            # 同时创建一个指向群聊共享 memory 的连接
            group_memory = os.path.join(group_work_dir, "memory")
            if os.path.exists(group_memory):
                shared_memory = os.path.join(self.work_dir, "shared_memory")
                if os.path.exists(shared_memory):
                    os.remove(shared_memory)
                os.symlink(group_memory, shared_memory, target_is_directory=True)


class SessionManager:
    """会话管理器"""
    
    def __init__(self, base_workplace: str = "WORKPLACE"):
        """
        初始化会话管理器
        
        Args:
            base_workplace: 基础工作目录
        """
        self.base_workplace = os.path.abspath(base_workplace)
        self.sessions: Dict[str, Session] = {}  # {session_id: Session}
        self._lock = threading.Lock()
        
        # 确保基础目录存在
        os.makedirs(self.base_workplace, exist_ok=True)
        
        # 确保 groupspace 目录存在
        os.makedirs(os.path.join(self.base_workplace, "groupspace"), exist_ok=True)
    
    def create_session(self, session_id: str, bot_id: str, 
                       session_type: str = "single",
                       is_group: bool = False,
                       member_bot_ids: List[str] = None) -> Session:
        """
        创建新会话
        
        Args:
            session_id: 会话ID
            bot_id: 主 Bot ID（发起者）
            session_type: single/group
            is_group: 是否是群聊
            member_bot_ids: 群聊成员 Bot ID 列表（仅群聊）
            
        Returns:
            Session 实例
        """
        with self._lock:
            if session_id in self.sessions:
                return self.sessions[session_id]
            
            # 创建会话
            session = Session(
                session_id=session_id,
                bot_id=bot_id,
                session_type=session_type,
                base_workplace=self.base_workplace,
                is_group=is_group
            )
            
            self.sessions[session_id] = session
            
            # 如果是群聊，为每个成员创建软连接
            if is_group and member_bot_ids:
                for member_bot_id in member_bot_ids:
                    if member_bot_id != bot_id:
                        self._create_member_group_link(
                            member_bot_id, session_id, session.work_dir
                        )
            
            return session
    
    def _create_member_group_link(self, bot_id: str, group_session_id: str, 
                                   group_work_dir: str):
        """为群成员创建到群聊目录的链接"""
        # 获取成员的 workplace
        bot_workspace = os.path.join(self.base_workplace, f"workplace_{bot_id}")
        member_group_dir = os.path.join(bot_workspace, f"g_{group_session_id}")
        
        # 确保成员的 workplace 存在
        os.makedirs(bot_workspace, exist_ok=True)
        
        # 创建软连接
        if os.path.exists(member_group_dir):
            if os.path.islink(member_group_dir):
                os.remove(member_group_dir)
            else:
                shutil.rmtree(member_group_dir)
        
        os.symlink(group_work_dir, member_group_dir, target_is_directory=True)
        print(f"[SessionManager] 创建群聊软连接: {member_group_dir} -> {group_work_dir}")
    
    def get_session(self, session_id: str) -> Optional[Session]:
        """获取会话"""
        return self.sessions.get(session_id)
    
    def remove_session(self, session_id: str):
        """移除会话"""
        with self._lock:
            if session_id in self.sessions:
                session = self.sessions[session_id]
                # 清理 ACP 客户端
                if session.acp_client:
                    # TODO: 清理 ACP 资源
                    pass
                del self.sessions[session_id]
    
    def get_or_create_session(self, session_id: str, bot_id: str,
                              session_type: str = "single",
                              is_group: bool = False) -> Session:
        """获取或创建会话"""
        session = self.get_session(session_id)
        if session is None:
            session = self.create_session(session_id, bot_id, session_type, is_group)
        return session
    
    def list_sessions(self, bot_id: str = None) -> List[Dict]:
        """列出会话"""
        result = []
        for session_id, session in self.sessions.items():
            if bot_id is None or session.bot_id == bot_id:
                result.append({
                    "session_id": session_id,
                    "bot_id": session.bot_id,
                    "type": "group" if session.is_group else "single",
                    "work_dir": session.work_dir
                })
        return result
