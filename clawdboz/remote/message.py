"""
远程消息数据模型
"""
from dataclasses import dataclass, field
from typing import Dict, Any, Optional
import time
import uuid
from enum import Enum


class MessageType(str, Enum):
    """消息类型"""
    BOT_CALL = "bot_call"
    BOT_RESPONSE = "bot_response"
    HEARTBEAT = "heartbeat"
    ERROR = "error"
    FRIEND_REQUEST = "friend_request"
    FRIEND_ACCEPT = "friend_accept"


@dataclass
class RemoteMessage:
    """远程消息"""
    message_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    msg_type: MessageType = MessageType.BOT_CALL
    from_instance: str = ""
    to_instance: str = ""
    bot_id: str = ""
    method: str = "chat"
    params: Dict[str, Any] = field(default_factory=dict)
    reply_to: str = ""
    timestamp: float = field(default_factory=time.time)

    # 文件访问相关字段
    fs_api_url: str = ""  # 文件访问 API 地址
    chat_token: str = ""  # 包含 chat_id 的 Token
    chat_id: str = ""  # 聊天 ID（单聊或群聊）

    # 错误信息
    error: Optional[str] = None
    result: Optional[str] = None

    def to_dict(self) -> dict:
        """转换为字典（用于序列化）"""
        data = {
            "message_id": self.message_id,
            "type": self.msg_type.value,
            "from_instance": self.from_instance,
            "to_instance": self.to_instance,
            "timestamp": self.timestamp
        }

        # 添加类型特定字段
        if self.msg_type == MessageType.BOT_CALL:
            data.update({
                "bot_id": self.bot_id,
                "method": self.method,
                "params": self.params,
                "fs_api_url": self.fs_api_url,
                "chat_token": self.chat_token,
                "chat_id": self.chat_id
            })
        elif self.msg_type == MessageType.BOT_RESPONSE:
            data.update({
                "reply_to": self.reply_to,
                "result": self.result,
                "error": self.error
            })

        return data

    @classmethod
    def from_dict(cls, data: dict) -> "RemoteMessage":
        """从字典创建消息（用于反序列化）"""
        msg_type = MessageType(data.get("type", "bot_call"))

        message = cls(
            message_id=data.get("message_id", str(uuid.uuid4())),
            msg_type=msg_type,
            from_instance=data.get("from_instance", ""),
            to_instance=data.get("to_instance", ""),
            timestamp=data.get("timestamp", time.time())
        )

        # 添加类型特定字段
        if msg_type == MessageType.BOT_CALL:
            message.bot_id = data.get("bot_id", "")
            message.method = data.get("method", "chat")
            message.params = data.get("params", {})
            message.fs_api_url = data.get("fs_api_url", "")
            message.chat_token = data.get("chat_token", "")
            message.chat_id = data.get("chat_id", "")
        elif msg_type == MessageType.BOT_RESPONSE:
            message.reply_to = data.get("reply_to", "")
            message.result = data.get("result")
            message.error = data.get("error")

        return message
