#!/usr/bin/env python3
"""
统一日志记录模块

提供统一的日志记录接口，替代分散在各处的 _log() 方法
"""
import os
import time
from typing import Optional
from pathlib import Path


class Logger:
    """统一日志记录器"""

    @staticmethod
    def log(message: str, log_file: Optional[str] = None, print_to_console: bool = True):
        """
        记录日志到文件和控制台

        Args:
            message: 日志消息
            log_file: 日志文件路径（可选）
            print_to_console: 是否打印到控制台（默认 True）
        """
        timestamp = time.strftime('%Y-%m-%d %H:%M:%S')
        log_msg = f"[{timestamp}] {message}\n"

        # 打印到控制台
        if print_to_console:
            print(log_msg.strip())

        # 写入文件
        if log_file:
            # 确保目录存在
            log_dir = os.path.dirname(log_file)
            if log_dir:
                os.makedirs(log_dir, exist_ok=True)

            with open(log_file, 'a', encoding='utf-8') as f:
                f.write(log_msg)

    @staticmethod
    def info(message: str, log_file: Optional[str] = None):
        """记录信息级别日志"""
        Logger.log(f"[INFO] {message}", log_file)

    @staticmethod
    def warning(message: str, log_file: Optional[str] = None):
        """记录警告级别日志"""
        Logger.log(f"[WARNING] {message}", log_file)

    @staticmethod
    def error(message: str, log_file: Optional[str] = None):
        """记录错误级别日志"""
        Logger.log(f"[ERROR] {message}", log_file)

    @staticmethod
    def debug(message: str, log_file: Optional[str] = None):
        """记录调试级别日志"""
        Logger.log(f"[DEBUG] {message}", log_file)


class FileLogger:
    """基于文件的日志记录器（带自动轮转）"""

    def __init__(self, log_file: str, max_size: int = 10 * 1024 * 1024):
        """
        初始化文件日志记录器

        Args:
            log_file: 日志文件路径
            max_size: 最大文件大小（字节），默认 10MB
        """
        self.log_file = log_file
        self.max_size = max_size
        self._ensure_log_dir()

    def _ensure_log_dir(self):
        """确保日志目录存在"""
        log_dir = os.path.dirname(self.log_file)
        if log_dir:
            os.makedirs(log_dir, exist_ok=True)

    def _rotate_if_needed(self):
        """如果文件过大，进行轮转"""
        if not os.path.exists(self.log_file):
            return

        if os.path.getsize(self.log_file) > self.max_size:
            # 轮转日志文件
            timestamp = time.strftime('%Y%m%d_%H%M%S')
            backup_file = f"{self.log_file}.{timestamp}"
            os.rename(self.log_file, backup_file)

    def log(self, message: str, level: str = "INFO"):
        """
        记录日志

        Args:
            message: 日志消息
            level: 日志级别
        """
        self._rotate_if_needed()
        Logger.log(f"[{level}] {message}", self.log_file)

    def info(self, message: str):
        """记录信息"""
        self.log(message, "INFO")

    def warning(self, message: str):
        """记录警告"""
        self.log(message, "WARNING")

    def error(self, message: str):
        """记录错误"""
        self.log(message, "ERROR")

    def debug(self, message: str):
        """记录调试信息"""
        self.log(message, "DEBUG")
