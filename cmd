问题现象

  Bot 启动后无法收发消息，日志显示错误：processor not found, type: p2p_chat_crea
  te。

  根本原因

  飞书在用户首次与 Bot 创建单聊会话时，会发送 im.chat.access_event.bot_p2p_chat_
  create_v1 事件。该事件与 p2p_chat_entered（用户进入已有单聊）是不同的：

  • p2p_chat_create - 用户首次创建与 Bot 的单聊会话（会话还不存在）
  • p2p_chat_entered - 用户进入已存在的单聊会话

  lark_oapi SDK 没有内置 p2p_chat_create 事件的注册方法，因此代码未处理该事件。
  当飞书发送此事件时，SDK 找不到处理器，报错 processor not found，导致后续消息处
  理失败。

  修复方案

  使用 register_p2_customized_event() 方法注册自定义事件处理器来处理 p2p_chat_cr
  eate 事件。

  修改的文件

  1. clawdboz/handlers.py - 新增处理器函数：
     def do_bot_p2p_chat_create(data):
      """机器人创建单聊事件处理（用户首次与Bot创建单聊）"""
      print(lark.JSON.marshal(data))
      chat_id = data.event.chat_id
      operator_id = data.event.operator_id
      print(f"用户创建与机器人的单聊: chat_id={chat_id}, operator_id={operator_i
     d}")
      return None
  2. clawdboz/main.py - 两处修改：
    • 导入新处理器：from .handlers import do_bot_p2p_chat_create
    • 注册事件处理器（main() 和 run_with_bot() 两个函数）：
      event_handler = lark.EventDispatcherHandler.builder(verification_token, en
      t_key) \
      .register_p2_im_message_receive_v1(bot.on_message) \
      ... \
      .register_p2_customized_event('im.chat.access_event.bot_p2p_chat_create_v1
      ', do_bot_p2p_chat_create) \
      .build()
  3. clawdboz/__init__.py - 导出新增的处理器，更新 __all__ 列表。
