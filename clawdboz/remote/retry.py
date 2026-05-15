"""
消息重试机制
处理失败消息的重试、退避和死信队列
"""
import asyncio
import random
import time
import uuid
from collections import deque
from typing import Dict, Optional, Callable
from dataclasses import dataclass, field
from enum import Enum


class RetryStrategy(str, Enum):
    """重试策略"""
    EXPONENTIAL_BACKOFF = "exponential_backoff"
    LINEAR_BACKOFF = "linear_backoff"
    FIXED_DELAY = "fixed_delay"


@dataclass
class RetryMessage:
    """待重试的消息"""
    message_id: str
    bot_id: str
    method: str
    params: dict
    attempt_count: int = 0
    max_retries: int = 3
    created_at: float = field(default_factory=time.time)
    last_attempt_at: float = field(default_factory=time.time)
    last_error: str = ""
    backoff_until: float = 0.0  # 最早重试时间

    def can_retry(self) -> bool:
        """检查是否可以重试"""
        if self.attempt_count >= self.max_retries:
            return False
        return time.time() >= self.backoff_until

    def increment_attempt(self, error: str = ""):
        """增加尝试次数"""
        self.attempt_count += 1
        self.last_attempt_at = time.time()
        self.last_error = error


@dataclass
class DeadLetterMessage:
    """死信消息（永久失败）"""
    message_id: str
    bot_id: str
    method: str
    params: dict
    attempts: int
    final_error: str
    created_at: float = field(default_factory=time.time)
    failed_at: float = field(default_factory=time.time)


class MessageRetry:
    """消息重试管理器"""

    def __init__(
        self,
        max_retries: int = 3,
        retry_strategy: RetryStrategy = RetryStrategy.EXPONENTIAL_BACKOFF,
        base_delay: float = 2.0,
        max_delay: float = 60.0,
        jitter: bool = True
    ):
        """
        初始化消息重试管理器

        Args:
            max_retries: 最大重试次数
            retry_strategy: 重试策略
            base_delay: 基础延迟（秒）
            max_delay: 最大延迟（秒）
            jitter: 是否添加随机抖动（避免惊群效应）
        """
        self.max_retries = max_retries
        self.retry_strategy = retry_strategy
        self.base_delay = base_delay
        self.max_delay = max_delay
        self.jitter = jitter

        # 重试队列 {message_id: RetryMessage}
        self._retry_queue: Dict[str, RetryMessage] = {}

        # 死信队列（FIFO）
        self._dead_letter_queue: deque = deque(maxlen=1000)

        # 后台任务
        self._retry_task: Optional[asyncio.Task] = None
        self._running = False

        # 统计信息
        self._total_retries = 0
        self._total_failures = 0
        self._total_successes = 0

    def start(self):
        """启动重试处理器"""
        if self._running:
            return

        self._running = True
        self._retry_task = asyncio.create_task(self._retry_loop())
        print(f"[Retry] 消息重试处理器已启动 (策略={self.retry_strategy.value})")

    async def stop(self):
        """停止重试处理器"""
        self._running = False

        if self._retry_task:
            self._retry_task.cancel()
            try:
                await self._retry_task
            except asyncio.CancelledError:
                pass
            self._retry_task = None

        print(f"[Retry] 消息重试处理器已停止")

    async def _retry_loop(self):
        """重试循环"""
        while self._running:
            try:
                # 检查所有待重试消息
                ready_to_retry = [
                    msg for msg in self._retry_queue.values()
                    if msg.can_retry()
                ]

                for msg in ready_to_retry:
                    await self._process_retry(msg)

                # 短暂休眠
                await asyncio.sleep(1)

            except asyncio.CancelledError:
                break
            except Exception as e:
                print(f"[Retry] 重试循环失败: {e}")
                await asyncio.sleep(5)

    async def _process_retry(self, msg: RetryMessage):
        """
        处理重试

        Args:
            msg: 待重试消息
        """
        print(f"[Retry] 重试消息: {msg.message_id} (尝试 {msg.attempt_count + 1}/{msg.max_retries})")

        # 这里需要调用实际的发送逻辑
        # 由于循环依赖，我们使用回调
        # 实际发送在 RemoteBotManager 中实现

        # 临时模拟：直接标记为失败
        await self.mark_failed(msg.message_id, "Retry not implemented")

    def enqueue_for_retry(
        self,
        bot_id: str,
        method: str,
        params: dict,
        error: str = ""
    ) -> str:
        """
        将消息加入重试队列

        Args:
            bot_id: Bot ID
            method: 调用方法
            params: 参数
            error: 错误信息

        Returns:
            消息 ID
        """
        message_id = str(uuid.uuid4())

        retry_msg = RetryMessage(
            message_id=message_id,
            bot_id=bot_id,
            method=method,
            params=params,
            max_retries=self.max_retries
        )

        # 计算退避时间
        retry_msg.backoff_until = self._calculate_backoff(0)

        self._retry_queue[message_id] = retry_msg

        print(f"[Retry] 消息加入重试队列: {message_id}")

        return message_id

    def _calculate_backoff(self, attempt_count: int) -> float:
        """
        计算退避时间

        Args:
            attempt_count: 尝试次数

        Returns:
            退避时间戳
        """
        if self.retry_strategy == RetryStrategy.EXPONENTIAL_BACKOFF:
            delay = self.base_delay * (2 ** attempt_count)
        elif self.retry_strategy == RetryStrategy.LINEAR_BACKOFF:
            delay = self.base_delay * (attempt_count + 1)
        else:  # FIXED_DELAY
            delay = self.base_delay

        # 限制最大延迟
        delay = min(delay, self.max_delay)

        # 添加随机抖动（±25%）
        if self.jitter:
            delay = delay * (0.75 + random.random() * 0.5)

        return time.time() + delay

    def should_retry(self, message_id: str, error: str) -> bool:
        """
        判断是否应该重试

        Args:
            message_id: 消息 ID
            error: 错误信息

        Returns:
            是否应该重试
        """
        msg = self._retry_queue.get(message_id)
        if not msg:
            return False

        return msg.attempt_count < msg.max_retries

    async def mark_success(self, message_id: str):
        """
        标记消息成功

        Args:
            message_id: 消息 ID
        """
        if message_id in self._retry_queue:
            msg = self._retry_queue.pop(message_id)
            self._total_successes += 1
            print(f"[Retry] 消息成功: {message_id} (尝试 {msg.attempt_count} 次)")

    async def mark_failed(self, message_id: str, error: str):
        """
        标记消息失败

        Args:
            message_id: 消息 ID
            error: 错误信息
        """
        msg = self._retry_queue.get(message_id)
        if not msg:
            return

        msg.increment_attempt(error)

        # 检查是否应该移入死信队列
        if msg.attempt_count >= msg.max_retries:
            await self._move_to_dead_letter(msg, error)
            # 从重试队列移除
            self._retry_queue.pop(message_id, None)
        else:
            # 更新退避时间
            msg.backoff_until = self._calculate_backoff(msg.attempt_count)
            self._total_retries += 1
            print(f"[Retry] 消息失败，将重试: {message_id} (下次重试在 {int(msg.backoff_until - time.time())}s 后)")

    async def _move_to_dead_letter(self, msg: RetryMessage, error: str):
        """
        移动消息到死信队列

        Args:
            msg: 消息
            error: 错误信息
        """
        dead_letter = DeadLetterMessage(
            message_id=msg.message_id,
            bot_id=msg.bot_id,
            method=msg.method,
            params=msg.params,
            attempts=msg.attempt_count,
            final_error=error
        )

        self._dead_letter_queue.append(dead_letter)
        self._total_failures += 1

        print(f"[Retry] 消息移入死信队列: {msg.message_id} (尝试 {msg.attempt_count} 次)")

    def get_dead_letter_count(self) -> int:
        """获取死信队列大小"""
        return len(self._dead_letter_queue)

    def get_retry_queue_size(self) -> int:
        """获取重试队列大小"""
        return len(self._retry_queue)

    def get_statistics(self) -> dict:
        """获取统计信息"""
        return {
            "total_retries": self._total_retries,
            "total_failures": self._total_failures,
            "total_successes": self._total_successes,
            "retry_queue_size": len(self._retry_queue),
            "dead_letter_queue_size": len(self._dead_letter_queue),
            "success_rate": self._total_successes / max(1, self._total_successes + self._total_failures)
        }
