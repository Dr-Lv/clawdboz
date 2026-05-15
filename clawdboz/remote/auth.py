"""
Token 认证和管理模块
"""
import jwt
import time
import uuid
from typing import Dict, Optional, Set
from dataclasses import dataclass, field
from pathlib import Path
import json


@dataclass
class ChatTokenPayload:
    """聊天 Token 载荷"""
    instance_id: str
    bot_id: str
    chat_id: str
    iat: float
    exp: float
    token_id: str = ""  # 唯一标识符
    refreshed_from: str = ""  # 原始 token ID（刷新时）
    created_at: float = field(default_factory=time.time)
    revoked_at: Optional[float] = None  # 撤销时间

    def to_dict(self) -> dict:
        """转换为字典"""
        return {
            "instance_id": self.instance_id,
            "bot_id": self.bot_id,
            "chat_id": self.chat_id,
            "iat": int(self.iat),
            "exp": int(self.exp),
            "token_id": self.token_id,
            "refreshed_from": self.refreshed_from,
            "created_at": int(self.created_at),
            "revoked_at": int(self.revoked_at) if self.revoked_at else None
        }


class TokenManager:
    """Token 管理器"""

    def __init__(
        self,
        secret_key: str,
        blacklist_path: Optional[Path] = None,
        grace_period_seconds: int = 300
    ):
        """
        初始化 Token 管理器

        Args:
            secret_key: 用于签名和验证 Token 的密钥
            blacklist_path: Token 黑名单存储路径
            grace_period_seconds: 刷新宽限期（秒）
        """
        self.secret_key = secret_key
        self.grace_period_seconds = grace_period_seconds

        # Token 黑名单 {token_id: reason}
        self._blacklist: Dict[str, str] = {}

        # Token 元数据 {token_id: token_metadata}
        self._token_metadata: Dict[str, dict] = {}

        # 黑名单持久化路径
        self._blacklist_path = blacklist_path or Path("WORKPLACE/.remote/token_blacklist.json")

        # 加载黑名单
        self._load_blacklist()

    def generate_chat_token(
        self,
        instance_id: str,
        bot_id: str,
        chat_id: str,
        ttl: int = 3600
    ) -> str:
        """
        生成聊天会话 Token

        Args:
            instance_id: 实例 ID
            bot_id: Bot ID
            chat_id: 聊天 ID（单聊或群聊）
            ttl: 过期时间（秒），默认 1 小时

        Returns:
            JWT Token 字符串
        """
        payload = {
            "instance_id": instance_id,
            "bot_id": bot_id,
            "chat_id": chat_id,
            "iat": int(time.time()),
            "exp": int(time.time()) + ttl
        }

        token = jwt.encode(payload, self.secret_key, algorithm="HS256")
        return token

    def verify_chat_token(self, token: str) -> ChatTokenPayload:
        """
        验证并解析 Token

        Args:
            token: JWT Token 字符串

        Returns:
            ChatTokenPayload 对象

        Raises:
            HTTPException: Token 无效或过期
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=["HS256"]
            )
            return ChatTokenPayload(
                instance_id=payload["instance_id"],
                bot_id=payload["bot_id"],
                chat_id=payload["chat_id"],
                iat=payload["iat"],
                exp=payload["exp"]
            )
        except jwt.ExpiredSignatureError:
            raise ValueError("Token has expired")
        except jwt.InvalidTokenError as e:
            raise ValueError(f"Invalid token: {str(e)}")

    def generate_instance_token(self, instance_id: str, ttl: int = 86400) -> str:
        """
        生成实例认证 Token（用于注册服务器）

        Args:
            instance_id: 实例 ID
            ttl: 过期时间（秒），默认 24 小时

        Returns:
            JWT Token 字符串
        """
        payload = {
            "instance_id": instance_id,
            "iat": int(time.time()),
            "exp": int(time.time()) + ttl
        }

        token = jwt.encode(payload, self.secret_key, algorithm="HS256")
        return token

    def verify_instance_token(self, token: str) -> str:
        """
        验证实例 Token

        Args:
            token: JWT Token 字符串

        Returns:
            实例 ID

        Raises:
            ValueError: Token 无效或过期
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=["HS256"]
            )
            return payload["instance_id"]
        except jwt.ExpiredSignatureError:
            raise ValueError("Instance token has expired")
        except jwt.InvalidTokenError as e:
            raise ValueError(f"Invalid instance token: {str(e)}")

    def refresh_token(self, token: str, new_ttl: int = None) -> str:
        """
        刷新过期的 Token

        Args:
            token: 原始 Token
            new_ttl: 新的 TTL（可选），默认使用原 TTL

        Returns:
            新的 Token

        Raises:
            ValueError: Token 无效或在黑名单中
        """
        # 验证原 Token（即使过期也要能解析）
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=["HS256"],
                options={"verify_exp": False}
            )
        except jwt.InvalidTokenError as e:
            raise ValueError(f"Invalid token: {str(e)}")

        # 检查是否在黑名单中
        token_id = payload.get("token_id", "")
        if token_id in self._blacklist:
            raise ValueError(f"Token has been revoked: {self._blacklist[token_id]}")

        # 计算原 TTL
        original_ttl = payload.get("exp", 0) - payload.get("iat", 0)
        ttl = new_ttl or original_ttl

        # 生成新 Token
        new_token_id = str(uuid.uuid4())
        new_payload = payload.copy()
        new_payload["iat"] = int(time.time())
        new_payload["exp"] = int(time.time()) + ttl
        new_payload["token_id"] = new_token_id
        new_payload["refreshed_from"] = token_id

        # 编码新 Token
        new_token = jwt.encode(new_payload, self.secret_key, algorithm="HS256")

        # 记录元数据
        self._token_metadata[new_token_id] = {
            "instance_id": payload.get("instance_id", ""),
            "bot_id": payload.get("bot_id", ""),
            "chat_id": payload.get("chat_id", ""),
            "created_at": time.time(),
            "refreshed_from": token_id
        }

        return new_token

    def revoke_token(self, token: str, reason: str = "Manual revocation"):
        """
        撤销 Token（加入黑名单）

        Args:
            token: 要撤销的 Token
            reason: 撤销原因
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=["HS256"],
                options={"verify_exp": False}
            )

            token_id = payload.get("token_id", "")

            # 如果没有 token_id，使用 token 的哈希作为 ID
            if not token_id:
                import hashlib
                token_id = hashlib.sha256(token.encode()).hexdigest()[:16]

            # 添加到黑名单
            self._blacklist[token_id] = reason

            # 更新元数据
            if token_id in self._token_metadata:
                self._token_metadata[token_id]["revoked_at"] = time.time()
                self._token_metadata[token_id]["revoke_reason"] = reason

            # 持久化黑名单
            self._save_blacklist()

            print(f"[TokenManager] Token 已撤销: {token_id}, 原因: {reason}")

        except jwt.InvalidTokenError as e:
            print(f"[TokenManager] 撤销 Token 失败: {e}")

    def is_token_revoked(self, token_id: str) -> bool:
        """
        检查 Token 是否已被撤销

        Args:
            token_id: Token ID

        Returns:
            是否已撤销
        """
        return token_id in self._blacklist

    def token_rotation(
        self,
        instance_id: str,
        bot_id: str,
        chat_id: str,
        current_ttl: int = 3600,
        rotation_threshold: float = 0.8
    ) -> tuple[str, float]:
        """
        自动轮转 Token（在过期前一定时间自动刷新）

        Args:
            instance_id: 实例 ID
            bot_id: Bot ID
            chat_id: 会话 ID
            current_ttl: 当前 TTL
            rotation_threshold: 轮转阈值（0.8 = 在 80% 生命周期时轮转）

        Returns:
            (token, expires_at) 元组
        """
        # 计算轮转时间
        rotation_time = time.time() + (current_ttl * rotation_threshold)

        # 如果还没到轮转时间，返回 None
        if time.time() < rotation_time:
            return None

        # 生成新 Token
        new_token = self.generate_chat_token(
            instance_id=instance_id,
            bot_id=bot_id,
            chat_id=chat_id,
            ttl=current_ttl
        )

        # 提取过期时间
        payload = jwt.decode(
            new_token,
            self.secret_key,
            algorithms=["HS256"],
            options={"verify_exp": False}
        )
        expires_at = payload["exp"]

        return new_token, expires_at

    def verify_chat_token_with_grace(
        self,
        token: str
    ) -> tuple[Optional[ChatTokenPayload], bool]:
        """
        验证 Token（支持宽限期）

        Args:
            token: JWT Token 字符串

        Returns:
            (ChatTokenPayload, needs_refresh) 元组
        """
        try:
            payload = jwt.decode(
                token,
                self.secret_key,
                algorithms=["HS256"]
            )

            token_obj = ChatTokenPayload(
                instance_id=payload["instance_id"],
                bot_id=payload["bot_id"],
                chat_id=payload["chat_id"],
                iat=payload["iat"],
                exp=payload["exp"],
                token_id=payload.get("token_id", ""),
                refreshed_from=payload.get("refreshed_from", ""),
                created_at=payload.get("created_at", time.time()),
                revoked_at=payload.get("revoked_at")
            )

            # 检查是否撤销
            if token_obj.token_id and self.is_token_revoked(token_obj.token_id):
                raise ValueError("Token has been revoked")

            # 检查是否需要刷新
            now = time.time()
            time_left = token_obj.exp - now
            needs_refresh = time_left < self.grace_period_seconds

            return token_obj, needs_refresh

        except jwt.ExpiredSignatureError:
            # 在宽限期内允许使用
            try:
                payload = jwt.decode(
                    token,
                    self.secret_key,
                    algorithms=["HS256"],
                    options={"verify_exp": False}
                )

                token_obj = ChatTokenPayload(
                    instance_id=payload["instance_id"],
                    bot_id=payload["bot_id"],
                    chat_id=payload["chat_id"],
                    iat=payload["iat"],
                    exp=payload["exp"],
                    token_id=payload.get("token_id", ""),
                    refreshed_from=payload.get("refreshed_from", ""),
                    created_at=payload.get("created_at", time.time())
                )

                # 检查是否撤销
                if token_obj.token_id and self.is_token_revoked(token_obj.token_id):
                    raise ValueError("Token has been revoked")

                return token_obj, True  # 已过期，需要刷新

            except Exception:
                raise ValueError("Token has expired and is invalid")
        except jwt.InvalidTokenError as e:
            raise ValueError(f"Invalid token: {str(e)}")

    def _load_blacklist(self):
        """从文件加载黑名单"""
        if not self._blacklist_path.exists():
            return

        try:
            with open(self._blacklist_path, 'r', encoding='utf-8') as f:
                data = json.load(f)
                self._blacklist = data.get("blacklist", {})
                self._token_metadata = data.get("metadata", {})
        except Exception as e:
            print(f"[TokenManager] 加载黑名单失败: {e}")

    def _save_blacklist(self):
        """保存黑名单到文件"""
        try:
            self._blacklist_path.parent.mkdir(parents=True, exist_ok=True)

            data = {
                "blacklist": self._blacklist,
                "metadata": self._token_metadata
            }

            with open(self._blacklist_path, 'w', encoding='utf-8') as f:
                json.dump(data, f, indent=2, ensure_ascii=False)

        except Exception as e:
            print(f"[TokenManager] 保存黑名单失败: {e}")

    def cleanup_expired_blacklist(self, max_age_seconds: int = 86400):
        """
        清理过期的黑名单条目

        Args:
            max_age_seconds: 最大保留时间（秒），默认 24 小时
        """
        now = time.time()
        cutoff_time = now - max_age_seconds

        # 清理元数据
        expired_tokens = []
        for token_id, metadata in self._token_metadata.items():
            revoked_at = metadata.get("revoked_at")
            if revoked_at and revoked_at < cutoff_time:
                expired_tokens.append(token_id)

        for token_id in expired_tokens:
            del self._token_metadata[token_id]
            if token_id in self._blacklist:
                del self._blacklist[token_id]

        if expired_tokens:
            self._save_blacklist()
            print(f"[TokenManager] 清理了 {len(expired_tokens)} 个过期的黑名单条目")
