"""
远程实例信息数据模型
"""
from dataclasses import dataclass, field
from typing import List, Optional
import time
from enum import Enum


class InstanceStatus(str, Enum):
    """实例状态"""
    ONLINE = "online"
    OFFLINE = "offline"
    PENDING = "pending"


@dataclass
class RemoteInstance:
    """远程实例信息"""
    instance_id: str
    name: str
    host: str
    port: int
    token: str
    status: InstanceStatus = InstanceStatus.OFFLINE
    is_friend: bool = False
    last_seen: float = field(default_factory=time.time)
    published_bots: List[str] = field(default_factory=list)
    published_bots_info: List[dict] = field(default_factory=list)
    friend_bots: List[str] = field(default_factory=list)  # NEW: Bot 级别好友列表
    created_at: float = field(default_factory=time.time)
    fs_api_enabled: bool = True  # 是否支持文件访问 API

    @property
    def ws_url(self) -> str:
        """获取 WebSocket 连接 URL"""
        return f"ws://{self.host}:{self.port}/ws/remote"

    @property
    def http_url(self) -> str:
        """获取 HTTP API URL"""
        protocol = "https" if self.port == 443 else "http"
        return f"{protocol}://{self.host}:{self.port}"

    def is_online(self, timeout: int = 60) -> bool:
        """检查实例是否在线"""
        return (time.time() - self.last_seen) < timeout

    def to_dict(self) -> dict:
        """转换为字典（用于 API 响应）"""
        return {
            "instance_id": self.instance_id,
            "name": self.name,
            "status": self.status.value,
            "is_friend": self.is_friend,
            "published_bots": self.published_bots,
            "published_bots_info": self.published_bots_info,
            "friend_bots": self.friend_bots,
            "fs_api_enabled": self.fs_api_enabled,
            "last_seen": self.last_seen,
            "created_at": self.created_at
        }

    @classmethod
    def from_dict(cls, data: dict) -> "RemoteInstance":
        """从字典创建实例（用于 API 请求）"""
        instance_id = data["instance_id"]

        # 尝试从 instance_id 解析端口（格式：hostname-port）
        port = 8443  # 默认端口
        if "-" in instance_id:
            parts = instance_id.rsplit("-", 1)
            if parts[-1].isdigit():
                try:
                    port = int(parts[-1])
                except ValueError:
                    pass

        # host 和 token 可能为空（从注册服务器获取时）
        host = data.get("host", "")
        token = data.get("token", "")

        return cls(
            instance_id=instance_id,
            name=data["name"],
            host=host,
            port=port,
            token=token,
            status=InstanceStatus(data.get("status", "offline")),
            is_friend=data.get("is_friend", False),
            last_seen=data.get("last_seen", time.time()),
            published_bots=data.get("published_bots", []),
            published_bots_info=data.get("published_bots_info", []),
            friend_bots=data.get("friend_bots", []),
            created_at=data.get("created_at", time.time()),
            fs_api_enabled=data.get("fs_api_enabled", True)
        )
