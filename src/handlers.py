#!/usr/bin/env python3
"""事件处理器模块 - 飞书事件回调处理"""
import lark_oapi as lark


def do_card_action_trigger(data):
    """卡片回调处理"""
    print(lark.JSON.marshal(data))
    return None


def do_url_preview_get(data):
    """链接预览处理"""
    print(lark.JSON.marshal(data))
    return None


def do_bot_p2p_chat_entered(data):
    """机器人进入单聊事件处理"""
    print(lark.JSON.marshal(data))
    chat_id = data.event.chat_id
    print(f"机器人被添加到单聊: {chat_id}")
    return None


def do_message_read(data):
    """消息已读事件处理（忽略）"""
    return None
