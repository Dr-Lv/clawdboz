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


def get_project_root(use_cwd=False):
    """获取项目根目录
    
    优先级：
    1. 环境变量 LARKBOT_ROOT
    2. 当前工作目录的 WORKPLACE 子目录（如果 use_cwd=True）
    3. config.json 中的 project_root
    4. 当前工作目录（如果包含 config.json）
    5. 包所在目录
    
    Args:
        use_cwd: 是否优先使用当前工作目录的 WORKPLACE
    """
    # 1. 检查环境变量
    env_root = os.environ.get('LARKBOT_ROOT')
    if env_root:
        return os.path.abspath(env_root)
    
    # 2. 获取当前工作目录
    cwd = os.getcwd()
    
    # 3. 如果指定使用当前目录，检查 WORKPLACE 子目录
    if use_cwd:
        workplace_dir = os.path.join(cwd, 'WORKPLACE')
        if os.path.exists(workplace_dir):
            return cwd
    
    # 4. 尝试读取当前目录的 config.json
    config_path = os.path.join(cwd, 'config.json')
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                project_root = config.get('project_root', cwd)
                if not os.path.isabs(project_root):
                    project_root = os.path.join(cwd, project_root)
                return os.path.abspath(project_root)
        except Exception:
            pass
    
    # 5. 尝试读取包所在目录的 config.json
    package_dir = os.path.dirname(os.path.abspath(__file__))
    config_path = os.path.join(package_dir, 'config.json')
    if not os.path.exists(config_path):
        config_path = os.path.join(package_dir, '..', 'config.json')
    if os.path.exists(config_path):
        try:
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
                project_root = config.get('project_root', '.')
                if not os.path.isabs(project_root):
                    project_root = os.path.join(package_dir, project_root)
                return os.path.abspath(project_root)
        except Exception:
            pass
    
    # 6. 默认使用当前工作目录
    return cwd


def load_dotenv(project_root):
    """加载 .env 文件到环境变量（仅加载非飞书配置的环境变量）
    
    注意：飞书配置 (FEISHU_APP_ID, FEISHU_APP_SECRET) 只从 config.json 读取
    
    Args:
        project_root: 项目根目录路径
    """
    dotenv_path = os.path.join(project_root, '.env')
    if not os.path.exists(dotenv_path):
        return
    
    # 飞书配置关键字（这些配置只从 config.json 读取）
    feishu_keys = {'FEISHU_APP_ID', 'FEISHU_APP_SECRET'}
    
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
                    # 跳过飞书配置（只从 config.json 读取）
                    if key in feishu_keys:
                        continue
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
    """从环境变量合并配置到 config 字典（飞书配置除外）
    
    优先级：环境变量 > config.json
    注意：飞书配置 (app_id, app_secret) 只从 config.json 读取，不从环境变量合并
    
    Args:
        config: 从 config.json 加载的配置字典
        
    Returns:
        合并后的配置字典
    """
    # 注意：飞书配置 (FEISHU_APP_ID, FEISHU_APP_SECRET) 只从 config.json 读取
    # 不再从环境变量或 .env 文件覆盖，确保每个项目使用自己的独立配置
    
    # QVeris 配置（仍可从环境变量读取）
    if os.environ.get('QVERIS_API_KEY'):
        config.setdefault('qveris', {})['api_key'] = os.environ['QVERIS_API_KEY']
    
    # 通知配置（仍可从环境变量读取）
    if os.environ.get('ENABLE_FEISHU_NOTIFY'):
        enable = os.environ['ENABLE_FEISHU_NOTIFY'].lower() in ('true', '1', 'yes', 'on')
        config.setdefault('notification', {})['enabled'] = enable
    
    # 项目根目录（仍可从环境变量读取）
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


def load_config(silent=False):
    """加载配置文件并合并环境变量
    
    Args:
        silent: 如果为 True，配置文件不存在时不打印错误（用于包导入时）
    """
    config_path = os.path.join(PROJECT_ROOT, 'config.json')
    try:
        with open(config_path, 'r', encoding='utf-8') as f:
            config = json.load(f)
    except FileNotFoundError:
        if not silent:
            print(f"[WARN] 配置文件不存在: {config_path}，使用默认配置")
        # 使用默认配置
        config = {
            'feishu': {},
            'logs': {},
            'paths': {},
            'scheduler': {
                'heart_beat': 60  # 心跳间隔，单位秒，默认60秒
            }
        }
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

# 全局配置（延迟加载或使用默认配置）
try:
    CONFIG = load_config(silent=True)
except SystemExit:
    # 配置验证失败时使用空配置（后续在 Bot 初始化时再验证）
    CONFIG = {
        'feishu': {},
        'logs': {},
        'paths': {},
        'scheduler': {
            'heart_beat': 60  # 心跳间隔，单位秒，默认60秒
        }
    }


def get_absolute_path(relative_path, project_root=None):
    """将相对于项目根目录的路径转换为绝对路径
    
    Args:
        relative_path: 相对于项目根目录的路径
        project_root: 项目根目录，默认为全局 PROJECT_ROOT
        
    Returns:
        str: 绝对路径
    """
    if os.path.isabs(relative_path):
        return relative_path
    root = project_root or PROJECT_ROOT
    return os.path.join(root, relative_path)
