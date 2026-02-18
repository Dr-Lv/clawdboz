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
import sys
from pathlib import Path
from typing import Optional


def get_version() -> str:
    """获取版本号"""
    try:
        from importlib.metadata import version
        return version("clawdboz")
    except Exception:
        return "2.2.0"


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
        default_bots_md = """# Agent 指令 - 嗑唠的宝子

> 本文档是嗑唠的宝子 (Clawdboz) 的系统提示词和开发规范。

## 基本信息

1. 你的名字叫 **clawdboz**，中文名称叫 **嗑唠的宝子**
2. 版本: **v2.0.0** - 模块化架构

## 开发规范

1. 调用 skills 或者 MCP 产生的中间临时文件，请放在 **WORKPLACE** 文件夹中
2. 谨慎使用删除命令，如果需要删除，**向用户询问**确认
3. 当新增功能被用户测试完，确认成功后，**git 更新版本**
"""
        try:
            with open(bots_md_path, 'w', encoding='utf-8') as f:
                f.write(default_bots_md)
            result['created'].append('.bots.md')
            if verbose:
                print(f"[INIT] 创建 Bot 规则文件: .bots.md")
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
                # 如果找不到模板，创建简化版本
                default_bot_manager = """#!/bin/bash
#
# 飞书 Bot 管理脚本
# 功能：启动、停止、重启、状态查看
#

BOT_NAME="feishu_bot"
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="/tmp/${BOT_NAME}_$(echo "$PROJECT_ROOT" | tr '/' '_').pid"

cd "$PROJECT_ROOT" || exit 1

case "$1" in
    start)
        if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
            echo "Bot 已在运行 (PID: $(cat $PID_FILE))"
            exit 1
        fi
        echo "启动 Bot..."
        nohup clawdboz run > logs/bot_output.log 2>&1 &
        echo $! > "$PID_FILE"
        echo "Bot 已启动 (PID: $!)"
        ;;
    stop)
        if [ -f "$PID_FILE" ]; then
            PID=$(cat "$PID_FILE")
            if kill -0 "$PID" 2>/dev/null; then
                echo "停止 Bot (PID: $PID)..."
                kill "$PID"
                rm -f "$PID_FILE"
                echo "Bot 已停止"
            else
                echo "Bot 未运行"
                rm -f "$PID_FILE"
            fi
        else
            echo "未找到 PID 文件，Bot 可能未运行"
        fi
        ;;
    restart)
        $0 stop
        sleep 2
        $0 start
        ;;
    status)
        if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
            echo "Bot 运行中 (PID: $(cat $PID_FILE))"
        else
            echo "Bot 未运行"
        fi
        ;;
    *)
        echo "用法: $0 {start|stop|restart|status}"
        exit 1
        ;;
esac
"""
                with open(bot_manager_path, 'w', encoding='utf-8') as f:
                    f.write(default_bot_manager)
                os.chmod(bot_manager_path, 0o755)
                result['created'].append('bot_manager.sh')
                if verbose:
                    print(f"[INIT] 创建管理脚本: bot_manager.sh")
        except Exception as e:
            result['errors'].append(f'bot_manager.sh: {e}')
    else:
        result['existing'].append('bot_manager.sh')
        if verbose:
            print(f"[INFO] 管理脚本已存在: bot_manager.sh")
    
    return result


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
    """
    target_dir = work_dir or os.getcwd()
    
    print(f"[INIT] 初始化项目: {target_dir}")
    
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
            }
        }
        
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        print(f"[INIT] 创建配置文件: config.json")
        print(f"[WARN] 请编辑 config.json，填入你的飞书应用凭证")
    else:
        print(f"[INFO] 配置文件已存在: config.json")
    
    # 创建 .kimi/mcp.json（如果不存在）
    mcp_path = os.path.join(target_dir, '.kimi', 'mcp.json')
    if not os.path.exists(mcp_path):
        mcp_config = {
            "mcpServers": {}
        }
        with open(mcp_path, 'w', encoding='utf-8') as f:
            json.dump(mcp_config, f, indent=2)
        print(f"[INIT] 创建 MCP 配置: .kimi/mcp.json")
    
    # 创建 .bots.md 和 bot_manager.sh
    ensure_bot_files(target_dir, verbose=True)
    
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
