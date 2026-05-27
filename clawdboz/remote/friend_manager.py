"""
好友管理模块 - Bot 级别好友关系（去中心化 + RSA）
注册中心不记录好友状态，所有关系双向存储在各自实例本地
"""
import asyncio
import json
import sys
import uuid
from pathlib import Path
from typing import List, Optional, Dict, Set, Callable
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
        message: str = "",
        from_bot_id: str = "",
        to_bot_id: str = "",
        from_public_key: str = "",
        to_public_key: str = ""
    ):
        self.request_id = request_id
        self.from_instance = from_instance
        self.to_instance = to_instance
        self.from_token = from_token
        self.message = message
        self.from_bot_id = from_bot_id
        self.to_bot_id = to_bot_id
        self.from_public_key = from_public_key
        self.to_public_key = to_public_key
        self.status = FriendStatus.PENDING
        self.created_at = 0

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "request_id": self.request_id,
            "from_instance": self.from_instance,
            "to_instance": self.to_instance,
            "from_token": self.from_token,
            "message": self.message,
            "from_bot_id": self.from_bot_id,
            "to_bot_id": self.to_bot_id,
            "from_public_key": self.from_public_key,
            "to_public_key": self.to_public_key,
            "status": self.status.value,
            "created_at": self.created_at
        }

    @classmethod
    def from_dict(cls, data: dict) -> "FriendRequest":
        """从字典创建"""
        req = cls(
            request_id=data["request_id"],
            from_instance=data["from_instance"],
            to_instance=data["to_instance"],
            from_token=data.get("from_token", ""),
            message=data.get("message", ""),
            from_bot_id=data.get("from_bot_id", ""),
            to_bot_id=data.get("to_bot_id", ""),
            from_public_key=data.get("from_public_key", ""),
            to_public_key=data.get("to_public_key", "")
        )
        req.status = FriendStatus(data.get("status", "pending"))
        req.created_at = data.get("created_at", 0)
        return req


class FriendManager:
    """好友管理器 - Bot 级别（去中心化设计）"""

    def __init__(
        self,
        registry_client,
        crypto,
        base_workplace: str,
        on_friend_accepted: Callable = None,
        on_friend_removed: Callable = None
    ):
        """
        初始化好友管理器

        Args:
            registry_client: 注册服务器客户端
            crypto: InstanceCrypto 实例
            base_workplace: 基础工作目录
            on_friend_accepted: 接受好友后的回调，签名 (from_instance, bot_id)
            on_friend_removed: 移除好友后的回调，签名 (instance_id, bot_id)
        """
        self.registry_client = registry_client
        self.crypto = crypto
        self.on_friend_accepted = on_friend_accepted
        self.on_friend_removed = on_friend_removed

        # instance_id -> {bot_id1, bot_id2, ...}
        self._friends: Dict[str, Set[str]] = {}
        self._pending_requests: Dict[str, FriendRequest] = {}

        # pending 请求持久化文件
        self._pending_file = Path(base_workplace) / ".remote" / "pending_requests.json"
        self._load_pending_requests()

        # 好友关系持久化文件
        self._friends_file = Path(base_workplace) / ".remote" / "friends.json"
        self._load_friends()

    # ------------------------------------------------------------------
    # 本地持久化
    # ------------------------------------------------------------------

    def _load_pending_requests(self):
        """从本地文件加载 pending 请求"""
        try:
            if self._pending_file.exists():
                with open(self._pending_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for req_data in data.values():
                    req = FriendRequest.from_dict(req_data)
                    self._pending_requests[req.request_id] = req
                print(f"[FriendManager] 加载了 {len(self._pending_requests)} 个 pending 请求")
        except Exception as e:
            print(f"[FriendManager] 加载 pending 请求失败: {e}")
            self._pending_requests = {}

    def _save_pending_requests(self):
        """保存 pending 请求到本地文件"""
        try:
            self._pending_file.parent.mkdir(parents=True, exist_ok=True)
            data = {req_id: req.to_dict() for req_id, req in self._pending_requests.items()}
            with open(self._pending_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[FriendManager] 保存 pending 请求失败: {e}")

    def _load_friends(self):
        """从本地文件加载好友关系"""
        try:
            if self._friends_file.exists():
                with open(self._friends_file, "r", encoding="utf-8") as f:
                    data = json.load(f)
                for instance_id, bot_ids in data.items():
                    self._friends[instance_id] = set(bot_ids)
                print(f"[FriendManager] 加载了 {len(self._friends)} 个好友关系")
        except Exception as e:
            print(f"[FriendManager] 加载好友关系失败: {e}")
            self._friends = {}

    def _save_friends(self):
        """保存好友关系到本地文件"""
        try:
            self._friends_file.parent.mkdir(parents=True, exist_ok=True)
            data = {instance_id: list(bot_ids) for instance_id, bot_ids in self._friends.items()}
            with open(self._friends_file, "w", encoding="utf-8") as f:
                json.dump(data, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[FriendManager] 保存好友关系失败: {e}")

    # ------------------------------------------------------------------
    # 发送/接收好友请求
    # ------------------------------------------------------------------

    async def send_friend_request(
        self,
        to_instance: str,
        message: str = "",
        to_bot_id: str = "",
        from_bot_id: str = ""
    ) -> FriendRequest:
        """
        发送好友请求（Bot 级别），附带上自己的 RSA 公钥
        """
        request_id = str(uuid.uuid4())
        from_instance = self.registry_client.instance_info["instance_id"]
        from_token = self.registry_client.instance_info["token"]

        payload = {
            "request_id": request_id,
            "from_instance": from_instance,
            "to_instance": to_instance,
            "from_bot_id": from_bot_id,
            "to_bot_id": to_bot_id,
            "from_token": from_token,
            "message": message,
            "from_public_key": self.crypto.get_public_key_pem()
        }

        try:
            result = await self.registry_client.send_friend_request(
                to_instance=to_instance,
                message=message,
                request_id=request_id,
                to_bot_id=to_bot_id,
                from_bot_id=from_bot_id,
                from_public_key=self.crypto.get_public_key_pem()
            )

            if result.get("success"):
                friend_req = FriendRequest(
                    request_id=request_id,
                    from_instance=from_instance,
                    to_instance=to_instance,
                    from_token=from_token,
                    message=message,
                    from_bot_id=from_bot_id,
                    to_bot_id=to_bot_id,
                    from_public_key=self.crypto.get_public_key_pem()
                )
                # 发送方不存储 pending，由接收方存储
                return friend_req
            else:
                raise Exception(f"发送好友请求失败: {result}")

        except Exception as e:
            print(f"[FriendManager] 发送好友请求异常: {e}")
            raise

    def receive_friend_request(self, data: dict):
        """
        收到注册中心转发的好友请求通知（WebSocket）
        """
        try:
            print(f"[FriendManager] receive_friend_request raw data: {data}")
            req = FriendRequest(
                request_id=data["request_id"],
                from_instance=data["from_instance"],
                to_instance=self.registry_client.instance_info["instance_id"],
                from_token=data.get("from_token", ""),
                message=data.get("message", ""),
                from_bot_id=data.get("from_bot_id", ""),
                to_bot_id=data.get("to_bot_id", ""),
                from_public_key=data.get("from_public_key", "")
            )
            req.created_at = data.get("timestamp", 0)
            self._pending_requests[req.request_id] = req
            self._save_pending_requests()
            print(f"[FriendManager] 收到好友请求: {req.request_id} from {req.from_instance}, to_bot_id={req.to_bot_id}, from_bot_id={req.from_bot_id}")
        except Exception as e:
            print(f"[FriendManager] 处理收到的好友请求异常: {e}")

    # ------------------------------------------------------------------
    # 接受/拒绝好友请求
    # ------------------------------------------------------------------

    async def accept_friend_request(
        self,
        request_id: str,
        accept: bool = True
    ) -> bool:
        """
        确认/拒绝好友请求
        接受后：保存对方公钥、建立本地好友关系、通知对方自己的公钥
        """
        try:
            print(f"[FriendManager] accept_friend_request: request_id={request_id}, accept={accept}", flush=True)

            req = self._pending_requests.get(request_id)
            if not req:
                print(f"[FriendManager] 未找到 pending 请求: {request_id}")
                return False

            from_instance = req.from_instance
            bot_id = req.to_bot_id or req.from_bot_id or ""

            if accept:
                # 保存对方公钥
                if req.from_public_key:
                    self.crypto.save_friend_public_key(from_instance, req.from_public_key)

                # 建立本地好友关系
                self.add_friend(from_instance, bot_id or "__all__")
                print(f"[FriendManager] 已添加好友: {from_instance}, bot: {bot_id or '__all__'}")

                # 通过回调通知 manager 发送接受通知（携带自己的公钥）
                if self.on_friend_accepted:
                    try:
                        await self.on_friend_accepted(from_instance, bot_id)
                    except Exception as e:
                        print(f"[FriendManager] on_friend_accepted 回调失败（非阻塞）: {e}")

            # 从 pending 中删除
            if request_id in self._pending_requests:
                del self._pending_requests[request_id]
                self._save_pending_requests()

            return True

        except Exception as e:
            print(f"[FriendManager] 确认好友请求异常: {e}")
            import traceback
            traceback.print_exc()
            return False

    def receive_friend_accept(self, data: dict):
        """
        收到对方的好友接受通知（WebSocket）
        """
        try:
            print(f"[FriendManager] receive_friend_accept raw data: {data}")
            from_instance = data.get("from_instance")
            bot_id = data.get("bot_id", "")
            public_key = data.get("public_key", "")

            if public_key:
                self.crypto.save_friend_public_key(from_instance, public_key)

            self.add_friend(from_instance, bot_id or "__all__")
            print(f"[FriendManager] 对方已接受好友: {from_instance}, bot: {bot_id or '__all__'}")
        except Exception as e:
            print(f"[FriendManager] 处理好友接受通知异常: {e}")

    # ------------------------------------------------------------------
    # 移除好友
    # ------------------------------------------------------------------

    def remove_friend(self, instance_id: str, bot_id: str = ""):
        """
        移除好友（Bot 级别），同时删除对方的公钥
        """
        if instance_id not in self._friends:
            return

        # 删除对方的公钥
        self.crypto.remove_friend_key(instance_id)

        if bot_id:
            self._friends[instance_id].discard(bot_id)
            if not self._friends[instance_id]:
                del self._friends[instance_id]
        else:
            del self._friends[instance_id]

        self._save_friends()
        print(f"[FriendManager] 已移除好友: {instance_id}:{bot_id or 'all'}")

    def receive_friend_remove(self, data: dict):
        """
        收到对方的好友解除通知（WebSocket）
        自动清理本地关系
        """
        try:
            from_instance = data.get("from_instance")
            bot_id = data.get("bot_id", "")

            print(f"[FriendManager] 收到好友解除通知: {from_instance}:{bot_id or 'all'}")

            # 删除对方的公钥
            self.crypto.remove_friend_key(from_instance)

            # 清理好友关系
            if from_instance in self._friends:
                if bot_id:
                    self._friends[from_instance].discard(bot_id)
                    if not self._friends[from_instance]:
                        del self._friends[from_instance]
                else:
                    del self._friends[from_instance]
                self._save_friends()

            # 触发回调（让 manager 清理 bot_subscribers / added_bots）
            if self.on_friend_removed:
                try:
                    asyncio.create_task(self.on_friend_removed(from_instance, bot_id))
                except Exception as e:
                    print(f"[FriendManager] on_friend_removed 回调失败: {e}")

        except Exception as e:
            print(f"[FriendManager] 处理好友解除通知异常: {e}")

    # ------------------------------------------------------------------
    # 查询
    # ------------------------------------------------------------------

    def get_pending_requests(self) -> List[FriendRequest]:
        """获取待处理的好友请求（从本地内存）"""
        return list(self._pending_requests.values())

    def is_friend(self, instance_id: str, bot_id: str = "") -> bool:
        """检查是否是好友（Bot 级别）"""
        if instance_id not in self._friends:
            return False
        if not bot_id:
            return len(self._friends[instance_id]) > 0
        return bot_id in self._friends[instance_id] or "__all__" in self._friends[instance_id]

    def add_friend(self, instance_id: str, bot_id: str = ""):
        """添加好友（Bot 级别）"""
        if instance_id not in self._friends:
            self._friends[instance_id] = set()
        if bot_id:
            self._friends[instance_id].add(bot_id)
        else:
            self._friends[instance_id].add("__all__")
        self._save_friends()

    def get_friends(self) -> List[dict]:
        """获取好友列表"""
        result = []
        for instance_id, bot_ids in self._friends.items():
            for bot_id in bot_ids:
                result.append({
                    "instance_id": instance_id,
                    "bot_id": bot_id
                })
        return result

    def get_friends_by_instance(self) -> Dict[str, List[str]]:
        """按实例分组获取好友 bot 列表"""
        return {k: list(v) for k, v in self._friends.items()}
