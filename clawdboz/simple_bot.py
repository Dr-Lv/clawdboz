#!/usr/bin/env python3
"""
simple_bot.py - 简化版 Bot API

3行代码启动 Bot:
    from clawdboz import Bot
    bot = Bot(app_id="your_app_id", app_secret="your_app_secret")
    bot.run()
"""

import os
import sys
from typing import Optional, Dict, Any

from .config import load_config, get_absolute_path, PROJECT_ROOT, CONFIG as GLOBAL_CONFIG
from .bot import LarkBot


def _get_caller_script() -> str:
    """获取调用 Bot 的 Python 脚本文件名"""
    import inspect
    
    # 获取调用栈
    frame = inspect.currentframe()
    try:
        # 向上查找调用者
        # frame -> _load_configuration -> Bot.__init__ -> 用户代码
        caller_frame = frame
        depth = 0
        while caller_frame and depth < 10:
            filename = caller_frame.f_code.co_filename
            # 跳过内部文件
            basename = os.path.basename(filename)
            if basename not in ('simple_bot.py', 'cli.py', 'bot.py', 'config.py', 
                               'acp_client.py', 'handlers.py', 'main.py'):
                # 可能是用户代码
                if basename.endswith('.py'):
                    return basename
            caller_frame = caller_frame.f_back
            depth += 1
    finally:
        del frame
    
    # 默认回退
    return 'bot0.py'


def _ensure_project_files(work_dir: str, verbose: bool = False):
    """
    确保项目文件存在（.bots.md 和 bot_manager.sh）
    内部辅助函数，避免循环导入
    """
    try:
        # 尝试从 cli 导入
        from .cli import ensure_bot_files
        return ensure_bot_files(work_dir, verbose=verbose)
    except ImportError:
        # 如果导入失败，直接创建文件
        result = {'created': [], 'existing': [], 'errors': []}
        
        # 创建 .bots.md
        bots_md_path = os.path.join(work_dir, '.bots.md')
        if not os.path.exists(bots_md_path):
            default_bots_md = """# Agent 指令 - 嗑唠的宝子

> 本文档是嗑唠的宝子 (Clawdboz) 的系统提示词和开发规范。

## 基本信息

1. 你的名字叫 **clawdboz**，中文名称叫 **嗑唠的宝子**
2. 版本: **v2.0.0** - 模块化架构

## 特殊命令

用户可以通过飞书消息发送以下特殊命令：

- **`/clear`** - 清除上下文：重置 MCP 上下文、清除对话历史、清除待处理的图片/文件
- **`/compact`** - 压缩上下文：提示用户该功能需要 ACP 协议支持（当前建议使用 /clear）
- **`Ctrl-C`** / **`/stop`** / **`中断`** - 停止当前任务：中断正在执行的对话或任务

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
                    print(f"[Bot] 创建 Bot 规则文件: .bots.md")
            except Exception as e:
                result['errors'].append(f'.bots.md: {e}')
        else:
            result['existing'].append('.bots.md')
        
        # 创建简化版 bot_manager.sh
        bot_manager_path = os.path.join(work_dir, 'bot_manager.sh')
        if not os.path.exists(bot_manager_path):
            default_bot_manager = """#!/bin/bash
#
# 飞书 Bot 管理脚本
# 功能：启动、停止、重启、状态查看
#

BOT_NAME="feishu_bot"
PROJECT_ROOT="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="/tmp/${BOT_NAME}_$(echo "$PROJECT_ROOT" | tr '/' '_').pid"
CONFIG_FILE="$PROJECT_ROOT/config.json"

# 使用当前环境中的 Python（支持虚拟环境）
PYTHON_BIN="${PYTHON_BIN:-python3}"

# 从 config.json 读取启动脚本路径，默认 bot0.py
get_config() {
    python3 -c "import json; c=json.load(open('$CONFIG_FILE')); print(c$1)" 2>/dev/null
}
BOT_SCRIPT=$(get_config "['start_script']" 2>/dev/null || echo 'bot0.py')

cd "$PROJECT_ROOT" || exit 1

case "$1" in
    start)
        if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
            echo "Bot 已在运行 (PID: $(cat $PID_FILE))"
            exit 1
        fi
        
        # 检查启动脚本是否存在
        if [ ! -f "$PROJECT_ROOT/$BOT_SCRIPT" ]; then
            echo "错误: 找不到启动脚本: $BOT_SCRIPT"
            echo "请在 config.json 中配置 start_script，或创建 bot0.py"
            exit 1
        fi
        
        # 检查 Python 是否可用
        if ! command -v "$PYTHON_BIN" &> /dev/null; then
            echo "错误: Python 命令不存在: $PYTHON_BIN"
            echo "请确保 Python 已安装或在虚拟环境中运行"
            exit 1
        fi
        
        echo "启动 Bot (使用: $BOT_SCRIPT, Python: $PYTHON_BIN)..."
        nohup "$PYTHON_BIN" "$BOT_SCRIPT" > logs/bot_output.log 2>&1 &
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
        echo ""
        echo "启动脚本配置:"
        echo "  1. 默认使用 bot0.py"
        echo "  2. 或在 config.json 中配置: \"start_script\": \"my_bot.py\""
        exit 1
        ;;
esac
"""
            try:
                with open(bot_manager_path, 'w', encoding='utf-8') as f:
                    f.write(default_bot_manager)
                os.chmod(bot_manager_path, 0o755)
                result['created'].append('bot_manager.sh')
                if verbose:
                    print(f"[Bot] 创建管理脚本: bot_manager.sh")
            except Exception as e:
                result['errors'].append(f'bot_manager.sh: {e}')
        else:
            result['existing'].append('bot_manager.sh')
        
        return result


def _copy_builtin_skills(work_dir: str, verbose: bool = False):
    """
    将内置 skills 复制到用户工作目录
    让用户可以看到和自定义内置 skills
    
    Args:
        work_dir: 用户工作目录
        verbose: 是否打印详细信息
    
    Returns:
        dict: {'copied': [], 'existing': [], 'errors': []}
    """
    import shutil
    from pathlib import Path
    
    result = {'copied': [], 'existing': [], 'errors': []}
    
    try:
        # 获取包安装目录
        package_dir = Path(__file__).parent.resolve()
        builtin_skills_dir = package_dir / '.kimi' / 'skills'
        
        if not builtin_skills_dir.exists():
            if verbose:
                print(f"[Bot] 未找到内置 skills 目录: {builtin_skills_dir}")
            return result
        
        # 用户 skills 目录
        user_skills_dir = Path(work_dir) / '.kimi' / 'skills'
        
        # 遍历内置 skills
        for skill_name in os.listdir(builtin_skills_dir):
            builtin_skill_path = builtin_skills_dir / skill_name
            
            # 只处理目录
            if not builtin_skill_path.is_dir():
                continue
            
            # 检查是否有 SKILL.md
            if not (builtin_skill_path / 'SKILL.md').exists():
                continue
            
            user_skill_path = user_skills_dir / skill_name
            
            # 如果用户目录已存在同名 skill，跳过（不覆盖用户自定义的）
            if user_skill_path.exists():
                result['existing'].append(skill_name)
                if verbose:
                    print(f"[Bot] Skill 已存在（跳过）: {skill_name}")
                continue
            
            # 复制 skill 到用户目录
            try:
                shutil.copytree(builtin_skill_path, user_skill_path)
                result['copied'].append(skill_name)
                if verbose:
                    print(f"[Bot] 复制内置 Skill: {skill_name}")
            except Exception as e:
                result['errors'].append(f'{skill_name}: {e}')
                if verbose:
                    print(f"[Bot] 复制 Skill 失败: {skill_name} - {e}")
        
        if verbose and result['copied']:
            print(f"[Bot] 已复制 {len(result['copied'])} 个内置 skills 到 .kimi/skills/")
            print(f"[Bot] 你可以在这些目录中自定义 skills，修改会立即生效")
        
    except Exception as e:
        result['errors'].append(str(e))
        if verbose:
            print(f"[Bot] 复制内置 skills 失败: {e}")
    
    return result


class Bot:
    """
    嗑唠的宝子简化版 Bot 类
    
    提供简洁的 API 来创建和运行飞书 Bot。
    支持从参数、配置文件或环境变量读取配置。
    """
    
    def __init__(
        self,
        app_id: Optional[str] = None,
        app_secret: Optional[str] = None,
        config_path: Optional[str] = None,
        work_dir: Optional[str] = None,
        **kwargs
    ):
        """
        初始化 Bot
        
        Args:
            app_id: 飞书 App ID（优先于配置文件）
            app_secret: 飞书 App Secret（优先于配置文件）
            config_path: 自定义配置文件路径
            work_dir: 工作目录（默认当前目录，优先使用当前目录的 WORKPLACE）
            **kwargs: 其他配置项覆盖
        
        Example:
            # 方式1: 直接传参
            bot = Bot(app_id="cli_xxx", app_secret="xxx")
            
            # 方式2: 使用当前目录的 config.json
            bot = Bot()
            
            # 方式3: 指定工作目录
            bot = Bot(work_dir="/path/to/work_dir")
        """
        # 1. 确定工作目录优先级：
        #    传入参数 > 当前目录的 WORKPLACE > 当前目录
        cwd = os.getcwd()
        if work_dir:
            # 用户明确指定了工作目录
            self.work_dir = os.path.abspath(work_dir)
        elif os.path.exists(os.path.join(cwd, 'WORKPLACE')):
            # 当前目录有 WORKPLACE 子目录，使用当前目录
            self.work_dir = cwd
        else:
            # 默认使用当前目录
            self.work_dir = cwd
        
        # 切换到工作目录
        os.chdir(self.work_dir)
        
        # 自动创建 .bots.md 和 bot_manager.sh（如果不存在）
        _ensure_project_files(self.work_dir, verbose=True)
        
        # 加载配置
        self.config = self._load_configuration(
            app_id=app_id,
            app_secret=app_secret,
            config_path=config_path,
            **kwargs
        )
        
        # 同步飞书配置到全局 CONFIG（供 MCP server 使用）
        if self.config.get('feishu'):
            GLOBAL_CONFIG['feishu'] = self.config['feishu'].copy()
        
        # 如果配置中指定了 paths.workplace，使用配置的
        if self.config.get('paths', {}).get('workplace'):
            workplace_path = self.config['paths']['workplace']
            if not os.path.isabs(workplace_path):
                workplace_path = os.path.join(self.work_dir, workplace_path)
            # 确保 WORKPLACE 目录存在
            os.makedirs(workplace_path, exist_ok=True)
        else:
            # 默认在工作目录下创建 WORKPLACE
            workplace_path = os.path.join(self.work_dir, 'WORKPLACE')
            os.makedirs(workplace_path, exist_ok=True)
            if 'paths' not in self.config:
                self.config['paths'] = {}
            self.config['paths']['workplace'] = 'WORKPLACE'
        
        # 创建 Bot 实例
        self._bot = LarkBot(
            app_id=self.config['feishu']['app_id'],
            app_secret=self.config['feishu']['app_secret']
        )
        
    def _load_configuration(
        self,
        app_id: Optional[str],
        app_secret: Optional[str],
        config_path: Optional[str],
        **kwargs
    ) -> Dict[str, Any]:
        """加载配置，优先级: 参数 > 自定义配置 > 全局配置
        
        如果传参与 config.json 不一致，报错而不是自动更新
        """
        import json
        
        # 1. 尝试加载配置文件
        config = {}
        config_file_exists = False
        target_config_path = config_path or os.path.join(self.work_dir, 'config.json')
        
        if config_path and os.path.exists(config_path):
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            config_file_exists = True
        elif os.path.exists('config.json'):
            with open('config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
            config_file_exists = True
        else:
            # 使用全局配置（从 config.py 加载的）
            config = GLOBAL_CONFIG.copy()
        
        # 2. 检查传参与配置文件是否一致（如果传参和配置文件都存在）
        if config_file_exists and (app_id or app_secret):
            feishu_config = config.get('feishu', {})
            mismatches = []
            
            if app_id and app_id != feishu_config.get('app_id'):
                mismatches.append(f"  - app_id: config.json='{feishu_config.get('app_id')}' != 参数='{app_id}'")
            
            if app_secret and app_secret != feishu_config.get('app_secret'):
                mismatches.append(f"  - app_secret: config.json != 参数")
            
            if mismatches:
                print("[ERROR] 传入参数与 config.json 配置不一致:")
                for m in mismatches:
                    print(m)
                print("\n请检查:")
                print("  1. 修改 config.json 中的配置")
                print("  2. 或使用与 config.json 一致的参数")
                print("  3. 或删除 config.json 后重新运行")
                raise ValueError("配置不一致: 传入参数与 config.json 不匹配")
        
        # 3. 参数覆盖（仅当配置文件不存在时）
        config_updated = False
        if not config_file_exists:
            if app_id or app_secret:
                if 'feishu' not in config:
                    config['feishu'] = {}
                if app_id:
                    config['feishu']['app_id'] = app_id
                    config_updated = True
                if app_secret:
                    config['feishu']['app_secret'] = app_secret
                    config_updated = True
        
        # 4. 环境变量覆盖（非飞书配置）
        if os.environ.get('QVERIS_API_KEY'):
            config.setdefault('qveris', {})['api_key'] = os.environ['QVERIS_API_KEY']
            config_updated = True
        
        # 5. 额外参数覆盖（仅当配置文件不存在时）
        if not config_file_exists and kwargs:
            config.update(kwargs)
            config_updated = True
        
        # 6. 没有配置文件时，自动创建 config.json
        if not config_file_exists and config_updated:
            try:
                # 构建完整的默认配置
                default_config = {
                    "project_root": self.work_dir,
                    "feishu": config.get('feishu', {
                        "app_id": app_id or "YOUR_APP_ID_HERE",
                        "app_secret": app_secret or "YOUR_APP_SECRET_HERE"
                    }),
                    "qveris": config.get('qveris', {
                        "api_key": os.environ.get('QVERIS_API_KEY', "${QVERIS_API_KEY}")
                    }),
                    "logs": config.get('logs', {
                        "main_log": "logs/main.log",
                        "debug_log": "logs/bot_debug.log",
                        "feishu_api_log": "logs/feishu_api.log",
                        "ops_log": "logs/ops_check.log"
                    }),
                    "paths": {
                        "workplace": "WORKPLACE",
                        "user_images": "WORKPLACE/user_images",
                        "user_files": "WORKPLACE/user_files",
                        "mcp_config": ".kimi/mcp.json",
                        "skills_dir": ".kimi/skills"
                    },
                    "start_script": _get_caller_script()
                }
                
                # 合并用户传入的额外配置
                for key, value in kwargs.items():
                    if key not in default_config:
                        default_config[key] = value
                
                # 写入配置文件
                with open(target_config_path, 'w', encoding='utf-8') as f:
                    json.dump(default_config, f, indent=2, ensure_ascii=False)
                print(f"[Bot] 自动创建配置文件: {target_config_path}")
                print(f"[Bot] 启动脚本配置为: {default_config['start_script']}")
            except Exception as e:
                print(f"[Bot] 警告: 无法创建配置文件: {e}")
        
        # 7. 验证必要配置
        self._validate_config(config)
        
        return config
    
    def _validate_config(self, config: Dict[str, Any]):
        """验证配置是否完整"""
        errors = []
        
        feishu = config.get('feishu', {})
        if not feishu.get('app_id'):
            errors.append("缺少 feishu.app_id 配置")
        if not feishu.get('app_secret'):
            errors.append("缺少 feishu.app_secret 配置")
        
        if errors:
            print("[ERROR] 配置验证失败:")
            for error in errors:
                print(f"  - {error}")
            print("\n提示: 可以通过以下方式配置:")
            print("  1. 传参: Bot(app_id='xxx', app_secret='xxx')")
            print("  2. 配置文件: 当前目录创建 config.json")
            print("  3. 运行: clawdboz init")
            raise ValueError("配置不完整")
    
    def run(self, blocking: bool = True):
        """
        启动 Bot
        
        Args:
            blocking: 是否阻塞运行（默认 True）
        
        Example:
            bot.run()  # 阻塞运行，直到手动停止
        """
        print(f"[Bot] 启动嗑唠的宝子 v2.2.0")
        print(f"[Bot] 工作目录: {self.work_dir}")
        print(f"[Bot] App ID: {self.config['feishu']['app_id'][:10]}...")
        
        # 复制内置 skills 到用户目录
        _copy_builtin_skills(self.work_dir, verbose=True)
        
        if blocking:
            # 阻塞模式：直接启动 WebSocket 监听
            self._start_websocket()
        else:
            # 非阻塞模式：在后台线程启动
            import threading
            thread = threading.Thread(target=self._start_websocket, daemon=True)
            thread.start()
            return thread
    
    def _start_websocket(self):
        """启动 WebSocket 连接"""
        try:
            from .main import run_with_bot
            run_with_bot(self._bot)
        except KeyboardInterrupt:
            print("\n[Bot] 收到停止信号，正在关闭...")
            self.stop()
        except Exception as e:
            print(f"[Bot] 运行出错: {e}")
            raise
    
    def stop(self):
        """停止 Bot"""
        print("[Bot] 正在停止...")
        # 停止心跳线程
        self._bot._stop_heart_beat()
        # 清理资源
        self._bot.executor.shutdown(wait=True)
        print("[Bot] 已停止")
    
    def send_message(self, chat_id: str, message: str) -> bool:
        """
        发送文本消息到指定聊天
        
        Args:
            chat_id: 聊天 ID
            message: 消息内容
        
        Returns:
            是否发送成功
        """
        return self._bot.reply_text(chat_id, message)
    
    def send_message_card(self, chat_id: str, title: str, content: str) -> bool:
        """
        发送消息卡片
        
        Args:
            chat_id: 聊天 ID
            title: 卡片标题
            content: 卡片内容（支持 Markdown）
        """
        return self._bot.reply_with_card(chat_id, title, content)
    
    def get_status(self) -> Dict[str, Any]:
        """获取 Bot 状态"""
        return {
            'app_id': self.config['feishu']['app_id'][:10] + '...',
            'work_dir': self.work_dir,
            'running': True,  # TODO: 实际检测运行状态
        }


def create_bot(app_id: Optional[str] = None, app_secret: Optional[str] = None, **kwargs) -> Bot:
    """
    快速创建 Bot 的工厂函数
    
    Example:
        bot = create_bot(app_id="cli_xxx", app_secret="xxx")
        bot.run()
    """
    return Bot(app_id=app_id, app_secret=app_secret, **kwargs)
