#!/usr/bin/env python3
"""
cli.py - 命令行入口

提供 clawdboz 命令行工具:
    clawdboz run          # 启动 Bot
    clawdboz init         # 初始化项目
    clawdboz status       # 查看状态
    clawdboz --version    # 查看版本
"""

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path
from typing import Optional


def get_version() -> str:
    """获取版本号 - 从 VERSION 文件读取"""
    try:
        version_file = os.path.join(os.path.dirname(__file__), 'VERSION')
        with open(version_file, 'r') as f:
            return f.read().strip()
    except Exception:
        return "2.6.9"


def get_templates_dir() -> Path:
    """获取模板文件目录"""
    try:
        from importlib import resources
        # 尝试获取包内的 templates 目录
        with resources.files('clawdboz') as pkg_path:
            templates_dir = pkg_path / 'templates'
            if templates_dir.exists():
                return templates_dir
    except Exception:
        pass
    
    # 回退到当前文件所在目录下的 templates
    templates_dir = Path(__file__).parent / 'templates'
    if templates_dir.exists():
        return templates_dir
    
    # 最后回退到项目根目录
    return Path(__file__).parent.parent


def ensure_bot_files(target_dir: str, verbose: bool = True) -> dict:
    """
    确保 Bot 所需的文件存在，如果不存在则自动创建
    
    Args:
        target_dir: 目标目录
        verbose: 是否打印详细信息
        
    Returns:
        dict: 包含创建的文件信息
    """
    result = {
        'created': [],
        'existing': [],
        'errors': []
    }
    
    # 创建 .bots.md（如果不存在）
    bots_md_path = os.path.join(target_dir, '.bots.md')
    if not os.path.exists(bots_md_path):
        # 从模板文件复制
        templates_dir = get_templates_dir()
        template_path = templates_dir / '.bots.md'
        
        try:
            if template_path.exists():
                shutil.copy2(template_path, bots_md_path)
                result['created'].append('.bots.md')
                if verbose:
                    print(f"[INIT] 创建 Bot 规则文件: .bots.md")
            else:
                result['errors'].append('.bots.md: 模板文件不存在')
        except Exception as e:
            result['errors'].append(f'.bots.md: {e}')
    else:
        result['existing'].append('.bots.md')
        if verbose:
            print(f"[INFO] Bot 规则文件已存在: .bots.md")
    
    # 创建 bot_manager.sh（如果不存在）
    bot_manager_path = os.path.join(target_dir, 'bot_manager.sh')
    if not os.path.exists(bot_manager_path):
        # 尝试从包数据目录复制模板
        templates_dir = get_templates_dir()
        template_path = templates_dir / 'bot_manager.sh'
        
        try:
            if template_path.exists():
                shutil.copy2(template_path, bot_manager_path)
                # 设置可执行权限
                os.chmod(bot_manager_path, 0o755)
                result['created'].append('bot_manager.sh')
                if verbose:
                    print(f"[INIT] 复制管理脚本: bot_manager.sh")
            else:
                result['errors'].append('bot_manager.sh: 模板文件不存在')
        except Exception as e:
            result['errors'].append(f'bot_manager.sh: {e}')
    else:
        result['existing'].append('bot_manager.sh')
        if verbose:
            print(f"[INFO] 管理脚本已存在: bot_manager.sh")
    
    # 创建 bot0.py 启动脚本（如果不存在）
    bot0_path = os.path.join(target_dir, 'bot0.py')
    if not os.path.exists(bot0_path):
        # 从模板文件复制
        templates_dir = get_templates_dir()
        template_path = templates_dir / 'bot0.py'
        
        try:
            if template_path.exists():
                shutil.copy2(template_path, bot0_path)
                os.chmod(bot0_path, 0o755)
                result['created'].append('bot0.py')
                if verbose:
                    print(f"[INIT] 创建启动脚本: bot0.py")
            else:
                result['errors'].append('bot0.py: 模板文件不存在')
        except Exception as e:
            result['errors'].append(f'bot0.py: {e}')
    else:
        result['existing'].append('bot0.py')
        if verbose:
            print(f"[INFO] 启动脚本已存在: bot0.py")
    
    return result


def check_kimi_installation():
    """
    检测 Kimi CLI 安装和登录状态
    
    Returns:
        tuple: (installed, logged_in, kimi_bin_path)
    """
    # 1. 检查 kimi 是否安装
    kimi_bin = None
    
    # 尝试 which kimi
    try:
        result = subprocess.run(['which', 'kimi'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            kimi_bin = result.stdout.strip()
    except Exception:
        pass
    
    # 如果 which 找不到，检查常见路径
    if not kimi_bin:
        common_paths = [
            os.path.expanduser('~/.local/bin/kimi'),
            '/usr/local/bin/kimi',
            '/usr/bin/kimi',
        ]
        for path in common_paths:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                kimi_bin = path
                break
    
    if not kimi_bin:
        return False, False, None
    
    # 2. 检查 kimi 是否已登录
    # 检查 credentials 文件是否存在 access_token
    logged_in = False
    credentials_paths = [
        os.path.expanduser('~/.kimi/credentials/kimi-code.json'),
        os.path.expanduser('~/.kimi/credentials/kimi.json'),
    ]
    for cred_path in credentials_paths:
        if os.path.exists(cred_path):
            try:
                with open(cred_path, 'r', encoding='utf-8') as f:
                    creds = json.load(f)
                # 检查是否有 access_token
                if creds.get('access_token'):
                    logged_in = True
                    break
            except Exception:
                pass
    
    return True, logged_in, kimi_bin


def init_project(work_dir: Optional[str] = None):
    """
    初始化项目目录结构
    
    创建:
    - config.json
    - WORKPLACE/
    - WORKPLACE/user_images/
    - WORKPLACE/user_files/
    - .kimi/
    - logs/
    - .bots.md
    - bot_manager.sh
    - bot0.py
    """
    target_dir = work_dir or os.getcwd()
    
    print(f"[INIT] 初始化项目: {target_dir}")
    
    # 检测 Kimi CLI 状态
    kimi_installed, kimi_logged_in, kimi_bin = check_kimi_installation()
    
    if not kimi_installed:
        print(f"[WARN] 未检测到 Kimi CLI，请先安装:")
        print(f"       curl -L code.kimi.com/install.sh | bash")
        print(f"       或访问: https://platform.moonshot.cn")
    elif not kimi_logged_in:
        print(f"[WARN] Kimi CLI 已安装但未登录，请先登录:")
        print(f"       {kimi_bin} auth login")
        print(f"       或访问: https://platform.moonshot.cn")
    else:
        print(f"[OK] Kimi CLI 已安装并已登录: {kimi_bin}")
    
    # 创建目录
    dirs = [
        'WORKPLACE',
        'WORKPLACE/user_images',
        'WORKPLACE/user_files',
        '.kimi',
        'logs',
    ]
    
    for d in dirs:
        path = os.path.join(target_dir, d)
        os.makedirs(path, exist_ok=True)
        print(f"[INIT] 创建目录: {d}/")
    
    # 创建 config.json（如果不存在）
    config_path = os.path.join(target_dir, 'config.json')
    if not os.path.exists(config_path):
        config = {
            "project_root": target_dir,
            "feishu": {
                "app_id": "YOUR_APP_ID_HERE",
                "app_secret": "YOUR_APP_SECRET_HERE"
            },
            "qveris": {
                "api_key": "${QVERIS_API_KEY}"
            },
            "notification": {
                "enabled": True,
                "script": "feishu_tools/notify_feishu.py"
            },
            "python": {
                "venv": os.environ.get('VIRTUAL_ENV', '.venv'),
                "bin": sys.executable
            },
            "logs": {
                "main_log": "logs/main.log",
                "debug_log": "logs/bot_debug.log",
                "feishu_api_log": "logs/feishu_api.log",
                "ops_log": "logs/ops_check.log"
            },
            "paths": {
                "workplace": "WORKPLACE",
                "user_images": "WORKPLACE/user_images",
                "user_files": "WORKPLACE/user_files",
                "mcp_config": ".kimi/mcp.json",
                "skills_dir": ".kimi/skills"
            },
            "kimi": {
                "bin_dir": os.path.expanduser("~/.local/bin")
            },
            "start_script": "bot0.py"
        }
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        print(f"[INIT] 创建配置文件: config.json")
        print(f"[INFO] Python 路径已配置为: {sys.executable}")
        print(f"[WARN] 请编辑 config.json，填入你的飞书应用凭证")
    else:
        print(f"[INFO] 配置文件已存在: config.json")
    
    # 创建 .kimi/mcp.json（空配置，保留文件用于兼容性）
    mcp_path = os.path.join(target_dir, '.kimi', 'mcp.json')
    if not os.path.exists(mcp_path):
        with open(mcp_path, 'w', encoding='utf-8') as f:
            json.dump({}, f, indent=2)
        print(f"[INIT] 创建 MCP 配置: .kimi/mcp.json")
    
    # 复制内置 skills 到项目目录（使用白名单机制）
    # 只有通过确认的技能才会被复制
    BUILTIN_SKILLS_WHITELIST = [
        'find-skills',
        'local-memory', 
        'scheduler',
        'feishu-api-sender',  # 飞书消息/文件发送
        # 'auto-test',  # 已禁用，需要手动安装
    ]
    
    pkg_kimi_dir = os.path.join(os.path.dirname(__file__), '.kimi')
    if os.path.exists(pkg_kimi_dir):
        # 复制 skills
        pkg_skills_dir = os.path.join(pkg_kimi_dir, 'skills')
        if os.path.exists(pkg_skills_dir):
            target_skills_dir = os.path.join(target_dir, '.kimi', 'skills')
            os.makedirs(target_skills_dir, exist_ok=True)
            
            for skill_name in os.listdir(pkg_skills_dir):
                pkg_skill_path = os.path.join(pkg_skills_dir, skill_name)
                # 只在白名单中的技能才会被复制
                if skill_name not in BUILTIN_SKILLS_WHITELIST:
                    continue
                if os.path.isdir(pkg_skill_path):
                    target_skill_path = os.path.join(target_skills_dir, skill_name)
                    if not os.path.exists(target_skill_path):
                        shutil.copytree(pkg_skill_path, target_skill_path)
                        print(f"[INIT] 复制 Skill: .kimi/skills/{skill_name}/")
                    else:
                        print(f"[INFO] Skill 已存在: .kimi/skills/{skill_name}/")
    
    # 创建 .bots.md 和 bot_manager.sh
    ensure_bot_files(target_dir, verbose=True)
    
    # 更新 .bots.md 中的版本号
    bots_md_path = os.path.join(target_dir, '.bots.md')
    if os.path.exists(bots_md_path):
        try:
            with open(bots_md_path, 'r', encoding='utf-8') as f:
                content = f.read()
            # 替换版本号
            version = get_version()
            content = content.replace('v2.6.6', f'v{version}').replace('v2.6.7', f'v{version}').replace('v2.6.8', f'v{version}').replace('v2.6.9', f'v{version}')
            with open(bots_md_path, 'w', encoding='utf-8') as f:
                f.write(content)
        except Exception:
            pass
    
    print(f"[INIT] 项目初始化完成！")
    print(f"\n下一步:")
    print(f"  1. 编辑 config.json，填入飞书 App ID 和 App Secret")
    print(f"  2. 运行: clawdboz run")
    print(f"  或使用: ./bot_manager.sh start")


def run_bot(app_id: Optional[str], app_secret: Optional[str], config: Optional[str]):
    """启动 Bot"""
    from .simple_bot import Bot
    
    print("[RUN] 启动嗑唠的宝子...")
    
    try:
        bot = Bot(
            app_id=app_id,
            app_secret=app_secret,
            config_path=config
        )
        bot.run()
    except ValueError as e:
        print(f"[ERROR] {e}")
        print("\n提示: 可以通过以下方式配置:")
        print("  1. 命令行: clawdboz run --app-id xxx --app-secret xxx")
        print("  2. 配置文件: 当前目录创建 config.json")
        print("  3. 初始化: clawdboz init")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n[RUN] 已停止")
    except Exception as e:
        print(f"[ERROR] 运行失败: {e}")
        sys.exit(1)


def show_status():
    """显示状态信息"""
    print(f"嗑唠的宝子 (Clawdboz) v{get_version()}")
    print()
    
    # 检查配置文件
    if os.path.exists('config.json'):
        print("[OK] 找到配置文件: config.json")
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)
            feishu = config.get('feishu', {})
            if feishu.get('app_id') and feishu.get('app_secret'):
                if 'YOUR_' in feishu['app_id']:
                    print("[WARN] 飞书凭证未配置（仍是占位符）")
                else:
                    print(f"[OK] 飞书 App ID: {feishu['app_id'][:8]}...")
        except Exception as e:
            print(f"[ERROR] 配置文件格式错误: {e}")
    else:
        print("[WARN] 未找到配置文件: config.json")
        print("      运行 'clawdboz init' 初始化项目")
    
    # 检查目录
    dirs = ['WORKPLACE', 'logs', '.kimi']
    for d in dirs:
        if os.path.exists(d):
            print(f"[OK] 目录存在: {d}/")
        else:
            print(f"[WARN] 目录缺失: {d}/")
    
    print()
    print("可用命令:")
    print("  clawdboz run     启动 Bot")
    print("  clawdboz init    初始化项目")


def main():
    """主入口"""
    parser = argparse.ArgumentParser(
        prog='clawdboz',
        description='嗑唠的宝子 - 基于 Kimi Code CLI 的智能飞书机器人',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  clawdboz init                          # 初始化项目
  clawdboz run                           # 使用配置文件启动
  clawdboz run --app-id xxx --secret yyy # 直接传参启动
  clawdboz status                        # 查看状态
        """
    )
    
    parser.add_argument(
        '--version',
        action='version',
        version=f'%(prog)s {get_version()}'
    )
    
    subparsers = parser.add_subparsers(dest='command', help='可用命令')
    
    # init 命令
    init_parser = subparsers.add_parser(
        'init',
        help='初始化项目目录和配置文件'
    )
    init_parser.add_argument(
        '--dir',
        help='指定项目目录（默认当前目录）'
    )
    
    # run 命令
    run_parser = subparsers.add_parser(
        'run',
        help='启动 Bot'
    )
    run_parser.add_argument(
        '--app-id',
        help='飞书 App ID'
    )
    run_parser.add_argument(
        '--app-secret', '--secret',
        dest='app_secret',
        help='飞书 App Secret'
    )
    run_parser.add_argument(
        '--config', '-c',
        help='配置文件路径'
    )
    
    # status 命令
    subparsers.add_parser(
        'status',
        help='查看项目状态'
    )
    
    args = parser.parse_args()
    
    if args.command == 'init':
        init_project(args.dir)
    elif args.command == 'run':
        run_bot(args.app_id, args.app_secret, args.config)
    elif args.command == 'status':
        show_status()
    else:
        parser.print_help()


if __name__ == '__main__':
    main()
