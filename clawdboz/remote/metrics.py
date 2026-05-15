"""
远程功能指标收集
收集和报告远程 Bot 通信的性能和可靠性指标
"""
import time
from collections import defaultdict
from typing import Dict, List, Optional
from dataclasses import dataclass, field
from enum import Enum

from clawdboz.remote.error_handler import ErrorType


class MetricType(str, Enum):
    """指标类型"""
    COUNTER = "counter"  # 计数器
    GAUGE = "gauge"  # 仪表盘
    HISTOGRAM = "histogram"  # 直方图


@dataclass
class Histogram:
    """直方图数据"""
    count: int = 0
    sum: float = 0.0
    min: float = float('inf')
    max: float = 0.0
    buckets: Dict[str, int] = field(default_factory=dict)

    def record(self, value: float):
        """记录值"""
        self.count += 1
        self.sum += value
        self.min = min(self.min, value)
        self.max = max(self.max, value)

    def get_percentile(self, percentile: float) -> float:
        """获取百分位数（简化版）"""
        if self.count == 0:
            return 0.0

        # 简化：使用平均值
        return self.sum / self.count


class RemoteMetrics:
    """远程功能指标收集器"""

    def __init__(self):
        """初始化指标收集器"""

        # 消息计数
        self.message_count = 0
        self.message_sent_count = 0
        self.message_received_count = 0

        # 错误计数
        self.error_counts: Dict[ErrorType, int] = defaultdict(int)
        self.error_counts_by_instance: Dict[str, Dict[ErrorType, int]] = defaultdict(
            lambda: defaultdict(int)
        )

        # 延迟统计
        self.latency_histogram = Histogram()
        self.latency_by_instance: Dict[str, Histogram] = defaultdict(Histogram)

        # 正常运行时间
        self.start_time = time.time()
        self.total_downtime = 0.0
        self.instance_downtime: Dict[str, float] = defaultdict(float)

        # 文件操作计数
        self.fs_operation_counts: Dict[str, int] = defaultdict(int)
        self.fs_operation_counts_by_chat: Dict[str, Dict[str, int]] = defaultdict(
            lambda: defaultdict(int)
        )

        # 实例级别指标
        self.instance_message_count: Dict[str, int] = defaultdict(int)
        self.instance_last_seen: Dict[str, float] = {}

    def record_message_sent(self, instance_id: str = ""):
        """记录发送消息"""
        self.message_count += 1
        self.message_sent_count += 1

        if instance_id:
            self.instance_message_count[instance_id] += 1
            self.instance_last_seen[instance_id] = time.time()

    def record_message_received(self, instance_id: str = ""):
        """记录接收消息"""
        self.message_count += 1
        self.message_received_count += 1

        if instance_id:
            self.instance_last_seen[instance_id] = time.time()

    def record_error(self, error_type: ErrorType, instance_id: str = ""):
        """记录错误"""
        self.error_counts[error_type] += 1

        if instance_id:
            self.error_counts_by_instance[instance_id][error_type] += 1

    def record_latency(self, latency_ms: float, instance_id: str = ""):
        """记录延迟"""
        self.latency_histogram.record(latency_ms)

        if instance_id:
            self.latency_by_instance[instance_id].record(latency_ms)

    def record_fs_operation(self, operation: str, chat_id: str = ""):
        """记录文件系统操作"""
        self.fs_operation_counts[operation] += 1

        if chat_id:
            self.fs_operation_counts_by_chat[chat_id][operation] += 1

    def record_instance_downtime(self, instance_id: str, duration: float):
        """记录实例停机时间"""
        self.instance_downtime[instance_id] += duration
        self.total_downtime += duration

    def reset_metrics(self):
        """重置所有指标"""
        self.__init__()

    def get_metrics_report(self) -> dict:
        """
        获取指标报告

        Returns:
            指标报告
        """
        now = time.time()
        uptime = now - self.start_time

        # 计算平均延迟
        avg_latency = 0.0
        if self.latency_histogram.count > 0:
            avg_latency = self.latency_histogram.get_percentile(50)

        # 计算可用性
        availability = 0.0
        if uptime > 0:
            availability = ((uptime - self.total_downtime) / uptime) * 100

        return {
            # 消息统计
            "messages": {
                "total": self.message_count,
                "sent": self.message_sent_count,
                "received": self.message_received_count
            },

            # 错误统计
            "errors": {
                "total": sum(self.error_counts.values()),
                "by_type": {
                    error_type.value: count
                    for error_type, count in self.error_counts.items()
                }
            },

            # 延迟统计
            "latency": {
                "avg_ms": round(avg_latency, 2),
                "min_ms": round(self.latency_histogram.min, 2) if self.latency_histogram.count > 0 else 0,
                "max_ms": round(self.latency_histogram.max, 2) if self.latency_histogram.count > 0 else 0,
                "count": self.latency_histogram.count
            },

            # 正常运行时间
            "uptime": {
                "total_seconds": round(uptime, 2),
                "downtime_seconds": round(self.total_downtime, 2),
                "availability_percent": round(availability, 2)
            },

            # 文件操作统计
            "fs_operations": {
                "total": sum(self.fs_operation_counts.values()),
                "by_type": dict(self.fs_operation_counts)
            },

            # 实例级别指标
            "instances": self._get_instance_metrics(),

            # 时间戳
            "generated_at": now
        }

    def _get_instance_metrics(self) -> Dict[str, dict]:
        """获取实例级别指标"""
        instance_metrics = {}

        for instance_id in list(self.instance_message_count.keys()) + list(self.instance_last_seen.keys()):
            # 计算实例延迟
            latency_hist = self.latency_by_instance.get(instance_id)
            avg_latency = 0.0
            if latency_hist and latency_hist.count > 0:
                avg_latency = latency_hist.get_percentile(50)

            # 计算实例错误
            error_counts = self.error_counts_by_instance.get(instance_id, {})

            instance_metrics[instance_id] = {
                "message_count": self.instance_message_count.get(instance_id, 0),
                "avg_latency_ms": round(avg_latency, 2),
                "error_count": sum(error_counts.values()),
                "errors_by_type": {
                    error_type.value: count
                    for error_type, count in error_counts.items()
                },
                "downtime_seconds": round(self.instance_downtime.get(instance_id, 0), 2),
                "last_seen": self.instance_last_seen.get(instance_id, 0)
            }

        return instance_metrics

    def get_latency_percentiles(self) -> dict:
        """
        获取延迟百分位数

        Returns:
            百分位数字典
        """
        return {
            "p50": round(self.latency_histogram.get_percentile(50), 2),
            "p95": round(self.latency_histogram.get_percentile(95), 2),
            "p99": round(self.latency_histogram.get_percentile(99), 2),
            "count": self.latency_histogram.count
        }

    def get_error_rate(self) -> float:
        """
        获取错误率

        Returns:
            错误率（百分比）
        """
        total = self.message_count
        errors = sum(self.error_counts.values())

        if total == 0:
            return 0.0

        return (errors / total) * 100

    def get_instance_error_rate(self, instance_id: str) -> float:
        """
        获取实例错误率

        Args:
            instance_id: 实例 ID

        Returns:
            错误率（百分比）
        """
        total = self.instance_message_count.get(instance_id, 0)
        error_counts = self.error_counts_by_instance.get(instance_id, {})
        errors = sum(error_counts.values())

        if total == 0:
            return 0.0

        return (errors / total) * 100

    def export_prometheus_metrics(self) -> str:
        """
        导出 Prometheus 格式指标

        Returns:
            Prometheus 格式字符串
        """
        lines = []

        # 消息计数
        lines.append(f"# HELP clawdboz_remote_messages_total Total number of remote messages")
        lines.append(f"# TYPE clawdboz_remote_messages_total counter")
        lines.append(f"clawdboz_remote_messages_total {self.message_count}")

        # 错误计数
        for error_type, count in self.error_counts.items():
            lines.append(f"clawdboz_remote_errors_total{{error_type=\"{error_type.value}\"}} {count}")

        # 延迟
        lines.append(f"# HELP clawdboz_remote_latency_ms Remote call latency in milliseconds")
        lines.append(f"# TYPE clawdboz_remote_latency_ms histogram")
        lines.append(f"clawdboz_remote_latency_ms_sum {self.latency_histogram.sum:.2f}")
        lines.append(f"clawdboz_remote_latency_ms_count {self.latency_histogram.count}")

        # 可用性
        now = time.time()
        uptime = now - self.start_time
        availability = ((uptime - self.total_downtime) / uptime * 100) if uptime > 0 else 0

        lines.append(f"# HELP clawdboz_remote_availability_percent Remote service availability")
        lines.append(f"# TYPE clawdboz_remote_availability_percent gauge")
        lines.append(f"clawdboz_remote_availability_percent {availability:.2f}")

        return "\n".join(lines)
