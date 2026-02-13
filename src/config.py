#!/usr/bin/env python3
"""
配置模块 - 项目根目录、配置加载、路径管理
"""
import json
import os
import sys


def get_project_root():
    """获取项目根目录
    
    优先从环境变量 LARKBOT_ROOT 获取，
    其次从 config.json 中的 project_root 获取（相对于当前文件），
    默认为当前文件所在目录
    """
    # 1. 检查环境变量
    env_root = os.environ.get('LARKBOT_ROOT')
    if env_root:
        return os.path.abspath(env_root)
    
    # 2. 获取当前文件所在目录
    current_dir = os.path.dirname(os.path.abspath(__file__))
    
    # 3. 尝试读取 config.json 中的 project_root
    # 先检查当前目录，再检查父目录（兼容 src/ 包结构）
    config_path = os.path.join(current_dir, 'config.json')
    if not os.path.exists(config_path):
        config_path = os.path.join(current_dir, '..', 'config.json')
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                project_root = config.get('project_root', '.')
                # 如果是相对路径，相对于当前文件目录
                if not os.path.isabs(project_root):
                    project_root = os.path.join(current_dir, project_root)
                return os.path.abspath(project_root)
        except Exception:
            pass
    
    # 4. 默认使用当前文件所在目录
    return current_dir


# 项目根目录（全局）
PROJECT_ROOT = get_project_root()


def load_config():
    """加载 config.json 配置文件"""
    config_path = os.path.join(PROJECT_ROOT, 'config.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            return json.load(f)
    except Exception as e:
        print(f"[ERROR] 加载配置文件失败: {e}")
        sys.exit(1)


# 全局配置
CONFIG = load_config()


def get_absolute_path(relative_path):
    """将相对于项目根目录的路径转换为绝对路径
    
    Args:
        relative_path: 相对于项目根目录的路径
        
    Returns:
        str: 绝对路径
    """
    if os.path.isabs(relative_path):
        return relative_path
    return os.path.join(PROJECT_ROOT, relative_path)
