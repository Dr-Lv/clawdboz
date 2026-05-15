#!/usr/bin/env python3
"""
Session Routes Package

包含会话核心路由和元数据路由。
"""

from .core import setup_session_core_routes
from .meta import setup_session_meta_routes

__all__ = [
    'setup_session_core_routes',
    'setup_session_meta_routes',
]
