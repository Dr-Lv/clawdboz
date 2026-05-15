"""
路径安全守卫
防止路径遍历攻击和非法访问
"""
import os
from pathlib import Path
from typing import Optional


class PathTraversalError(Exception):
    """路径遍历错误"""
    pass


class PathGuard:
    """路径安全守卫"""

    # 危险路径模式
    DANGEROUS_PATTERNS = [
        "..",  # 父目录
        "~",   # 家目录
    ]

    @staticmethod
    def validate_path(
        path: str,
        allowed_root: Path,
        require_absolute: bool = False
    ) -> Path:
        """
        验证路径是否安全

        Args:
            path: 要验证的路径
            allowed_root: 允许的根目录
            require_absolute: 是否要求绝对路径

        Returns:
            规范化后的安全路径

        Raises:
            PathTraversalError: 路径遍历攻击
            ValueError: 路径无效
        """
        if not path:
            raise ValueError("Path cannot be empty")

        # 检查危险模式
        for pattern in PathGuard.DANGEROUS_PATTERNS:
            if pattern in path:
                raise PathTraversalError(
                    f"Path contains dangerous pattern: {pattern}"
                )

        # 规范化路径
        normalized = os.path.normpath(path)

        # 如果是相对路径，相对于 allowed_root
        if not os.path.isabs(normalized):
            full_path = allowed_root / normalized
        else:
            full_path = Path(normalized)

        # 规范化完整路径
        full_path = full_path.resolve()

        # 确保路径在允许的根目录下
        try:
            full_path.relative_to(allowed_root.resolve())
        except ValueError:
            raise PathTraversalError(
                f"Path '{path}' is outside allowed root '{allowed_root}'"
            )

        return full_path

    @staticmethod
    def detect_path_traversal(path: str) -> bool:
        """
        检测路径遍历攻击

        Args:
            path: 要检测的路径

        Returns:
            是否包含路径遍历
        """
        # 检查常见的路径遍历模式
        traversal_patterns = [
            "../",
            "..\\",
            "%2e%2e",  # URL 编码的 ..
            "%252e",  # 双重 URL 编码
            "..%2f",
            "..%5c",
            "....//",  # 双重编码
            "....\\\\",
        ]

        path_lower = path.lower()
        for pattern in traversal_patterns:
            if pattern in path_lower:
                return True

        return False

    @staticmethod
    def normalize_path(path: str) -> str:
        """
        规范化路径

        Args:
            path: 要规范化的路径

        Returns:
            规范化后的路径
        """
        # 移除开头的斜杠
        normalized = path.lstrip("/")

        # 使用 os.path.normpath 规范化
        normalized = os.path.normpath(normalized)

        return normalized

    @staticmethod
    def safe_join(base: Path, *paths: str) -> Path:
        """
        安全地连接路径

        Args:
            base: 基础路径
            *paths: 要连接的路径部分

        Returns:
            连接后的安全路径

        Raises:
            PathTraversalError: 路径遍历攻击
        """
        result = base

        for path_part in paths:
            if PathGuard.detect_path_traversal(path_part):
                raise PathTraversalError(
                    f"Path traversal detected in: {path_part}"
                )

            result = result / path_part

        # 规范化并确保在 base 下
        result = result.resolve()
        base_resolved = base.resolve()

        try:
            result.relative_to(base_resolved)
        except ValueError:
            raise PathTraversalError(
                f"Joined path is outside base directory"
            )

        return result
