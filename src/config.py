#!/usr/bin/env python3
"""
配置模块 - 项目根目录、配置加载、路径管理

支持从 config.json 和环境变量读取配置，优先级：
1. 环境变量 (os.environ)
2. .env 文件 (项目根目录下的 .env)
3. config.json 文件
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


def load_dotenv(project_root):
    """加载 .env 文件到环境变量
    
    Args:
        project_root: 项目根目录路径
    """
    dotenv_path = os.path.join(project_root, '.env')
    if not os.path.exists(dotenv_path):
        return
    
    try:
        with open(dotenv_path, 'r', encoding='utf-8') as f:
            for line in f:
                line = line.strip()
                # 跳过空行和注释
                if not line or line.startswith('#'):
                    continue
                # 解析 KEY=VALUE
                if '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip()
                    # 去除可能的引号
                    if (value.startswith('"') and value.endswith('"')) or \
                       (value.startswith("'") and value.endswith("'")):
                        value = value[1:-1]
                    # 只在环境变量不存在时才设置（环境变量优先级更高）
                    if key and key not in os.environ:
                        os.environ[key] = value
    except Exception as e:
        print(f"[WARN] 加载 .env 文件失败: {e}")


def merge_config_from_env(config):
    """从环境变量合并配置到 config 字典
    
    优先级：环境变量 > config.json
    
    Args:
        config: 从 config.json 加载的配置字典
        
    Returns:
        合并后的配置字典
    """
    # 飞书配置
    if os.environ.get('FEISHU_APP_ID'):
        config.setdefault('feishu', {})['app_id'] = os.environ['FEISHU_APP_ID']
    if os.environ.get('FEISHU_APP_SECRET'):
        config.setdefault('feishu', {})['app_secret'] = os.environ['FEISHU_APP_SECRET']
    
    # QVeris 配置
    if os.environ.get('QVERIS_API_KEY'):
        config.setdefault('qveris', {})['api_key'] = os.environ['QVERIS_API_KEY']
    
    # 通知配置
    if os.environ.get('ENABLE_FEISHU_NOTIFY'):
        enable = os.environ['ENABLE_FEISHU_NOTIFY'].lower() in ('true', '1', 'yes', 'on')
        config.setdefault('notification', {})['enabled'] = enable
    
    # 项目根目录
    if os.environ.get('LARKBOT_ROOT'):
        config['project_root'] = os.environ['LARKBOT_ROOT']
    
    return config


def validate_config(config):
    """验证配置是否完整
    
    Args:
        config: 配置字典
        
    Raises:
        SystemExit: 如果必要配置缺失
    """
    errors = []
    
    # 检查飞书配置
    feishu = config.get('feishu', {})
    if not feishu.get('app_id'):
        errors.append("缺少 feishu.app_id 配置，请设置 FEISHU_APP_ID 环境变量或在 config.json 中配置")
    if not feishu.get('app_secret'):
        errors.append("缺少 feishu.app_secret 配置，请设置 FEISHU_APP_SECRET 环境变量或在 config.json 中配置")
    
    if errors:
        print("[ERROR] 配置验证失败:")
        for error in errors:
            print(f"  - {error}")
        print("\n提示: 您可以将敏感配置写入项目根目录的 .env 文件，格式如下:")
        print("  FEISHU_APP_ID=your_app_id")
        print("  FEISHU_APP_SECRET=your_app_secret")
        print("  QVERIS_API_KEY=your_api_key (可选)")
        sys.exit(1)


def load_config():
    """加载配置文件并合并环境变量"""
    config_path = os.path.join(PROJECT_ROOT, 'config.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except Exception as e:
        print(f"[ERROR] 加载配置文件失败: {e}")
        sys.exit(1)
    
    # 从环境变量合并配置（环境变量优先级更高）
    config = merge_config_from_env(config)
    
    # 验证配置
    validate_config(config)
    
    return config


# 项目根目录（全局）
PROJECT_ROOT = get_project_root()

# 加载 .env 文件（如果有）
load_dotenv(PROJECT_ROOT)

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
