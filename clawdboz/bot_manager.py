#!/usr/bin/env python3
"""
BotManager - 多 Bot 管理器
支持注册多个 Bot，自动分配独立工作目录
"""

import json
import os
import threading
from typing import Dict, Optional


class BotManager:
    """极简 Bot 管理器"""
    
    def __init__(self, base_workplace: str = "WORKPLACE"):
        """
        初始化 BotManager
        
        Args:
            base_workplace: 基础工作目录，所有 Bot 子目录将创建在此之下
        """
        self.base_workplace = os.path.abspath(base_workplace)
        self.bots: Dict[str, object] = {}
        
        # 确保基础目录存在
        os.makedirs(self.base_workplace, exist_ok=True)
        
    def register(self, bot_id: str, app_id: str, app_secret: str, 
                 system_prompt: str = None, **kwargs) -> object:
        """
        注册新 Bot，自动分配独立工作目录
        
        Args:
            bot_id: Bot 唯一标识（如 "code-bot", "doc-bot"）
            app_id: 飞书 App ID
            app_secret: 飞书 App Secret
            system_prompt: 系统提示词（可选）
            **kwargs: 其他配置项
            
        Returns:
            Bot 实例
        """
        if bot_id in self.bots:
            raise ValueError(f"Bot '{bot_id}' 已存在")
        
        # 为每个 Bot 创建独立工作目录
        bot_work_dir = os.path.join(self.base_workplace, bot_id)
        logs_dir = os.path.join(bot_work_dir, "logs")
        
        os.makedirs(bot_work_dir, exist_ok=True)
        os.makedirs(logs_dir, exist_ok=True)
        os.makedirs(os.path.join(bot_work_dir, "user_files"), exist_ok=True)
        os.makedirs(os.path.join(bot_work_dir, "user_images"), exist_ok=True)
        os.makedirs(os.path.join(bot_work_dir, ".kimi", "skills"), exist_ok=True)
        
        # 创建 Bot 专属 config.json
        config = {
            "project_root": os.path.dirname(bot_work_dir),
            "feishu": {
                "app_id": app_id,
                "app_secret": app_secret
            },
            "paths": {
                "workplace": bot_work_dir,
                "user_images": os.path.join(bot_work_dir, "user_images"),
                "user_files": os.path.join(bot_work_dir, "user_files"),
                "mcp_config": os.path.join(bot_work_dir, ".kimi", "mcp.json"),
                "skills_dir": os.path.join(bot_work_dir, ".kimi", "skills")
            },
            "logs": {
                "debug_log": os.path.join(logs_dir, "bot_debug.log"),
                "feishu_api_log": os.path.join(logs_dir, "feishu_api.log"),
                "ops_log": os.path.join(logs_dir, "ops_check.log")
            }
        }
        
        # 添加额外的配置
        for key, value in kwargs.items():
            if key not in config:
                config[key] = value
        
        config_path = os.path.join(bot_work_dir, "config.json")
        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)
        
        # 延迟导入，避免循环导入
        from .simple_bot import Bot
        
        # 实例化 Bot（使用其工作目录）
        original_cwd = os.getcwd()
        try:
            os.chdir(bot_work_dir)
            bot = Bot(app_id=app_id, app_secret=app_secret)
            # 附加额外属性便于识别
            bot._bot_id = bot_id
            bot._work_dir = bot_work_dir
            if system_prompt:
                bot._system_prompt = system_prompt
        finally:
            os.chdir(original_cwd)
        
        self.bots[bot_id] = bot
        print(f"[BotManager] 注册 Bot '{bot_id}' @ {bot_work_dir}")
        return bot
    
    def get_bot(self, bot_id: str) -> Optional[object]:
        """获取指定 Bot 实例"""
        return self.bots.get(bot_id)
    
    def list_bots(self) -> Dict[str, str]:
        """列出所有已注册的 Bot"""
        return {bid: getattr(bot, '_work_dir', 'unknown') 
                for bid, bot in self.bots.items()}
    
    def run(self, bot_id: str = None):
        """
        启动 Bot 服务
        
        Args:
            bot_id: 指定启动某个 Bot，None 则启动第一个
        """
        if not self.bots:
            print("[BotManager] 没有注册的 Bot")
            return
        
        if bot_id:
            bot = self.bots.get(bot_id)
            if not bot:
                raise ValueError(f"Bot '{bot_id}' 不存在")
        else:
            bot = list(self.bots.values())[0]
            bot_id = getattr(bot, '_bot_id', 'default')
        
        print(f"[BotManager] 启动 Bot '{bot_id}'...")
        
        # 切换到 Bot 的工作目录
        work_dir = getattr(bot, '_work_dir', None)
        if work_dir:
            os.chdir(work_dir)
        
        # 启动 Bot（阻塞）
        bot.run()
    
    def run_all(self):
        """
        启动所有 Bot（每个 Bot 一个线程）
        注意：飞书 WebSocket 长连接可能需要独立进程
        """
        if not self.bots:
            print("[BotManager] 没有注册的 Bot")
            return
        
        threads = []
        for bot_id, bot in self.bots.items():
            def run_bot(b=bot, bid=bot_id):
                work_dir = getattr(b, '_work_dir', None)
                if work_dir:
                    os.chdir(work_dir)
                print(f"[BotManager] 启动 Bot '{bid}'...")
                try:
                    b.run(blocking=True)
                except Exception as e:
                    print(f"[BotManager] Bot '{bid}' 异常: {e}")
            
            t = threading.Thread(target=run_bot, name=f"Bot-{bot_id}", daemon=True)
            t.start()
            threads.append(t)
        
        print(f"[BotManager] 已启动 {len(threads)} 个 Bot")
        
        # 等待所有线程（实际上不会执行到这里，因为 run() 是阻塞的）
        try:
            for t in threads:
                t.join()
        except KeyboardInterrupt:
            print("\n[BotManager] 收到停止信号")
