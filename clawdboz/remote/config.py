"""
远程功能配置模块
"""
from dataclasses import dataclass
from typing import Optional, Dict, Any
import json
from pathlib import Path


@dataclass
class RemoteConfig:
    """远程功能配置"""
    enabled: bool = False
    registry_url: str = "http://localhost:9000"
    instance_name: str = ""
    host: str = "0.0.0.0"
    port: int = 8443
    auto_register: bool = True
    heartbeat_interval: int = 30  # 秒
    connection_mode: str = "center"  # 连接模式: 仅支持 "center" (中心转发)，P2P 已移除
    registry_ws_url: str = ""  # 注册服务器 WebSocket URL，如 "ws://localhost:9000/ws/registry"
    token_secret: str = ""  # JWT 签名密钥

    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> "RemoteConfig":
        """从字典加载配置"""
        return cls(
            enabled=data.get("enabled", False),
            registry_url=data.get("registry_url", "http://localhost:9000"),
            instance_name=data.get("instance_name", ""),
            host=data.get("host", "0.0.0.0"),
            port=data.get("port", 8443),
            auto_register=data.get("auto_register", True),
            heartbeat_interval=data.get("heartbeat_interval", 30),
            connection_mode=data.get("connection_mode", "center"),
            registry_ws_url=data.get("registry_ws_url", ""),
            token_secret=data.get("token_secret", "")
        )

    def to_dict(self) -> Dict[str, Any]:
        """转换为字典"""
        return {
            "enabled": self.enabled,
            "registry_url": self.registry_url,
            "instance_name": self.instance_name,
            "host": self.host,
            "port": self.port,
            "auto_register": self.auto_register,
            "heartbeat_interval": self.heartbeat_interval,
            "connection_mode": self.connection_mode,
            "registry_ws_url": self.registry_ws_url,
            "token_secret": self.token_secret
        }

    @classmethod
    def load_from_config_file(cls, config_path: Path) -> "RemoteConfig":
        """从配置文件加载"""
        if not config_path.exists():
            return cls()

        with open(config_path, 'r', encoding='utf-8') as f:
            data = json.load(f)
            remote_config = data.get("remote", {})
            return cls.from_dict(remote_config)

    def save_to_config_file(self, config_path: Path):
        """保存到配置文件"""
        config_path.parent.mkdir(parents=True, exist_ok=True)

        # 读取现有配置
        if config_path.exists():
            with open(config_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
        else:
            data = {}

        # 更新远程配置
        data["remote"] = self.to_dict()

        # 写回文件
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(data, f, indent=2, ensure_ascii=False)
