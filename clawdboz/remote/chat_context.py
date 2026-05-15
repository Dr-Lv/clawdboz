"""
会话上下文管理
管理远程 Bot 的文件访问会话
"""
import time
from dataclasses import dataclass, field
from typing import Optional
from pathlib import Path


@dataclass
class ChatSessionContext:
    """会话上下文"""
    chat_id: str  # 会话 ID (g_xxx for group, w_xxx for single)
    workspace_path: Path  # 工作区路径
    token: str  # 认证 Token
    expires_at: float  # 过期时间戳
    created_at: float = field(default_factory=time.time)
    instance_id: str = ""  # 实例 ID（可选）
    bot_id: str = ""  # Bot ID（可选）

    @property
    def is_expired(self) -> bool:
        """检查是否已过期"""
        return time.time() > self.expires_at

    @property
    def time_remaining(self) -> float:
        """获取剩余时间（秒）"""
        return max(0, self.expires_at - time.time())

    def get_allowed_path(self, relative_path: str = "") -> Path:
        """
        获取允许访问的路径

        Args:
            relative_path: 相对路径（可选）

        Returns:
            绝对路径
        """
        if relative_path:
            # 规范化相对路径并连接到工作区
            normalized = relative_path.lstrip("/")
            return self.workspace_path / normalized
        else:
            return self.workspace_path

    def refresh(self, ttl: int = 3600):
        """
        刷新过期时间

        Args:
            ttl: 新的 TTL（秒）
        """
        self.expires_at = time.time() + ttl

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "chat_id": self.chat_id,
            "workspace_path": str(self.workspace_path),
            "token": self.token,
            "expires_at": self.expires_at,
            "created_at": self.created_at,
            "instance_id": self.instance_id,
            "bot_id": self.bot_id
        }
