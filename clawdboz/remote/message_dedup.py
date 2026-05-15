"""
消息去重和排序管理器
确保消息处理的幂等性和顺序性
"""
import time
import hashlib
import threading
from typing import Dict, Set, Optional, Tuple
from dataclasses import dataclass, field
from collections import OrderedDict
from enum import Enum

from clawdboz.remote.message import RemoteMessage


class DuplicateAction(str, Enum):
    """重复消息处理策略"""
    SKIP = "skip"  # 跳过重复消息
    MERGE = "merge"  # 合并重复消息
    REPLACE = "replace"  # 替换旧消息


@dataclass
class MessageMetadata:
    """消息元数据"""
    message_id: str
    content_hash: str
    timestamp: float
    seen_at: float = field(default_factory=time.time)
    processed: bool = False


@dataclass
class IdempotencyKey:
    """幂等性键"""
    key: str
    message_id: str
    expires_at: float


class LRUCache:
    """LRU 缓存实现"""

    def __init__(self, capacity: int = 1000):
        """
        初始化 LRU 缓存

        Args:
            capacity: 缓存容量
        """
        self.capacity = capacity
        self.cache: OrderedDict = OrderedDict()
        self._lock = threading.RLock()

    def get(self, key: str) -> Optional[MessageMetadata]:
        """获取缓存项"""
        with self._lock:
            if key in self.cache:
                # 移动到末尾（最近使用）
                self.cache.move_to_end(key)
                return self.cache[key]
            return None

    def put(self, key: str, value: MessageMetadata):
        """放入缓存项"""
        with self._lock:
            if key in self.cache:
                self.cache.move_to_end(key)
            self.cache[key] = value

            # 超过容量，删除最久未使用的项
            if len(self.cache) > self.capacity:
                self.cache.popitem(last=False)

    def remove(self, key: str):
        """移除缓存项"""
        with self._lock:
            if key in self.cache:
                del self.cache[key]

    def clear(self):
        """清空缓存"""
        with self._lock:
            self.cache.clear()

    def size(self) -> int:
        """获取缓存大小"""
        with self._lock:
            return len(self.cache)


class MessageDeduplicator:
    """消息去重器"""

    def __init__(
        self,
        cache_size: int = 1000,
        ttl_seconds: int = 3600,
        cleanup_interval: int = 300
    ):
        """
        初始化消息去重器

        Args:
            cache_size: LRU 缓存容量
            ttl_seconds: 消息记录生存时间（秒）
            cleanup_interval: 清理间隔（秒）
        """
        self.cache_size = cache_size
        self.ttl_seconds = ttl_seconds
        self.cleanup_interval = cleanup_interval

        # LRU 缓存 {message_id: MessageMetadata}
        self._cache = LRUCache(cache_size)

        # 内容哈希索引 {content_hash: message_id}
        self._content_hash_index: Dict[str, str] = {}

        # 序列号 {instance_id: sequence_number}
        self._sequence_numbers: Dict[str, int] = {}

        # 幂等性键 {key: IdempotencyKey}
        self._idempotency_keys: Dict[str, IdempotencyKey] = {}

        # 会话消息 {chat_id: Set[message_id]}
        self._session_messages: Dict[str, Set[str]] = {}

        # 清理线程
        self._cleanup_thread: Optional[threading.Thread] = None
        self._running = False

        # 统计信息
        self._stats = {
            "total_seen": 0,
            "duplicates_found": 0,
            "cache_hits": 0,
            "cache_misses": 0
        }

    def start(self):
        """启动去重器"""
        if self._running:
            return

        self._running = True

        # 启动清理线程
        self._cleanup_thread = threading.Thread(
            target=self._cleanup_loop,
            daemon=True,
            name="MessageDeduplicator-Cleanup"
        )
        self._cleanup_thread.start()

        print(f"[MessageDeduplicator] 已启动 (缓存={self.cache_size}, TTL={self.ttl_seconds}s)")

    def stop(self):
        """停止去重器"""
        self._running = False

        if self._cleanup_thread:
            self._cleanup_thread.join(timeout=5)
            self._cleanup_thread = None

        print("[MessageDeduplicator] 已停止")

    def dedup_message(
        self,
        message: RemoteMessage,
        chat_id: str,
        action: DuplicateAction = DuplicateAction.SKIP
    ) -> Tuple[bool, Optional[RemoteMessage]]:
        """
        去重消息

        Args:
            message: 远程消息
            chat_id: 会话 ID
            action: 重复消息处理策略

        Returns:
            (is_duplicate, result_message) 元组
            - is_duplicate: 是否重复
            - result_message: 处理后的消息（如果是重复且 action=SKIP，则为 None）
        """
        self._stats["total_seen"] += 1

        # 生成内容哈希（基于序列化的参数）
        content_hash = self._hash_content_from_params(message.params)

        # 检查消息 ID 是否已存在
        cached = self._cache.get(message.message_id)

        if cached:
            self._stats["duplicates_found"] += 1
            self._stats["cache_hits"] += 1

            # 消息 ID 重复
            if action == DuplicateAction.SKIP:
                return True, None
            elif action == DuplicateAction.REPLACE:
                # 更新缓存
                new_meta = MessageMetadata(
                    message_id=message.message_id,
                    content_hash=content_hash,
                    timestamp=message.timestamp
                )
                self._cache.put(message.message_id, new_meta)
                return True, message
            elif action == DuplicateAction.MERGE:
                # 合并参数（简单追加到 message 字段）
                existing_params = message.params.get("message", "")
                new_content = f"{cached.content_hash}\n{existing_params}"
                message.params["message"] = new_content
                return True, message

        # 检查内容哈希是否重复
        if content_hash in self._content_hash_index:
            existing_id = self._content_hash_index[content_hash]
            if existing_id != message.message_id:
                # 内容重复但 ID 不同
                self._stats["duplicates_found"] += 1
                if action == DuplicateAction.SKIP:
                    return True, None
                elif action == DuplicateAction.REPLACE:
                    # 移除旧记录
                    self._cache.remove(existing_id)
                    del self._content_hash_index[content_hash]
                    # 添加新记录
                    meta = MessageMetadata(
                        message_id=message.message_id,
                        content_hash=content_hash,
                        timestamp=message.timestamp
                    )
                    self._cache.put(message.message_id, meta)
                    self._content_hash_index[content_hash] = message.message_id
                    return True, message

        # 检查序列号
        from_instance = getattr(message, 'from_instance', '')
        if from_instance:
            last_seq = self._sequence_numbers.get(from_instance, 0)
            current_seq = getattr(message, 'sequence_number', 0)

            if current_seq > 0 and current_seq <= last_seq:
                # 序列号重复或乱序
                self._stats["duplicates_found"] += 1
                if action == DuplicateAction.SKIP:
                    return True, None

            # 更新序列号
            if current_seq > last_seq:
                self._sequence_numbers[from_instance] = current_seq

        # 新消息
        self._stats["cache_misses"] += 1

        meta = MessageMetadata(
            message_id=message.message_id,
            content_hash=content_hash,
            timestamp=message.timestamp
        )

        self._cache.put(message.message_id, meta)
        self._content_hash_index[content_hash] = message.message_id

        # 添加到会话
        if chat_id not in self._session_messages:
            self._session_messages[chat_id] = set()
        self._session_messages[chat_id].add(message.message_id)

        return False, message

    def is_duplicate(self, message_id: str, params: dict = None) -> bool:
        """
        检查消息是否重复

        Args:
            message_id: 消息 ID
            params: 消息参数（可选，用于内容哈希检查）

        Returns:
            是否重复
        """
        # 检查消息 ID
        cached = self._cache.get(message_id)
        if cached:
            return True

        # 检查内容哈希
        if params:
            content_hash = self._hash_content_from_params(params)
            if content_hash in self._content_hash_index:
                return True

        return False

    def register_idempotency_key(
        self,
        key: str,
        message_id: str,
        ttl: int = 300
    ):
        """
        注册幂等性键

        Args:
            key: 幂等性键
            message_id: 关联的消息 ID
            ttl: 过期时间（秒）
        """
        idempotency_key = IdempotencyKey(
            key=key,
            message_id=message_id,
            expires_at=time.time() + ttl
        )

        self._idempotency_keys[key] = idempotency_key

    def check_idempotency(self, key: str) -> Optional[str]:
        """
        检查幂等性键

        Args:
            key: 幂等性键

        Returns:
            关联的消息 ID，如果键不存在或已过期则返回 None
        """
        idem_key = self._idempotency_keys.get(key)

        if not idem_key:
            return None

        if time.time() > idem_key.expires_at:
            # 过期，移除
            del self._idempotency_keys[key]
            return None

        return idem_key.message_id

    def mark_message_processed(self, message_id: str):
        """
        标记消息已处理

        Args:
            message_id: 消息 ID
        """
        cached = self._cache.get(message_id)
        if cached:
            cached.processed = True
            self._cache.put(message_id, cached)

    def is_message_processed(self, message_id: str) -> bool:
        """
        检查消息是否已处理

        Args:
            message_id: 消息 ID

        Returns:
            是否已处理
        """
        cached = self._cache.get(message_id)
        return cached.processed if cached else False

    def get_session_messages(self, chat_id: str) -> Set[str]:
        """
        获取会话的所有消息 ID

        Args:
            chat_id: 会话 ID

        Returns:
            消息 ID 集合
        """
        return self._session_messages.get(chat_id, set()).copy()

    def clear_session(self, chat_id: str):
        """
        清除会话消息

        Args:
            chat_id: 会话 ID
        """
        if chat_id in self._session_messages:
            # 从缓存中移除这些消息
            for message_id in self._session_messages[chat_id]:
                cached = self._cache.get(message_id)
                if cached:
                    # 从哈希索引中移除
                    if cached.content_hash in self._content_hash_index:
                        del self._content_hash_index[cached.content_hash]
                    # 从缓存中移除
                    self._cache.remove(message_id)

            # 清除会话
            del self._session_messages[chat_id]

            print(f"[MessageDeduplicator] 清除会话: {chat_id}")

    def get_statistics(self) -> dict:
        """
        获取统计信息

        Returns:
            统计信息字典
        """
        return {
            "total_seen": self._stats["total_seen"],
            "duplicates_found": self._stats["duplicates_found"],
            "cache_hits": self._stats["cache_hits"],
            "cache_misses": self._stats["cache_misses"],
            "cache_size": self._cache.size(),
            "cache_capacity": self.cache_size,
            "active_sessions": len(self._session_messages),
            "idempotency_keys": len(self._idempotency_keys),
            "sequence_numbers": len(self._sequence_numbers)
        }

    def _hash_content(self, content: str) -> str:
        """
        生成内容哈希

        Args:
            content: 消息内容

        Returns:
            SHA256 哈希值（前16位）
        """
        return hashlib.sha256(content.encode()).hexdigest()[:16]

    def _hash_content_from_params(self, params: dict) -> str:
        """
        从参数字典生成内容哈希

        Args:
            params: 参数字典

        Returns:
            SHA256 哈希值（前16位）
        """
        # 序列化参数字典（排序键以确保一致性）
        import json
        content = json.dumps(params, sort_keys=True)
        return self._hash_content(content)

    def _cleanup_loop(self):
        """清理循环"""
        while self._running:
            try:
                self._cleanup_expired()
                time.sleep(self.cleanup_interval)
            except Exception as e:
                print(f"[MessageDeduplicator] 清理失败: {e}")
                time.sleep(self.cleanup_interval)

    def _cleanup_expired(self):
        """清理过期记录"""
        now = time.time()
        cutoff_time = now - self.ttl_seconds

        # 清理缓存中的过期记录
        keys_to_remove = []

        # LRU 缓存是 OrderedDict，遍历时需要注意
        with self._cache._lock:
            for key, meta in list(self._cache.cache.items()):
                if meta.seen_at < cutoff_time:
                    keys_to_remove.append(key)

            for key in keys_to_remove:
                meta = self._cache.cache.get(key)
                if meta and meta.content_hash in self._content_hash_index:
                    del self._content_hash_index[meta.content_hash]
                del self._cache.cache[key]

        # 清理幂等性键
        expired_keys = [
            key
            for key, idem_key in self._idempotency_keys.items()
            if idem_key.expires_at < now
        ]

        for key in expired_keys:
            del self._idempotency_keys[key]

        if keys_to_remove or expired_keys:
            print(f"[MessageDeduplicator] 清理过期记录: "
                  f"消息={len(keys_to_remove)}, 幂等键={len(expired_keys)}")
