"""
好友管理模块 - Bot 级别好友关系
"""
import asyncio
import sys
from typing import List, Optional, Dict, Set
from enum import Enum


class FriendStatus(str, Enum):
    """好友状态"""
    PENDING = "pending"
    ACCEPTED = "accepted"
    REJECTED = "rejected"


class FriendRequest:
    """好友请求"""

    def __init__(
        self,
        request_id: str,
        from_instance: str,
        to_instance: str,
        from_token: str,
        message: str = ""
    ):
        self.request_id = request_id
        self.from_instance = from_instance
        self.to_instance = to_instance
        self.from_token = from_token
        self.message = message
        self.status = FriendStatus.PENDING
        self.created_at = 0  # 设置为当前时间

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "request_id": self.request_id,
            "from_instance": self.from_instance,
            "to_instance": self.to_instance,
            "from_token": self.from_token,
            "message": self.message,
            "status": self.status.value,
            "created_at": self.created_at
        }


class FriendManager:
    """好友管理器 - Bot 级别"""

    def __init__(self, registry_client):
        """
        初始化好友管理器

        Args:
            registry_client: 注册服务器客户端
        """
        self.registry_client = registry_client
        # instance_id -> {bot_id1, bot_id2, ...}
        self._friends: Dict[str, Set[str]] = {}
        self._pending_requests: Dict[str, FriendRequest] = {}

    async def send_friend_request(
        self,
        to_instance: str,
        message: str = "",
        to_bot_id: str = "",
        from_bot_id: str = ""
    ) -> FriendRequest:
        """
        发送好友请求（Bot 级别）

        Args:
            to_instance: 目标实例 ID
            message: 附加消息
            to_bot_id: 目标 bot ID
            from_bot_id: 发起方 bot ID

        Returns:
            FriendRequest 对象
        """
        import uuid

        request_id = str(uuid.uuid4())

        payload = {
            "request_id": request_id,
            "from_instance": self.registry_client.instance_info["instance_id"],
            "to_instance": to_instance,
            "from_bot_id": from_bot_id,
            "to_bot_id": to_bot_id,
            "from_token": self.registry_client.instance_info["token"],
            "message": message
        }

        try:
            result = await self.registry_client.send_friend_request(
                to_instance=to_instance,
                message=message,
                request_id=request_id,
                to_bot_id=to_bot_id,
                from_bot_id=from_bot_id
            )

            if result.get("success"):
                friend_req = FriendRequest(
                    request_id=request_id,
                    from_instance=payload["from_instance"],
                    to_instance=to_instance,
                    from_token=payload["from_token"],
                    message=message
                )
                self._pending_requests[request_id] = friend_req
                return friend_req
            else:
                raise Exception(f"发送好友请求失败: {result}")

        except Exception as e:
            print(f"[FriendManager] 发送好友请求异常: {e}")
            raise

    async def accept_friend_request(
        self,
        request_id: str,
        accept: bool = True
    ) -> bool:
        """
        确认/拒绝好友请求

        Args:
            request_id: 请求 ID
            accept: 是否接受

        Returns:
            是否成功
        """
        try:
            msg = f"[FriendManager] accept_friend_request called: request_id={request_id}, accept={accept}"
            print(msg, flush=True)
            sys.stdout.flush()

            # 首先加载待处理请求（确保_pending_requests已填充）
            if not self._pending_requests:
                msg = f"[FriendManager] Loading pending requests first..."
                print(msg, flush=True)
                sys.stdout.flush()
                await self.get_pending_requests()

            msg = f"[FriendManager] Current _pending_requests: {list(self._pending_requests.keys())}"
            print(msg, flush=True)
            sys.stdout.flush()

            # 如果接受，先获取请求信息以便后续添加好友
            from_instance = None
            from_bot_id = ""
            to_bot_id = ""
            if accept and request_id in self._pending_requests:
                req = self._pending_requests[request_id]
                from_instance = req.from_instance
                print(f"[FriendManager] Found from_instance: {from_instance}", flush=True)
                sys.stdout.flush()

            result = await self.registry_client.accept_friend_request(
                request_id=request_id,
                accept=accept
            )

            msg = f"[FriendManager] Registry result: {result}"
            print(msg, flush=True)
            sys.stdout.flush()

            if result.get("success") and accept and from_instance:
                # 接受好友请求后，将对方 bot 添加到好友列表
                # 注意：这里的 bot_id 需要从请求详情中获取
                # 由于 pending_requests 中没有 bot_id，我们通过 result 中的信息来推断
                # 或者从注册中心重新获取请求详情
                self.add_friend(from_instance, "__all__")  # 临时添加，等待心跳同步具体 bot
                msg = f"[FriendManager] 已添加好友实例: {from_instance}"
                print(msg, flush=True)
                sys.stdout.flush()

            # 从待处理列表中删除
            if request_id in self._pending_requests:
                del self._pending_requests[request_id]

            return result.get("success", False)

        except Exception as e:
            msg = f"[FriendManager] 确认好友请求异常: {e}"
            print(msg, flush=True)
            sys.stdout.flush()
            import traceback
            traceback.print_exc()
            return False

    async def get_pending_requests(self) -> List[FriendRequest]:
        """
        获取待处理的好友请求

        Returns:
            好友请求列表
        """
        try:
            requests_data = await self.registry_client.get_friend_requests()

            requests = []
            for req_data in requests_data:
                friend_req = FriendRequest(
                    request_id=req_data["request_id"],
                    from_instance=req_data["from_instance"],
                    to_instance=req_data["to_instance"],
                    from_token=req_data["from_token"],
                    message=req_data.get("message", "")
                )
                requests.append(friend_req)
                # 存储到待处理字典中，以便 accept_friend_request 可以访问
                self._pending_requests[friend_req.request_id] = friend_req

            return requests

        except Exception as e:
            print(f"[FriendManager] 获取待处理请求异常: {e}")
            return []

    def is_friend(self, instance_id: str, bot_id: str = "") -> bool:
        """
        检查是否是好友（Bot 级别）

        Args:
            instance_id: 实例 ID
            bot_id: Bot ID（为空则检查实例是否有任何好友 bot）

        Returns:
            是否是好友
        """
        if instance_id not in self._friends:
            return False
        if not bot_id:
            return len(self._friends[instance_id]) > 0
        return bot_id in self._friends[instance_id] or "__all__" in self._friends[instance_id]

    def add_friend(self, instance_id: str, bot_id: str = ""):
        """
        添加好友（Bot 级别）

        Args:
            instance_id: 实例 ID
            bot_id: Bot ID（为空则添加整个实例）
        """
        if instance_id not in self._friends:
            self._friends[instance_id] = set()
        if bot_id:
            self._friends[instance_id].add(bot_id)
        else:
            self._friends[instance_id].add("__all__")

    def remove_friend(self, instance_id: str, bot_id: str = ""):
        """
        移除好友（Bot 级别）

        Args:
            instance_id: 实例 ID
            bot_id: Bot ID（为空则移除整个实例关系）
        """
        if instance_id not in self._friends:
            return

        if bot_id:
            self._friends[instance_id].discard(bot_id)
            # 如果没有 bot 了，删除整个实例
            if not self._friends[instance_id]:
                del self._friends[instance_id]
        else:
            del self._friends[instance_id]

    def get_friends(self) -> List[dict]:
        """
        获取好友列表（Bot 级别）

        Returns:
            好友列表，每项包含 instance_id 和 bot_id
        """
        result = []
        for instance_id, bot_ids in self._friends.items():
            for bot_id in bot_ids:
                result.append({
                    "instance_id": instance_id,
                    "bot_id": bot_id
                })
        return result

    def get_friends_by_instance(self) -> Dict[str, List[str]]:
        """
        按实例分组获取好友 bot 列表

        Returns:
            {instance_id: [bot_id1, bot_id2, ...]}
        """
        return {k: list(v) for k, v in self._friends.items()}
