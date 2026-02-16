#!/usr/bin/env python3
"""Bot 入口模块 - 启动飞书 Bot"""
import sys
import os
import time
import ssl
import asyncio
import logging
from datetime import datetime

# 禁用 SSL 证书验证（解决自签名证书问题）
ssl._create_default_https_context = ssl._create_unverified_context

import lark_oapi as lark
from lark_oapi.ws.client import Client as WSClient, _new_ping_frame
from lark_oapi.ws.exception import ServerUnreachableException
from lark_oapi.ws.pb.pbbp2_pb2 import Frame

# Monkey-patch websockets.connect 来禁用 SSL 验证
import websockets
_original_connect = websockets.connect

async def _patched_connect(uri, **kwargs):
    # 禁用 SSL 验证
    kwargs['ssl'] = ssl._create_unverified_context()
    return await _original_connect(uri, **kwargs)

websockets.connect = _patched_connect

from .config import CONFIG, get_absolute_path
from .bot import LarkBot
from .handlers import (
    do_card_action_trigger,
    do_url_preview_get,
    do_bot_p2p_chat_entered,
    do_message_read,
)


# 确保日志目录存在
main_log_file = get_absolute_path('logs/main.log')
os.makedirs(os.path.dirname(main_log_file), exist_ok=True)

# 设置 main.log 日志
logging.basicConfig(
    level=logging.INFO,
    format='%(asctime)s [%(levelname)s] %(message)s',
    handlers=[
        logging.FileHandler(main_log_file, encoding='utf-8'),
        logging.StreamHandler(sys.stdout)
    ]
)
logger = logging.getLogger('feishu_bot')


class MonitoredWSClient(WSClient):
    """带监控的 WebSocket 客户端 - 记录连接状态并检测心跳失败"""
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self._ping_fail_count = 0
        self._max_ping_failures = 10  # 连续 10 次心跳失败触发告警
        self._is_connected = False
        self._conn_start_time = None
        self._total_reconnects = 0
        
    async def _connect(self) -> None:
        """重写连接方法，记录连接状态"""
        try:
            await super()._connect()
            self._is_connected = True
            self._conn_start_time = datetime.now()
            self._ping_fail_count = 0  # 重置失败计数
            logger.info(f"[CONNECT] WebSocket 连接成功 - conn_id: {getattr(self, '_conn_id', 'unknown')}")
        except Exception as e:
            logger.error(f"[CONNECT] WebSocket 连接失败: {e}")
            raise
    
    async def _reconnect(self):
        """重写重连方法，记录重连事件"""
        self._total_reconnects += 1
        self._is_connected = False
        logger.warning(f"[RECONNECT] 开始第 {self._total_reconnects} 次重连...")
        
        try:
            await super()._reconnect()
            logger.info(f"[RECONNECT] 重连成功")
        except ServerUnreachableException as e:
            logger.error(f"[RECONNECT] 重连失败，服务器不可达: {e}")
            raise
        except Exception as e:
            logger.error(f"[RECONNECT] 重连异常: {e}")
            raise
    
    async def _ping_loop(self):
        """重写心跳循环，添加失败计数和告警"""
        while True:
            try:
                if self._conn is not None:
                    # 构建并发送 ping 帧
                    frame = _new_ping_frame(int(self._service_id))
                    await self._write_message(frame.SerializeToString())
                    
                    # 心跳成功，重置失败计数
                    if self._ping_fail_count > 0:
                        logger.info(f"[PING] 心跳恢复成功 (之前失败 {self._ping_fail_count} 次)")
                        self._ping_fail_count = 0
                    else:
                        logger.debug(f"[PING] 心跳正常")
                else:
                    # 连接不存在，计为失败
                    self._ping_fail_count += 1
                    logger.warning(f"[PING] 连接不存在，心跳失败计数: {self._ping_fail_count}")
                    
            except Exception as e:
                self._ping_fail_count += 1
                logger.warning(f"[PING] 心跳失败 #{self._ping_fail_count}: {e}")
            
            # 检查是否达到告警阈值
            if self._ping_fail_count >= self._max_ping_failures:
                logger.error(f"[ALERT] 连续 {self._ping_fail_count} 次心跳失败！连接可能已断开")
                logger.error(f"[ALERT] 连接状态: connected={self._is_connected}, reconnects={self._total_reconnects}")
                # 这里可以添加更多告警方式（如发送飞书消息、邮件等）
            
            # 等待下次心跳
            await asyncio.sleep(self._ping_interval)
    
    def _disconnect(self):
        """重写断开连接方法"""
        if self._is_connected:
            duration = "未知"
            if self._conn_start_time:
                duration = str(datetime.now() - self._conn_start_time).split('.')[0]
            logger.warning(f"[DISCONNECT] WebSocket 连接断开，持续时长: {duration}")
            self._is_connected = False
        super()._disconnect()
    
    def get_stats(self):
        """获取连接统计信息"""
        return {
            'connected': self._is_connected,
            'ping_fail_count': self._ping_fail_count,
            'total_reconnects': self._total_reconnects,
            'conn_start_time': self._conn_start_time,
            'conn_id': getattr(self, '_conn_id', 'unknown')
        }


def main():
    """主函数"""
    logger.info("=" * 60)
    logger.info("飞书 Bot 启动")
    logger.info("=" * 60)
    
    # 从配置文件加载凭证
    feishu_config = CONFIG.get('feishu', {})
    appid = sys.argv[1] if len(sys.argv) > 1 else feishu_config.get('app_id')
    app_secret = sys.argv[2] if len(sys.argv) > 2 else feishu_config.get('app_secret')

    if not appid or not app_secret:
        logger.error("[ERROR] 缺少飞书应用配置")
        sys.exit(1)

    logger.info(f"[INIT] 应用 ID: {appid[:8]}...")
    bot = LarkBot(appid, app_secret)

    # 检查是否是测试模式
    if len(sys.argv) > 1 and sys.argv[1] == "--test-streaming":
        chat_id = sys.argv[2] if len(sys.argv) > 2 else "oc_d24a689f16656bb78b5a6b75c5a2b552"
        test_msg = sys.argv[3] if len(sys.argv) > 3 else "写一个50字的问候语"
        logger.info(f"[TEST] 开始流式测试: chat_id={chat_id}")
        bot.run_msg_script_streaming(chat_id, test_msg)
        time.sleep(15)
        logger.info("[TEST] 流式测试结束")
        sys.exit(0)

    # 创建事件处理器
    verification_token = CONFIG.get('feishu', {}).get('verification_token', '')
    encrypt_key = CONFIG.get('feishu', {}).get('encrypt_key', '')
    
    event_handler = lark.EventDispatcherHandler.builder(verification_token, encrypt_key) \
        .register_p2_im_message_receive_v1(bot.on_message) \
        .register_p2_card_action_trigger(do_card_action_trigger) \
        .register_p2_url_preview_get(do_url_preview_get) \
        .register_p2_im_chat_access_event_bot_p2p_chat_entered_v1(do_bot_p2p_chat_entered) \
        .register_p2_im_message_message_read_v1(do_message_read) \
        .build()

    # 使用带监控的 WebSocket 客户端
    logger.info("[INIT] 启动 WebSocket 连接监控 (心跳间隔: 120秒, 告警阈值: 10次)")
    cli = MonitoredWSClient(
        appid, 
        app_secret, 
        event_handler=event_handler, 
        log_level=lark.LogLevel.INFO
    )
    
    try:
        cli.start()  # 建立长连接，阻塞运行
    except KeyboardInterrupt:
        logger.info("[SHUTDOWN] 收到中断信号，正在关闭...")
        stats = cli.get_stats()
        logger.info(f"[STATS] 连接统计: {stats}")
        sys.exit(0)
    except Exception as e:
        logger.error(f"[FATAL] 运行异常: {e}")
        sys.exit(1)


def run_with_bot(bot_instance: LarkBot = None):
    """
    使用已有的 Bot 实例启动 WebSocket 连接
    
    Args:
        bot_instance: 已初始化的 LarkBot 实例（可选，默认从配置创建）
    """
    logger.info("=" * 60)
    logger.info("飞书 Bot 启动 (通过 Bot 实例)")
    logger.info("=" * 60)
    
    if bot_instance is None:
        # 从配置创建 Bot
        feishu_config = CONFIG.get('feishu', {})
        appid = feishu_config.get('app_id')
        app_secret = feishu_config.get('app_secret')
        
        if not appid or not app_secret:
            logger.error("[ERROR] 缺少飞书应用配置")
            raise ValueError("缺少飞书应用配置")
        
        bot_instance = LarkBot(appid, app_secret)
    
    # 获取 Bot 的凭证
    appid = bot_instance.app_id
    app_secret = bot_instance.app_secret
    
    logger.info(f"[INIT] 应用 ID: {appid[:8]}...")
    
    # 创建事件处理器
    verification_token = CONFIG.get('feishu', {}).get('verification_token', '')
    encrypt_key = CONFIG.get('feishu', {}).get('encrypt_key', '')
    
    event_handler = lark.EventDispatcherHandler.builder(verification_token, encrypt_key) \
        .register_p2_im_message_receive_v1(bot_instance.on_message) \
        .register_p2_card_action_trigger(do_card_action_trigger) \
        .register_p2_url_preview_get(do_url_preview_get) \
        .register_p2_im_chat_access_event_bot_p2p_chat_entered_v1(do_bot_p2p_chat_entered) \
        .register_p2_im_message_message_read_v1(do_message_read) \
        .build()
    
    # 使用带监控的 WebSocket 客户端
    logger.info("[INIT] 启动 WebSocket 连接监控 (心跳间隔: 120秒, 告警阈值: 10次)")
    cli = MonitoredWSClient(
        appid, 
        app_secret, 
        event_handler=event_handler, 
        log_level=lark.LogLevel.INFO
    )
    
    try:
        cli.start()  # 建立长连接，阻塞运行
    except KeyboardInterrupt:
        logger.info("[SHUTDOWN] 收到中断信号，正在关闭...")
        stats = cli.get_stats()
        logger.info(f"[STATS] 连接统计: {stats}")
    except Exception as e:
        logger.error(f"[FATAL] 运行异常: {e}")
        raise


if __name__ == "__main__":
    main()
