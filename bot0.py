#!/usr/bin/env python3
"""
bot0.py - 嗑唠的宝子 Bot 启动脚本

此脚本可被 bot_manager.sh 管理。
用法:
    ./bot_manager.sh start    # 启动 Bot
    ./bot_manager.sh stop     # 停止 Bot
    ./bot_manager.sh status   # 查看状态
"""

import os
import sys

# 从环境变量或配置文件读取飞书凭证
# 优先级：环境变量 > config.json

def load_config():
    """加载配置"""
    config = {
        'app_id': os.environ.get('FEISHU_APP_ID', ''),
        'app_secret': os.environ.get('FEISHU_APP_SECRET', '')
    }
    
    # 如果环境变量未设置，尝试读取 config.json
    if not config['app_id'] or not config['app_secret']:
        try:
            import json
            config_path = os.path.join(os.path.dirname(__file__), 'config.json')
            with open(config_path, 'r') as f:
                data = json.load(f)
                config['app_id'] = data.get('feishu', {}).get('app_id', '')
                config['app_secret'] = data.get('feishu', {}).get('app_secret', '')
        except Exception:
            pass
    
    return config

if __name__ == "__main__":
    config = load_config()
    
    if not config['app_id'] or not config['app_secret']:
        print("[错误] 缺少飞书应用配置")
        print("请设置环境变量 FEISHU_APP_ID 和 FEISHU_APP_SECRET")
        print("或在 config.json 中配置 feishu.app_id 和 feishu.app_secret")
        sys.exit(1)
    
    from clawdboz import Bot
    
    bot = Bot(
        app_id=config['app_id'],
        app_secret=config['app_secret']
    )
    
    try:
        bot.run()
    except KeyboardInterrupt:
        print("\n[Bot] 正在关闭...")
        bot.stop()
