"""
错误处理器和断路器模式
处理远程连接错误、超时、认证失败和文件访问错误
"""
import asyncio
import time
from enum import Enum
from typing import Dict, Optional, Callable
from dataclasses import dataclass, field


class CircuitBreakerState(str, Enum):
    """断路器状态"""
    CLOSED = "closed"  # 正常，请求通过
    OPEN = "open"  # 熔断，请求直接失败
    HALF_OPEN = "half_open"  # 半开，允许试探性请求


class ErrorType(str, Enum):
    """错误类型"""
    CONNECTION_ERROR = "connection_error"
    TIMEOUT = "timeout"
    AUTH_FAILURE = "auth_failure"
    FS_ERROR = "fs_error"
    UNKNOWN = "unknown"


@dataclass
class ErrorRecord:
    """错误记录"""
    error_type: ErrorType
    message: str
    timestamp: float = field(default_factory=time.time)
    instance_id: str = ""
    bot_id: str = ""


@dataclass
class CircuitBreakerConfig:
    """断路器配置"""
    failure_threshold: int = 5  # 失败阈值
    success_threshold: int = 2  # 成功阈值（半开状态）
    timeout: float = 60.0  # 熔断超时（秒）
    half_open_max_calls: int = 3  # 半开状态最大调用次数


class CircuitBreaker:
    """断路器"""

    def __init__(
        self,
        instance_id: str,
        config: Optional[CircuitBreakerConfig] = None
    ):
        """
        初始化断路器

        Args:
            instance_id: 实例 ID
            config: 断路器配置
        """
        self.instance_id = instance_id
        self.config = config or CircuitBreakerConfig()

        self.state = CircuitBreakerState.CLOSED
        self.failure_count = 0
        self.success_count = 0
        self.last_failure_time: float = 0
        self.last_state_change: float = time.time()

        # 半开状态调用计数
        self._half_open_calls = 0

    def record_success(self):
        """记录成功"""
        self.failure_count = 0
        self.success_count += 1

        if self.state == CircuitBreakerState.HALF_OPEN:
            self._half_open_calls += 1

            # 检查是否应该恢复到闭合状态
            if self.success_count >= self.config.success_threshold:
                self._transition_to_closed()

    def record_failure(self, error_type: ErrorType = ErrorType.UNKNOWN):
        """记录失败"""
        self.failure_count += 1
        self.last_failure_time = time.time()
        self.success_count = 0

        # 检查是否应该熔断
        if self.state == CircuitBreakerState.CLOSED:
            if self.failure_count >= self.config.failure_threshold:
                self._transition_to_open()
        elif self.state == CircuitBreakerState.HALF_OPEN:
            # 半开状态下的失败直接熔断
            self._transition_to_open()

    def _transition_to_open(self):
        """转换到熔断状态"""
        self.state = CircuitBreakerState.OPEN
        self.last_state_change = time.time()
        print(f"[CircuitBreaker] 实例 {self.instance_id} 断路器熔断 (失败次数={self.failure_count})")

    def _transition_to_half_open(self):
        """转换到半开状态"""
        self.state = CircuitBreakerState.HALF_OPEN
        self.last_state_change = time.time()
        self._half_open_calls = 0
        self.success_count = 0
        print(f"[CircuitBreaker] 实例 {self.instance_id} 断路器进入半开状态")

    def _transition_to_closed(self):
        """转换到闭合状态"""
        self.state = CircuitBreakerState.CLOSED
        self.last_state_change = time.time()
        self.failure_count = 0
        print(f"[CircuitBreaker] 实例 {self.instance_id} 断路器恢复正常")

    def can_attempt(self) -> bool:
        """检查是否可以尝试调用"""
        now = time.time()

        if self.state == CircuitBreakerState.CLOSED:
            return True

        elif self.state == CircuitBreakerState.OPEN:
            # 检查超时是否已过
            if (now - self.last_state_change) >= self.config.timeout:
                self._transition_to_half_open()
                return True
            return False

        elif self.state == CircuitBreakerState.HALF_OPEN:
            # 半开状态限制调用次数
            return self._half_open_calls < self.config.half_open_max_calls

        return False

    def get_state(self) -> CircuitBreakerState:
        """获取当前状态"""
        return self.state


class RemoteErrorHandler:
    """远程错误处理器"""

    def __init__(self):
        """初始化错误处理器"""
        # 断路器 {instance_id: CircuitBreaker}
        self._circuit_breakers: Dict[str, CircuitBreaker] = {}

        # 错误计数 {instance_id: {error_type: count}}
        self._error_counts: Dict[str, Dict[ErrorType, int]] = {}

        # 错误历史（最近100条）
        self._error_history: list = []
        self._max_history = 100

        # 回调函数
        self._on_error: Optional[Callable] = None
        self._on_recovery: Optional[Callable] = None

    def set_error_callback(self, callback: Callable):
        """设置错误回调"""
        self._on_error = callback

    def set_recovery_callback(self, callback: Callable):
        """设置恢复回调"""
        self._on_recovery = callback

    def get_or_create_circuit_breaker(self, instance_id: str) -> CircuitBreaker:
        """获取或创建断路器"""
        if instance_id not in self._circuit_breakers:
            self._circuit_breakers[instance_id] = CircuitBreaker(instance_id)
        return self._circuit_breakers[instance_id]

    async def handle_connection_error(
        self,
        instance_id: str,
        bot_id: str,
        error: Exception
    ):
        """
        处理连接错误

        Args:
            instance_id: 实例 ID
            bot_id: Bot ID
            error: 错误
        """
        error_type = ErrorType.CONNECTION_ERROR

        # 记录错误
        self._record_error(instance_id, bot_id, error_type, str(error))

        # 更新断路器
        cb = self.get_or_create_circuit_breaker(instance_id)
        cb.record_failure(error_type)

        # 检查是否应该熔断
        if not cb.can_attempt():
            print(f"[ErrorHandler] 实例 {instance_id} 断路器已熔断，拒绝调用")
            # 通知错误
            if self._on_error:
                await self._call_error_callback(instance_id, error_type, str(error))

    async def handle_timeout(
        self,
        instance_id: str,
        bot_id: str,
        message_id: str
    ):
        """
        处理超时

        Args:
            instance_id: 实例 ID
            bot_id: Bot ID
            message_id: 消息 ID
        """
        error_type = ErrorType.TIMEOUT

        # 记录错误
        error_msg = f"Timeout: {message_id}"
        self._record_error(instance_id, bot_id, error_type, error_msg)

        # 更新断路器（超时也算失败）
        cb = self.get_or_create_circuit_breaker(instance_id)
        cb.record_failure(error_type)

    async def handle_auth_failure(
        self,
        instance_id: str,
        error: Exception
    ):
        """
        处理认证失败

        Args:
            instance_id: 实例 ID
            error: 错误
        """
        error_type = ErrorType.AUTH_FAILURE

        # 记录错误
        self._record_error(instance_id, "", error_type, str(error))

        # 认证失败通常意味着token过期，需要特殊处理
        # 暂停一段时间后重试
        print(f"[ErrorHandler] 认证失败: {instance_id}, 将暂停重试")

        # 通知错误
        if self._on_error:
            await self._call_error_callback(instance_id, error_type, str(error))

    async def handle_fs_error(
        self,
        chat_id: str,
        path: str,
        error: Exception
    ):
        """
        处理文件系统错误（优雅降级）

        Args:
            chat_id: 会话 ID
            path: 文件路径
            error: 错误
        """
        error_type = ErrorType.FS_ERROR

        # 记录错误
        error_msg = f"FS Error: chat_id={chat_id}, path={path}, error={str(error)}"
        self._record_error("", "", error_type, error_msg)

        # 文件系统错误不应该影响整体调用，只记录
        print(f"[ErrorHandler] 文件访问失败（已降级）: {error_msg}")

    async def handle_success(
        self,
        instance_id: str,
        bot_id: str
    ):
        """
        处理成功

        Args:
            instance_id: 实例 ID
            bot_id: Bot ID
        """
        # 更新断路器
        cb = self.get_or_create_circuit_breaker(instance_id)
        old_state = cb.get_state()
        cb.record_success()

        # 检查是否从熔断恢复
        new_state = cb.get_state()
        if old_state != new_state and new_state == CircuitBreakerState.CLOSED:
            print(f"[ErrorHandler] 实例 {instance_id} 从熔断恢复")

            # 通知恢复
            if self._on_recovery:
                await self._call_recovery_callback(instance_id)

    def _record_error(
        self,
        instance_id: str,
        bot_id: str,
        error_type: ErrorType,
        message: str
    ):
        """
        记录错误

        Args:
            instance_id: 实例 ID
            bot_id: Bot ID
            error_type: 错误类型
            message: 错误消息
        """
        # 更新错误计数
        if instance_id not in self._error_counts:
            self._error_counts[instance_id] = {}

        self._error_counts[instance_id][error_type] = \
            self._error_counts[instance_id].get(error_type, 0) + 1

        # 添加到历史
        error_record = ErrorRecord(
            error_type=error_type,
            message=message,
            instance_id=instance_id,
            bot_id=bot_id
        )

        self._error_history.append(error_record)

        # 限制历史大小
        if len(self._error_history) > self._max_history:
            self._error_history.pop(0)

    async def _call_error_callback(
        self,
        instance_id: str,
        error_type: ErrorType,
        message: str
    ):
        """调用错误回调"""
        if self._on_error:
            try:
                if asyncio.iscoroutinefunction(self._on_error):
                    await self._on_error(instance_id, error_type, message)
                else:
                    self._on_error(instance_id, error_type, message)
            except Exception as e:
                print(f"[ErrorHandler] 错误回调失败: {e}")

    async def _call_recovery_callback(self, instance_id: str):
        """调用恢复回调"""
        if self._on_recovery:
            try:
                if asyncio.iscoroutinefunction(self._on_recovery):
                    await self._on_recovery(instance_id)
                else:
                    self._on_recovery(instance_id)
            except Exception as e:
                print(f"[ErrorHandler] 恢复回调失败: {e}")

    def get_error_statistics(self, instance_id: str) -> dict:
        """
        获取错误统计

        Args:
            instance_id: 实例 ID

        Returns:
            错误统计
        """
        error_counts = self._error_counts.get(instance_id, {})

        return {
            "instance_id": instance_id,
            "total_errors": sum(error_counts.values()),
            "connection_errors": error_counts.get(ErrorType.CONNECTION_ERROR, 0),
            "timeouts": error_counts.get(ErrorType.TIMEOUT, 0),
            "auth_failures": error_counts.get(ErrorType.AUTH_FAILURE, 0),
            "fs_errors": error_counts.get(ErrorType.FS_ERROR, 0),
            "circuit_breaker_state": self._circuit_breakers.get(
                instance_id, CircuitBreaker(instance_id)
            ).get_state().value
        }

    def can_call_instance(self, instance_id: str) -> bool:
        """
        检查是否可以调用实例

        Args:
            instance_id: 实例 ID

        Returns:
            是否可以调用
        """
        cb = self.get_or_create_circuit_breaker(instance_id)
        return cb.can_attempt()
