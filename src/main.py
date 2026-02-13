#!/usr/bin/env python3
"""Bot 入口模块 - 启动飞书 Bot"""
import sys
import time

import lark_oapi as lark

from .config import CONFIG
from .bot import LarkBot
from .handlers import (
    do_card_action_trigger,
    do_url_preview_get,
    do_bot_p2p_chat_entered,
    do_message_read,
)


def main():
    """主函数"""
    # 从配置文件加载凭证
    feishu_config = CONFIG.get('feishu', {})
    appid = sys.argv[1] if len(sys.argv) > 1 else feishu_config.get('app_id')
    app_secret = sys.argv[2] if len(sys.argv) > 2 else feishu_config.get('app_secret')

    if not appid or not app_secret:
        print("[ERROR] 缺少飞书应用配置")
        sys.exit(1)

    bot = LarkBot(appid, app_secret)

    # 检查是否是测试模式
    if len(sys.argv) > 1 and sys.argv[1] == "--test-streaming":
        chat_id = sys.argv[2] if len(sys.argv) > 2 else "oc_d24a689f16656bb78b5a6b75c5a2b552"
        test_msg = sys.argv[3] if len(sys.argv) > 3 else "写一个50字的问候语"
        print(f"[TEST] 开始流式测试: chat_id={chat_id}, msg='{test_msg}'")
        bot.run_msg_script_streaming(chat_id, test_msg)
        # 等待流式完成
        time.sleep(15)
        print("[TEST] 流式测试结束")
        sys.exit(0)

    # 创建事件处理器
    event_handler = lark.EventDispatcherHandler.builder("", "") \
        .register_p2_im_message_receive_v1(bot.on_message) \
        .register_p2_card_action_trigger(do_card_action_trigger) \
        .register_p2_url_preview_get(do_url_preview_get) \
        .register_p2_im_chat_access_event_bot_p2p_chat_entered_v1(do_bot_p2p_chat_entered) \
        .register_p2_im_message_message_read_v1(do_message_read) \
        .build()

    # 使用 WebSocket 长连接客户端
    cli = lark.ws.Client(appid, app_secret, event_handler=event_handler, log_level=lark.LogLevel.INFO)
    cli.start()  # 建立长连接，阻塞运行


if __name__ == "__main__":
    main()
