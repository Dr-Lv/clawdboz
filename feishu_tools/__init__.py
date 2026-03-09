"""飞书工具模块 - 包含通知、MCP服务器等功能"""

import os

def get_notify_script_path():
    """获取 notify_feishu.py 脚本的绝对路径"""
    return os.path.join(os.path.dirname(__file__), 'notify_feishu.py')
