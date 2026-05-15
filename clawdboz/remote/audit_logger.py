"""
审计日志记录
记录文件访问操作用于安全审计
"""
import json
import time
from dataclasses import dataclass, field, asdict
from typing import List, Optional
from pathlib import Path
from enum import Enum


class OperationType(str, Enum):
    """操作类型"""
    LS = "ls"  # 列出目录
    READ = "read"  # 读取文件
    WRITE = "write"  # 写入文件
    MKDIR = "mkdir"  # 创建目录
    DELETE_FILE = "delete_file"  # 删除文件
    DELETE_DIR = "delete_dir"  # 删除目录


class OperationResult(str, Enum):
    """操作结果"""
    SUCCESS = "success"
    FAILED = "failed"
    UNAUTHORIZED = "unauthorized"
    NOT_FOUND = "not_found"


@dataclass
class AuditLogEntry:
    """审计日志条目"""
    timestamp: float  # 时间戳
    operation: OperationType  # 操作类型
    chat_id: str  # 会话 ID
    instance_id: str  # 实例 ID
    bot_id: str  # Bot ID
    path: str  # 文件路径
    result: OperationResult  # 操作结果
    error: Optional[str] = None  # 错误信息
    file_size: Optional[int] = None  # 文件大小（字节）
    duration_ms: Optional[float] = None  # 操作耗时（毫秒）

    def to_dict(self) -> dict:
        """转换为字典"""
        data = asdict(self)
        data['operation'] = self.operation.value
        data['result'] = self.result.value
        return data


class AuditLogger:
    """审计日志记录器"""

    def __init__(self, log_path: Optional[Path] = None):
        """
        初始化审计日志记录器

        Args:
            log_path: 日志文件路径
        """
        self.log_path = log_path or Path("WORKPLACE") / ".remote" / "audit.log"

        # 确保日志目录存在
        self.log_path.parent.mkdir(parents=True, exist_ok=True)

        # 内存中的日志缓存
        self._logs: List[AuditLogEntry] = []

    def log_operation(
        self,
        operation: OperationType,
        chat_id: str,
        path: str,
        result: OperationResult,
        instance_id: str = "",
        bot_id: str = "",
        error: Optional[str] = None,
        file_size: Optional[int] = None,
        duration_ms: Optional[float] = None
    ):
        """
        记录操作

        Args:
            operation: 操作类型
            chat_id: 会话 ID
            path: 文件路径
            result: 操作结果
            instance_id: 实例 ID
            bot_id: Bot ID
            error: 错误信息
            file_size: 文件大小
            duration_ms: 操作耗时
        """
        entry = AuditLogEntry(
            timestamp=time.time(),
            operation=operation,
            chat_id=chat_id,
            instance_id=instance_id,
            bot_id=bot_id,
            path=path,
            result=result,
            error=error,
            file_size=file_size,
            duration_ms=duration_ms
        )

        # 添加到内存缓存
        self._logs.append(entry)

        # 写入文件
        self._write_log(entry)

    def _write_log(self, entry: AuditLogEntry):
        """
        写入日志到文件

        Args:
            entry: 日志条目
        """
        try:
            with open(self.log_path, 'a', encoding='utf-8') as f:
                f.write(json.dumps(entry.to_dict(), ensure_ascii=False))
                f.write('\n')
        except Exception as e:
            print(f"[AuditLogger] 写入日志失败: {e}")

    def get_audit_log(
        self,
        chat_id: Optional[str] = None,
        operation: Optional[OperationType] = None,
        limit: int = 100
    ) -> List[dict]:
        """
        获取审计日志

        Args:
            chat_id: 过滤会话 ID
            operation: 过滤操作类型
            limit: 最大返回数量

        Returns:
            日志列表
        """
        # 从文件读取所有日志
        all_logs = []

        if self.log_path.exists():
            try:
                with open(self.log_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        try:
                            entry = json.loads(line.strip())
                            all_logs.append(entry)
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                print(f"[AuditLogger] 读取日志失败: {e}")

        # 添加内存中的日志
        for entry in self._logs:
            all_logs.append(entry.to_dict())

        # 过滤
        filtered = all_logs

        if chat_id:
            filtered = [log for log in filtered if log.get("chat_id") == chat_id]

        if operation:
            filtered = [log for log in filtered if log.get("operation") == operation.value]

        # 按时间戳倒序排序
        filtered.sort(key=lambda x: x.get("timestamp", 0), reverse=True)

        # 限制数量
        return filtered[:limit]

    def get_recent_logs(self, minutes: int = 5) -> List[dict]:
        """
        获取最近的日志

        Args:
            minutes: 最近几分钟

        Returns:
            日志列表
        """
        cutoff_time = time.time() - (minutes * 60)

        return [
            log.to_dict()
            for log in self._logs
            if log.timestamp >= cutoff_time
        ]

    def clear_old_logs(self, days: int = 7):
        """
        清理旧日志

        Args:
            days: 保留天数
        """
        cutoff_time = time.time() - (days * 86400)

        # 读取现有日志
        valid_logs = []

        if self.log_path.exists():
            try:
                with open(self.log_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        try:
                            entry = json.loads(line.strip())
                            if entry.get("timestamp", 0) >= cutoff_time:
                                valid_logs.append(entry)
                        except json.JSONDecodeError:
                            continue
            except Exception as e:
                print(f"[AuditLogger] 读取日志失败: {e}")

        # 重写文件
        try:
            with open(self.log_path, 'w', encoding='utf-8') as f:
                for entry in valid_logs:
                    f.write(json.dumps(entry, ensure_ascii=False))
                    f.write('\n')
        except Exception as e:
            print(f"[AuditLogger] 重写日志失败: {e}")

        # 清理内存缓存
        self._logs = [
            log
            for log in self._logs
            if log.timestamp >= cutoff_time
        ]
