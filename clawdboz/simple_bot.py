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

cd "$PROJECT_ROOT" || exit 1

case "$1" in
    start)
        if [ -f "$PID_FILE" ] && kill -0 $(cat "$PID_FILE") 2>/dev/null; then
            echo "Bot 已在运行 (PID: $(cat $PID_FILE))"
            exit 1
        fi
        echo "启动 Bot..."
        nohup python3 -c "from clawdboz import Bot; bot = Bot(); bot.run()" > logs/bot_output.log 2>&1 &
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
        """加载配置，优先级: 参数 > 自定义配置 > 全局配置"""
        
        # 1. 尝试加载配置文件
        config = {}
        if config_path and os.path.exists(config_path):
            import json
            with open(config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
        elif os.path.exists('config.json'):
            import json
            with open('config.json', 'r', encoding='utf-8') as f:
                config = json.load(f)
        else:
            # 使用全局配置（从 config.py 加载的）
            config = GLOBAL_CONFIG.copy()
        
        # 2. 参数覆盖
        if app_id or app_secret:
            if 'feishu' not in config:
                config['feishu'] = {}
            if app_id:
                config['feishu']['app_id'] = app_id
            if app_secret:
                config['feishu']['app_secret'] = app_secret
        
        # 3. 环境变量覆盖（非飞书配置）
        if os.environ.get('QVERIS_API_KEY'):
            config.setdefault('qveris', {})['api_key'] = os.environ['QVERIS_API_KEY']
        
        # 4. 额外参数覆盖
        config.update(kwargs)
        
        # 5. 验证必要配置
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
