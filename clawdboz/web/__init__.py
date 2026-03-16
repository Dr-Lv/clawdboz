#!/usr/bin/env python3
"""
Clawdboz Web Chat - 网页聊天界面

快速开始:
    from clawdboz import BotManager
    from clawdboz.web import start_web_chat
    
    manager = BotManager()
    manager.register("bot1", "cli_xxx", "secret")
    start_web_chat(manager.bots, port=8080)
"""

from .server import WebChatServer

__all__ = ["start_web_chat", "WebChatServer"]


def start_web_chat(bots: dict, port: int = 8080, auth_token: str = None, 
                   base_workplace: str = None):
    """
    启动 Web 聊天界面
    
    Args:
        bots: {"bot_id": bot_instance, ...} 从 BotManager.bots 获取
        port: 服务端口，默认 8080
        auth_token: 访问密码，None 则自动生成随机 token
        base_workplace: 基础 workplace 目录路径（默认使用 CONFIG 中的配置）
        
    Returns:
        WebChatServer 实例
        
    Example:
        >>> from clawdboz import BotManager
        >>> from clawdboz.web import start_web_chat
        >>> manager = BotManager()
        >>> manager.register("code-bot", "cli_xxx", "xxx")
        >>> start_web_chat(manager.bots, port=8080)
        🌐 Web Chat 已启动
           URL: http://localhost:8080/static/index.html?token=xxxxx
           Token: xxxxx
    """
    server = WebChatServer(bots, port=port, auth_token=auth_token, 
                          base_workplace=base_workplace)
    server.run()
    return server
