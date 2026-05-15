#!/usr/bin/env python3
"""
Web Server Routes Package

包含所有 FastAPI 路由模块。
"""

from .internal import setup_internal_routes
from .bots import setup_bots_routes
from .sessions import setup_session_core_routes, setup_session_meta_routes
from .file import setup_file_routes
from .moments import setup_moments_routes

__all__ = [
    'setup_internal_routes',
    'setup_bots_routes',
    'setup_session_core_routes',
    'setup_session_meta_routes',
    'setup_file_routes',
    'setup_moments_routes',
]
