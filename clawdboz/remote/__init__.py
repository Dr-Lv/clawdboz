"""
远程 Bot 功能模块

提供多个 Clawdboz 实例之间的联邦通信能力。
"""

from clawdboz.remote.instance import RemoteInstance, InstanceStatus
from clawdboz.remote.message import RemoteMessage, MessageType

__all__ = [
    "RemoteInstance",
    "InstanceStatus",
    "RemoteMessage",
    "MessageType"
]
