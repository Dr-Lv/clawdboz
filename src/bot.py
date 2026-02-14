#!/usr/bin/env python3
"""Bot 核心模块 - LarkBot 主类"""

import json
import os
import re
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import lark_oapi as lark
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody

from .config import CONFIG, get_absolute_path
from .acp_client import ACPClient


class LarkBot:
    """飞书 Bot 核心类"""

    def __init__(self, app_id, app_secret):
        self.app_id = app_id
        self.app_secret = app_secret
        self.client = lark.Client.builder() \
            .app_id(app_id) \
            .app_secret(app_secret) \
            .log_level(lark.LogLevel.INFO) \
            .build()
        self.processed_messages = set()  # 用于去重已处理的消息
        self.acp_client = None  # ACP 客户端（延迟初始化）
        # 创建线程池用于异步处理（增加worker数量）
        self.executor = ThreadPoolExecutor(max_workers=8, thread_name_prefix="acp_worker")
        # 批量更新相关
        self._pending_updates = {}  # 待更新的内容 {message_id: text}
        self._update_timers = {}  # 更新定时器 {message_id: timer}
        self._update_lock = threading.Lock()  # 更新锁
        self._update_counts = {}  # 每个消息的更新计数 {message_id: count}
        self._completed_messages = set()  # 已完成生成的消息ID
        self._pending_image = {}  # 待处理的图片 {chat_id: image_path}
        self._pending_file = {}  # 待处理的文件 {chat_id: file_path}
        # Bot 的 user_id（用于精确检测 @）
        self._bot_user_id = None
        # 日志文件路径（使用 PROJECT_ROOT）
        self.log_file = get_absolute_path(CONFIG.get('logs', {}).get('debug_log', 'logs/bot_debug.log'))
        # 飞书 API 调用日志
        self.feishu_log_file = get_absolute_path(CONFIG.get('logs', {}).get('feishu_api_log', 'logs/feishu_api.log'))
        # 清空旧日志
        with open(self.log_file, 'w') as f:
            f.write(f"=== Bot started at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        with open(self.feishu_log_file, 'w') as f:
            f.write(f"=== Feishu API Log started at {time.strftime('%Y-%m-%d %H:%M:%S')} ===\n")
        # 获取 Bot 的 user_id
        self._fetch_bot_user_id()

    def _log(self, message):
        """写入日志到文件"""
        timestamp = time.strftime('%H:%M:%S')
        with open(self.log_file, 'a') as f:
            f.write(f"[{timestamp}] {message}\n")
            f.flush()
        # 同时输出到控制台（会被重定向到 log 文件）
        print(message)

    def _fetch_bot_user_id(self):
        """获取 Bot 的 user_id，用于精确检测 @"""
        # 暂时使用应用 ID 作为标识（飞书通常使用 open_id）
        # 实际会在收到第一条消息时从 mentions 中提取
        self._bot_user_id = None
        self._log(f"[DEBUG] Bot user_id 将在收到消息时动态检测")

    def _log_feishu(self, direction, content, extra=""):
        """记录飞书 API 调用日志
        direction: 'SEND' 或 'RECV'
        content: 发送/接收的内容
        extra: 额外信息（如响应时间、错误码等）
        """
        timestamp = time.strftime('%H:%M:%S.%f')[:-3]  # 包含毫秒
        direction_str = "[SEND]" if direction == "SEND" else "[RECV]"
        
        with open(self.feishu_log_file, 'a') as f:
            f.write(f"[{timestamp}] {direction_str} {extra}\n")
            # 截断过长的内容，但保留足够信息用于调试
            content_str = str(content)
            if len(content_str) > 500:
                content_str = content_str[:250] + " ... [truncated] ... " + content_str[-100:]
            f.write(f"  Content: {content_str}\n")
            f.write("-" * 80 + "\n")
            f.flush()

    def _get_chat_history(self, chat_id: str, limit: int = 30) -> list:
        """获取最近聊天记录（最近7天内）"""
        try:
            from lark_oapi.api.im.v1 import ListMessageRequest
            
            self._log(f"[DEBUG] 开始获取聊天记录: chat_id={chat_id}, limit={limit}")
            
            # 计算7天前的时间戳（毫秒）用于过滤
            import time
            days_ago = int((time.time() - 7 * 24 * 60 * 60) * 1000)
            
            # 请求消息列表 - 需要分页获取最新消息
            # 注意：飞书 API 的 page_size 最大值为 50
            # API 返回的消息是从旧到新，需要获取最后一页才能得到最新消息
            all_items = []
            page_token = None
            max_pages = 10  # 最多获取10页，确保拿到最新消息
            
            for page in range(max_pages):
                builder = ListMessageRequest.builder() \
                    .container_id_type("chat") \
                    .container_id(chat_id) \
                    .page_size(50)
                
                if page_token:
                    builder = builder.page_token(page_token)
                
                request = builder.build()
                self._log(f"[DEBUG] 发送 ListMessageRequest (page {page + 1})...")
                response = self.client.im.v1.message.list(request)
                
                if not response.success():
                    self._log(f"[ERROR] 获取聊天记录失败: {response.code} - {response.msg}")
                    break
                
                items = response.data.items if response.data else []
                self._log(f"[DEBUG] API 返回 {len(items)} 条消息 (page {page + 1})")
                
                all_items.extend(items)
                
                # 检查是否有更多页
                has_more = response.data.has_more if hasattr(response.data, 'has_more') else False
                page_token = response.data.page_token if hasattr(response.data, 'page_token') else None
                
                if not has_more or not page_token:
                    break
            
            self._log(f"[DEBUG] 总共获取 {len(all_items)} 条消息")
            
            items = all_items
            
            # 按时间戳降序排序（最新的在前）
            items = sorted(items, key=lambda x: int(getattr(x, 'create_time', 0) or 0), reverse=True)
            
            # 过滤最近7天内的消息
            recent_items = []
            for item in items:
                create_time = int(getattr(item, 'create_time', 0) or 0)
                if create_time >= days_ago:
                    recent_items.append(item)
            
            self._log(f"[DEBUG] 最近7天内的消息: {len(recent_items)} 条")
            
            # 获取足够多的消息来解析出有效的 limit 条
            # 因为前面可能有 @标记/空消息，需要多取一些
            fetch_limit = min(limit * 3, len(recent_items))
            recent_items = recent_items[:fetch_limit]
            
            self._log(f"[DEBUG] 取最新 {len(recent_items)} 条消息进行解析")
            
            history = []
            for idx, item in enumerate(recent_items):
                try:
                    # 获取 sender（使用 id 属性）
                    sender = item.sender.id if item.sender and hasattr(item.sender, 'id') else "unknown"
                    content = json.loads(item.body.content) if item.body else {}
                    text = content.get('text', '')
                    msg_type = getattr(item, 'msg_type', 'unknown')
                    
                    # 如果是卡片消息（interactive），尝试提取文本内容
                    if not text and msg_type == 'interactive':
                        elements = content.get('elements', [])
                        texts = []
                        has_image = False
                        for element_list in elements:
                            if isinstance(element_list, list):
                                for elem in element_list:
                                    if isinstance(elem, dict):
                                        if elem.get('tag') == 'text':
                                            texts.append(elem.get('text', ''))
                                        elif elem.get('tag') == 'img':
                                            has_image = True
                        text = ''.join(texts)
                        
                        # 如果是图片卡片且只有占位文本，标记为[图片回复]
                        if has_image and ('请升级至最新版本' in text or '查看内容' in text):
                            text = "[图片/卡片回复]"
                        
                        if text:
                            self._log(f"[DEBUG] 消息 {idx} 是卡片，提取文本: {text[:50]}...")
                    
                    # 跳过空文本
                    if not text:
                        self._log(f"[DEBUG] 消息 {idx} 文本为空，跳过 (type={msg_type})")
                        continue
                    
                    # 跳过纯 @ 标记（如 @_user_1）
                    if text.strip() == '@_user_1' or text.strip().startswith('@_user_1'):
                        self._log(f"[DEBUG] 消息 {idx} 是纯 @ 标记，跳过: {text}")
                        continue
                    
                    # 如果消息太长（超过100字），截取最后100字
                    if len(text) > 100:
                        text = "..." + text[-100:]
                    history.append(f"{sender}: {text}")
                except Exception as e:
                    self._log(f"[DEBUG] 处理消息 {idx} 出错: {e}")
                    continue
            
            # 限制返回数量，并按时间正序排列（旧的在前面，方便上下文理解）
            history = history[:limit]
            history.reverse()
            
            self._log(f"[DEBUG] 成功解析 {len(history)} 条聊天记录（最近7天内最新的 {limit} 条）")
            return history
        except Exception as e:
            self._log(f"[ERROR] 获取聊天记录异常: {e}")
            import traceback
            self._log(f"[ERROR] 异常详情: {traceback.format_exc()}")
            return []

    def on_message(self, data: lark.im.v1.P2ImMessageReceiveV1):
        """处理收到的消息（支持文本、图片、文件）"""
        # 最开始的日志，确保任何消息进入都能被记录
        print(f"[ON_MESSAGE] 收到消息事件")
        try:
            msg_content = data.event.message.content
            chat_id = data.event.message.chat_id
            message_id = data.event.message.message_id
            msg_type = data.event.message.message_type
            
            # 获取聊天类型和 @ 信息
            # 飞书消息中可能没有 chat_type 字段，需要通过其他方式判断
            chat_type = getattr(data.event.message, 'chat_type', None)
            
            # 基于 chat_id 格式辅助判断：oc_ 开头的通常是群聊
            # 注意：这不是 100% 可靠，但可以作为参考
            # 飞书群聊 chat_id 可能以 'oc_' 或其他格式开头
            chat_id_looks_like_group = chat_id.startswith('oc_') if chat_id else False
            self._log(f"[DEBUG] chat_id 格式检查: chat_id={chat_id}, 以'oc_'开头={chat_id.startswith('oc_') if chat_id else False}")
            
            # 如果没有 chat_type，尝试从消息结构判断
            if chat_type is None:
                # 默认根据 chat_id 格式判断：oc_ 开头认为是群聊
                if chat_id_looks_like_group:
                    chat_type = 'group'
                else:
                    chat_type = 'p2p'  # 默认单聊更安全（不会误回复群聊）
            
            # 额外检查：如果 chat_type 不是预期的值，但 chat_id 是 oc_ 开头，强制认为是群聊
            # 这可以防止飞书返回意外的 chat_type 值
            if chat_type not in ['group', 'p2p'] and chat_id_looks_like_group:
                self._log(f"[DEBUG] chat_type='{chat_type}' 不是预期值，但 chat_id='{chat_id}' 是群聊格式，强制设为 group")
                chat_type = 'group'
            
            self._log(f"[DEBUG] 收到消息, type: {msg_type}, chat_type={chat_type!r}({type(chat_type).__name__}), chat_id={chat_id}, message_id={message_id}")
            self._log(f"[DEBUG] chat_id_looks_like_group={chat_id_looks_like_group}, chat_id 前3字符='{chat_id[:3] if chat_id else 'N/A'}'")
            
            # 打印完整的消息内容用于调试
            try:
                self._log(f"[DEBUG] 消息原始内容: {msg_content[:200]}")
            except:
                pass

            # 去重：如果消息已处理过，直接返回
            if message_id in self.processed_messages:
                self._log(f"[DEBUG] 消息 {message_id} 已处理过，跳过")
                return

            # 标记消息为已处理
            self.processed_messages.add(message_id)
            
            # 检查是否是群聊
            is_group = chat_type == 'group'
            
            # 检查是否被 @
            # 方法1: 通过消息中的 mentions 字段（如果有的话）
            # 方法2: 通过消息内容中的 <at> 标签
            current_text = ""
            is_mentioned = False
            
            # 首先尝试从 mentions 字段检测
            mentions = getattr(data.event.message, 'mentions', None)
            if mentions:
                self._log(f"[DEBUG] 消息包含 mentions 字段: {len(mentions)} 个, type={type(mentions)}")
                # 打印原始 mentions 数据用于调试
                try:
                    mentions_str = str(mentions)
                    self._log(f"[DEBUG] mentions 原始数据: {mentions_str[:500]}")
                except:
                    pass
                for i, mention in enumerate(mentions):
                    mention_id_obj = getattr(mention, 'id', None)
                    mention_type = getattr(mention, 'type', None)
                    mention_name = getattr(mention, 'name', None)
                    # mention.id 可能是 UserId 对象，提取实际 ID
                    mention_id = None
                    if mention_id_obj:
                        if hasattr(mention_id_obj, 'open_id'):
                            mention_id = mention_id_obj.open_id
                        elif hasattr(mention_id_obj, 'user_id'):
                            mention_id = mention_id_obj.user_id
                        else:
                            mention_id = str(mention_id_obj)
                    self._log(f"[DEBUG] mention[{i}]: id={mention_id}, type={mention_type}, name={mention_name}")
                    # 如果是第一次检测到 app 类型，保存为 Bot 的 user_id
                    if mention_type == 'app' and mention_id and not self._bot_user_id:
                        self._bot_user_id = mention_id
                        self._log(f"[DEBUG] 发现 Bot user_id: {self._bot_user_id}")
                    # 检查是否 @ 了 Bot（如果已知 user_id）或只要是 app 类型就认为是 Bot
                    if mention_id and (mention_id == self._bot_user_id or mention_type == 'app'):
                        is_mentioned = True
                        self._log(f"[DEBUG] mentions 中检测到 @ Bot")
            
            # 然后通过消息内容检测（备用方法）
            if msg_type == 'text':
                try:
                    content_dict = json.loads(msg_content)
                    current_text = content_dict.get('text', '')
                    self._log(f"[DEBUG] 消息文本内容: {current_text[:100]}")
                    
                    # 如果还没检测到 @，继续检测
                    if not is_mentioned:
                        # 飞书中 @ 某人时可能有多种格式：
                        # 1. <at id="user_id"></at> 或 <at id="user_id">@username</at>
                        # 2. @_user_1 (纯文本格式)
                        if '<at' in current_text and '</at>' in current_text:
                            # 提取所有 @ 的 user_id
                            at_ids = re.findall(r'<at[^>]+id=["\']([^"\']+)["\'][^>]*>', current_text)
                            self._log(f"[DEBUG] 消息中 <at> 标签的用户: {at_ids}")
                            
                            # 如果已知 Bot 的 user_id，精确匹配
                            if self._bot_user_id:
                                if self._bot_user_id in at_ids:
                                    is_mentioned = True
                                    self._log(f"[DEBUG] 检测到 @ Bot (id={self._bot_user_id})")
                                else:
                                    self._log(f"[DEBUG] 检测到 @ 其他人，不是 @ Bot")
                            else:
                                # 如果不知道 Bot 的 user_id，但只有一个 @，假设是 @ Bot
                                if len(at_ids) == 1:
                                    self._bot_user_id = at_ids[0]
                                    is_mentioned = True
                                    self._log(f"[DEBUG] 假设 @ 的是 Bot，设置 user_id={self._bot_user_id}")
                                else:
                                    # 多个 @，无法确定哪个是 Bot，保守处理（认为是被 @）
                                    is_mentioned = True
                                    self._log(f"[DEBUG] 多个 @，保守认为是 @ Bot")
                        elif '@_user_' in current_text:
                            # 纯文本格式的 @ (如 @_user_1)
                            # 如果消息中有 @_user_ 且 mentions 字段存在，认为是 @ Bot
                            if mentions:
                                is_mentioned = True
                                self._log(f"[DEBUG] 检测到纯文本 @ 且 mentions 存在，认为是 @ Bot")
                except Exception as e:
                    self._log(f"[DEBUG] 解析消息内容异常: {e}")
            
            # 如果不是群聊（单聊），正常回复
            # 如果是群聊，只有被 @ 时才回复
            if is_group and not is_mentioned:
                self._log(f"[DEBUG] ❌ 群聊消息但未 @，不回复 (chat_type={chat_type}, text={current_text[:50]})")
                return
            
            self._log(f"[DEBUG] ✅ 需要回复消息 (is_group={is_group}, is_mentioned={is_mentioned}, chat_type={chat_type})")

            # 更新 MCP 上下文文件，让 MCP Server 知道当前聊天的 chat_id 和 chat_type
            try:
                context_dir = get_absolute_path(CONFIG.get('paths', {}).get('workplace', 'WORKPLACE'))
                os.makedirs(context_dir, exist_ok=True)
                context_file = os.path.join(context_dir, 'mcp_context.json')
                with open(context_file, 'w') as f:
                    json.dump({'chat_id': chat_id, 'chat_type': chat_type, 'timestamp': time.time()}, f)
                self._log(f"[DEBUG] 更新 MCP 上下文: chat_id={chat_id}, chat_type={chat_type}")
            except Exception as e:
                self._log(f"[ERROR] 更新 MCP 上下文失败: {e}")

            # 获取最近聊天记录作为上下文
            chat_history = []
            if is_group:
                self._log(f"[DEBUG] 获取群聊最近 30 条聊天记录...")
                chat_history = self._get_chat_history(chat_id, limit=30)
                self._log(f"[DEBUG] 获取到 {len(chat_history)} 条聊天记录")
            
            # 构建上下文提示
            context_prompt = ""
            if chat_history:
                context_prompt = "以下是最近聊天记录上下文：\n\n" + "\n".join(chat_history[-30:]) + "\n\n"

            # 根据消息类型处理
            if msg_type == 'text':
                text = current_text
                
                # 构建最终提示词
                final_prompt = context_prompt + f"用户当前消息：{text}\n\n请基于上下文回复用户的消息。"
                
                # 日志打印发送给 ACP 的完整信息（群聊时）
                self._log(f"[DEBUG] 检查日志打印条件: is_group={is_group}, chat_type={chat_type!r}")
                if is_group:
                    self._log(f"[DEBUG] ===== 发送给 ACP 的完整信息 =====")
                    self._log(f"[DEBUG] 上下文长度: {len(context_prompt)} 字符")
                    self._log(f"[DEBUG] 完整提示词:\n{final_prompt[:500]}{'...' if len(final_prompt) > 500 else ''}")
                    self._log(f"[DEBUG] ===== 结束 =====")
                else:
                    self._log(f"[DEBUG] 不是群聊，跳过日志打印")
                
                # 检查是否有待处理的图片或文件
                if chat_id in self._pending_image:
                    image_path = self._pending_image[chat_id]
                    if os.path.exists(image_path):
                        combined_prompt = f"{context_prompt}用户发送了一张图片，路径为: {image_path}\n\n用户对该图片的指令: {text}\n\n请根据用户的指令分析处理这张图片。"
                        self._log(f"[DEBUG] 将图片和消息一起发送给 Kimi: {image_path}, 消息: {text[:50]}...")
                        # 日志打印发送给 ACP 的完整信息（群聊时）
                        if is_group:
                            self._log(f"[DEBUG] ===== 发送给 ACP 的完整信息（图片） =====")
                            self._log(f"[DEBUG] 上下文长度: {len(context_prompt)} 字符")
                            self._log(f"[DEBUG] 完整提示词:\n{combined_prompt[:500]}{'...' if len(combined_prompt) > 500 else ''}")
                            self._log(f"[DEBUG] ===== 结束 =====")
                        self.executor.submit(self.run_msg_script_streaming, chat_id, combined_prompt)
                        del self._pending_image[chat_id]
                    else:
                        del self._pending_image[chat_id]
                        self.executor.submit(self.run_msg_script_streaming, chat_id, final_prompt)
                elif chat_id in self._pending_file:
                    file_path = self._pending_file[chat_id]
                    if os.path.exists(file_path):
                        combined_prompt = f"{context_prompt}用户发送了一个文件，路径为: {file_path}\n\n用户对该文件的指令: {text}\n\n请根据用户的指令分析处理这个文件。"
                        self._log(f"[DEBUG] 将文件和消息一起发送给 Kimi: {file_path}, 消息: {text[:50]}...")
                        # 日志打印发送给 ACP 的完整信息（群聊时）
                        if is_group:
                            self._log(f"[DEBUG] ===== 发送给 ACP 的完整信息（文件） =====")
                            self._log(f"[DEBUG] 上下文长度: {len(context_prompt)} 字符")
                            self._log(f"[DEBUG] 完整提示词:\n{combined_prompt[:500]}{'...' if len(combined_prompt) > 500 else ''}")
                            self._log(f"[DEBUG] ===== 结束 =====")
                        self.executor.submit(self.run_msg_script_streaming, chat_id, combined_prompt)
                        del self._pending_file[chat_id]
                    else:
                        del self._pending_file[chat_id]
                        self.executor.submit(self.run_msg_script_streaming, chat_id, final_prompt)
                else:
                    self.executor.submit(self.run_msg_script_streaming, chat_id, final_prompt)
            elif msg_type == 'image':
                content_dict = json.loads(msg_content)
                image_key = content_dict.get('image_key', '')
                if image_key:
                    self.executor.submit(self._handle_image_message, chat_id, image_key, message_id)
                else:
                    self.reply_text(chat_id, "❌ 无法获取图片内容", streaming=False)
            elif msg_type == 'file':
                content_dict = json.loads(msg_content)
                file_key = content_dict.get('file_key', '')
                file_name = content_dict.get('file_name', 'unknown')
                if file_key:
                    self.executor.submit(self._handle_file_message, chat_id, file_key, file_name, message_id)
                else:
                    self.reply_text(chat_id, "❌ 无法获取文件内容", streaming=False)
            else:
                self._log(f"[DEBUG] 暂不处理的消息类型: {msg_type}")
                self.reply_text(chat_id, f"⚠️ 暂不支持 {msg_type} 类型的消息", streaming=False)
        except Exception as e:
            self._log(f"[ERROR] on_message 处理异常: {e}")
            import traceback
            self._log(traceback.format_exc())

    def run_msg_script_streaming(self, chat_id, text):
        """使用 ACP 协议调用 Kimi Code CLI（流式输出）"""
        try:
            # 延迟初始化 ACP 客户端（传递 self 引用）
            if self.acp_client is None:
                self._log("[DEBUG] 初始化 ACP 客户端...")
                self.acp_client = ACPClient(bot_ref=self)

            self._log(f"[DEBUG] 调用 ACP: {text[:50]}...")
            self._log(f"[DEBUG] 传入 ACP 的完整提示词长度: {len(text)} 字符")
            self._log(f"[DEBUG] 传入 ACP 的完整提示词前 1000 字:\n{text[:1000]}{'...' if len(text) > 1000 else ''}")

            # 先发送占位消息（卡片格式）
            initial_message_id = self.reply_text(chat_id, "⏳ 正在思考...", streaming=True)
            if not initial_message_id:
                self._log("[ERROR] 发送占位消息失败")
                return

            # 用于控制更新频率
            last_update_time = [time.time()]
            last_content = [""]  # 记录上次更新的内容
            first_update = [True]  # 是否是第一次更新
            is_completed = [False]  # 是否已完成
            
            # 等待动画符号列表
            waiting_symbols = ["◐", "◯", "◑", "●"]
            symbol_index = [0]
            
            # 动画定时器
            animation_timer = [None]
            
            def get_waiting_symbol():
                """获取当前等待符号并更新索引"""
                symbol = waiting_symbols[symbol_index[0] % len(waiting_symbols)]
                symbol_index[0] += 1
                return symbol
            
            def update_animation():
                """独立更新动画符号，每0.3秒执行一次"""
                if is_completed[0]:
                    return
                
                # 无条件更新动画符号（定时器本身就是每0.3秒触发）
                current_text = last_content[0] if last_content[0] else "⏳ 正在思考..."
                display_text = current_text + f"\n\n{get_waiting_symbol()} **生成中...**"
                self.executor.submit(self.update_card, initial_message_id, display_text)
                
                # 安排下一次更新
                if not is_completed[0]:
                    animation_timer[0] = threading.Timer(0.3, update_animation)
                    animation_timer[0].start()
            
            # 立即显示第一帧动画（不要等待定时器）
            update_animation()
            
            def on_chunk(current_text):
                """收到新的文本块时的回调 - 仅更新内容"""
                if is_completed[0]:
                    return
                
                # 仅更新内容（动画定时器会负责每0.3秒更新一次卡片）
                if current_text != last_content[0]:
                    last_content[0] = current_text
            
            def on_chunk_final(final_text):
                """最终回调 - 立即去掉动画"""
                # 标记已完成，阻止 on_chunk 继续更新
                is_completed[0] = True
                
                # 停止动画定时器
                if animation_timer[0]:
                    try:
                        animation_timer[0].cancel()
                    except:
                        pass
                
                # 等待一小段时间，确保线程池中的动画更新完成
                time.sleep(0.1)
                
                # 标记消息为已完成（用于 _do_update_card 过滤）
                with self._update_lock:
                    self._completed_messages.add(initial_message_id)
                    # 取消所有待处理的定时器
                    if initial_message_id in self._update_timers:
                        try:
                            self._update_timers[initial_message_id].cancel()
                        except:
                            pass
                        del self._update_timers[initial_message_id]
                    # 清空待更新内容
                    self._pending_updates[initial_message_id] = ""
                
                # 等待一小段时间，确保已提交的动画更新完成
                time.sleep(0.2)
                # 立即更新卡片，去掉生成中字样
                self._do_update_card_now(initial_message_id, final_text)

            # 调用 ACP（流式，超时 5 分钟）
            response = self.acp_client.chat(text, on_chunk=on_chunk, timeout=300)

            # 使用最终回调更新完整回复，确保去掉生成中字样
            self._log(f"[DEBUG] 最终更新卡片，长度: {len(response)}")
            on_chunk_final(response)

            self._log(f"[DEBUG] ACP 完成，总长度: {len(response)}")

        except Exception as e:
            import traceback
            traceback.print_exc()
            error_msg = f"调用 ACP 出错: {str(e)}"
            self._log(f"[ERROR] {error_msg}")
            self.reply_text(chat_id, error_msg, streaming=False)

    def reply_text(self, chat_id, text, streaming=False, use_card=True):
        """发送消息（支持纯文本或卡片格式）
        
        Args:
            chat_id: 聊天 ID
            text: 消息内容
            streaming: 是否是流式消息
            use_card: 是否使用卡片格式（False 则发送纯文本）
        """
        text_length = len(text)

        # 记录发送给飞书的消息
        self._log_feishu("SEND", {
            "type": "CREATE_MESSAGE",
            "chat_id": chat_id,
            "text_length": text_length,
            "text_preview": text[:200] if len(text) > 200 else text
        }, f"streaming={streaming}, use_card={use_card}")
        
        if use_card:
            # 构建新版消息卡片内容 (V2)
            card_content = self._build_v2_card_content(text)
            msg_type_str = "interactive"
            content_str = json.dumps(card_content)
        else:
            # 发送纯文本
            msg_type_str = "text"
            content_str = json.dumps({"text": text})
        
        request = CreateMessageRequest.builder() \
            .receive_id_type("chat_id") \
            .request_body(CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type(msg_type_str)
                .content(content_str)
                .build()) \
            .build()
        msg_type = "card" if use_card else "text"

        start_time = time.time()
        response = self.client.im.v1.message.create(request)
        elapsed = time.time() - start_time
        
        if response.success():
            self._log_feishu("RECV", {
                "type": "CREATE_RESPONSE",
                "message_id": response.data.message_id if response.data else None,
                "elapsed_ms": int(elapsed * 1000)
            }, f"success, time={elapsed:.3f}s")
            print(f"发送成功 ({msg_type}, {text_length}字)")
            return response.data.message_id  # 返回 message_id 用于后续更新
        else:
            self._log_feishu("RECV", {
                "type": "CREATE_RESPONSE",
                "error_code": response.code,
                "error_msg": response.msg
            }, f"failed, time={elapsed:.3f}s")
            print(f"发送失败: {response.code} - {response.msg}")
            return None

    def _build_v2_card_content(self, text):
        """构建飞书新版消息卡片内容（V2 格式，支持完整 Markdown）
        
        新版卡片支持 markdown 元素，可以渲染：
        - 标题 (# ## ###)
        - 粗体 (**text**)
        - 斜体 (*text*)
        - 删除线 (~~text~~)
        - 代码块 (```code```)
        - 行内代码 (`code`)
        - 链接 ([text](url))
        - 无序列表 (- item)
        - 有序列表 (1. item)
        - 引用 (> text)
        - 分割线 (---)
        """
        if not text:
            return {
                "schema": "2.0",
                "config": {"width_mode": "fill"},
                "body": {"elements": []}
            }
        
        elements = []
        lines = text.split('\n')
        i = 0
        
        while i < len(lines):
            line = lines[i]
            stripped = line.strip()
            
            # 跳过空行
            if not stripped:
                i += 1
                continue
            
            # 检测代码块开始 ```
            if stripped.startswith('```'):
                language = stripped[3:].strip()
                code_lines = []
                i += 1
                while i < len(lines) and not lines[i].strip().startswith('```'):
                    code_lines.append(lines[i])
                    i += 1
                i += 1  # 跳过结束标记
                
                code_content = '\n'.join(code_lines)
                # 使用 markdown 元素渲染代码块
                elements.append({
                    "tag": "markdown",
                    "content": f"```{language}\n{code_content}\n```"
                })
                continue
            
            # 检测标题 (# ## ###)
            header_match = re.match(r'^(#{1,6})\s+(.+)$', stripped)
            if header_match:
                level = len(header_match.group(1))
                content = header_match.group(2)
                elements.append({
                    "tag": "markdown",
                    "content": f"{'#' * level} {content}"
                })
                i += 1
                continue
            
            # 检测分割线
            if stripped == '---' or stripped == '***' or stripped == '___':
                elements.append({"tag": "hr"})
                i += 1
                continue
            
            # 普通 Markdown 内容（包括列表、粗体、斜体、代码等）
            # 收集连续的普通行
            markdown_lines = []
            while i < len(lines):
                current_line = lines[i]
                current_stripped = current_line.strip()
                
                # 遇到代码块、标题、分割线、空行时停止
                if not current_stripped:
                    break
                if current_stripped.startswith('```'):
                    break
                if re.match(r'^#{1,6}\s+', current_stripped):
                    break
                if current_stripped in ('---', '***', '___'):
                    break
                
                markdown_lines.append(current_line)
                i += 1
            
            if markdown_lines:
                content = '\n'.join(markdown_lines)
                elements.append({
                    "tag": "markdown",
                    "content": content
                })
        
        return {
            "schema": "2.0",
            "config": {"width_mode": "fill"},
            "body": {"elements": elements}
        }

    def update_card(self, message_id, text):
        """更新消息卡片内容（智能批量策略）- 线程安全
        
        前2次更新立即发送（快速响应开始）
        后续使用1秒批量策略（配合API 0.6秒延迟）
        """
        with self._update_lock:
            # 保存最新的待更新内容
            self._pending_updates[message_id] = text
            
            # 获取当前更新计数
            count = self._update_counts.get(message_id, 0)
            
            # 前2次立即发送（快速响应）
            if count < 2:
                self._update_counts[message_id] = count + 1
                # 取消可能存在的定时器
                if message_id in self._update_timers:
                    try:
                        self._update_timers[message_id].cancel()
                    except:
                        pass
                    del self._update_timers[message_id]
                # 立即发送
                self.executor.submit(self._do_update_card, message_id)
                return
            
            # 如果该消息已经有定时器在运行，不创建新的
            if message_id in self._update_timers and self._update_timers[message_id].is_alive():
                return
            
            # 创建定时器，0.3秒后执行实际更新（匹配动画频率）
            timer = threading.Timer(0.3, self._do_update_card, args=[message_id])
            self._update_timers[message_id] = timer
            timer.start()
    
    def _do_update_card(self, message_id):
        """实际执行卡片更新（批量策略）"""
        from lark_oapi.api.im.v1 import PatchMessageRequest, PatchMessageRequestBody
        
        with self._update_lock:
            # 获取最新的待更新内容
            text = self._pending_updates.get(message_id, "")
            if not text:
                return
            
            # 如果消息已完成且内容包含"生成中..."，跳过更新
            if message_id in self._completed_messages and "生成中..." in text:
                self._log(f"[DEBUG] 跳过已完成的生成中更新")
                self._pending_updates[message_id] = ""
                if message_id in self._update_timers:
                    del self._update_timers[message_id]
                return
            
            # 清空待更新内容
            self._pending_updates[message_id] = ""
            
            # 清理定时器引用
            if message_id in self._update_timers:
                del self._update_timers[message_id]
        
        # 执行实际更新
        self._do_update_card_now(message_id, text)
    
    def _do_update_card_now(self, message_id, text):
        """立即执行卡片更新（不经过批量策略）"""
        from lark_oapi.api.im.v1 import PatchMessageRequest, PatchMessageRequestBody
        
        if not text:
            return
        
        start_time = time.time()
        
        # 记录发送给飞书的更新请求
        self._log_feishu("SEND", {
            "type": "UPDATE_CARD_V2",
            "message_id": message_id,
            "text_length": len(text),
            "text_preview": text[:200] if len(text) > 200 else text
        }, "streaming update")
        
        # 构建新版消息卡片内容 (V2)
        card_content = self._build_v2_card_content(text)

        request = PatchMessageRequest.builder() \
            .message_id(message_id) \
            .request_body(PatchMessageRequestBody.builder()
                .content(json.dumps(card_content))
                .build()) \
            .build()

        response = self.client.im.v1.message.patch(request)
        elapsed = time.time() - start_time
        
        # 记录飞书API响应
        self._log_feishu("RECV", {
            "type": "UPDATE_CARD_V2_RESPONSE",
            "success": response.success(),
            "code": response.code if not response.success() else 0,
            "elapsed_ms": round(elapsed * 1000, 2)
        }, "streaming response")
        
        # 流式更新时减少日志输出
        if elapsed > 0.5 or len(text) < 100:
            if response.success():
                self._log(f"[DEBUG] 更新卡片成功 ({len(text)}字, 耗时{elapsed:.2f}s)")
            else:
                self._log(f"[ERROR] 更新卡片失败: {response.code} - {response.msg}")

    def _get_tenant_access_token(self):
        """获取 tenant_access_token"""
        try:
            from lark_oapi.api.auth.v3 import InternalTenantAccessTokenRequest, InternalTenantAccessTokenRequestBody
            
            request = InternalTenantAccessTokenRequest.builder() \
                .request_body(InternalTenantAccessTokenRequestBody.builder()
                    .app_id(self.app_id)
                    .app_secret(self.app_secret)
                    .build()) \
                .build()
            
            response = self.client.auth.v3.tenant_access_token.internal(request)
            
            if response.success() and hasattr(response, 'raw') and response.raw:
                content = response.raw.content.decode('utf-8')
                data = json.loads(content)
                return data.get('tenant_access_token')
            else:
                self._log(f"[ERROR] 获取 tenant_access_token 失败")
                return None
        except Exception as e:
            self._log(f"[ERROR] 获取 tenant_access_token 异常: {e}")
            return None

    def _handle_image_message(self, chat_id, image_key, message_id):
        """处理图片消息 - 使用 messages/:message_id/resources/:file_key 接口"""
        try:
            self._log(f"[DEBUG] 处理图片消息, image_key: {image_key}, message_id: {message_id}")
            
            # 先发送占位消息
            initial_message_id = self.reply_text(chat_id, "⏳ 正在下载图片...", streaming=True)
            
            # 获取 tenant_access_token
            tenant_token = self._get_tenant_access_token()
            if not tenant_token:
                self.update_card(initial_message_id, "❌ 获取访问令牌失败")
                return
            
            # 使用 messages/:message_id/resources/:file_key 接口下载图片
            import requests
            import urllib.parse
            
            encoded_key = urllib.parse.quote(image_key, safe='')
            # 添加 type=image 查询参数（根据 file_res_api.md 文档要求）
            url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/resources/{encoded_key}?type=image"
            headers = {"Authorization": f"Bearer {tenant_token}"}
            
            self._log(f"[DEBUG] 下载图片: {url}")
            resp = requests.get(url, headers=headers, timeout=30)
            
            self._log(f"[DEBUG] 图片响应: status={resp.status_code}")
            
            if resp.status_code != 200:
                error_msg = resp.text[:500] if resp.text else f"HTTP {resp.status_code}"
                self._log(f"[ERROR] 下载图片失败: {error_msg}")
                self.update_card(initial_message_id, f"⚠️ **无法处理图片**\n\n飞书平台限制，无法获取用户发送的图片。\n\n**替代方案**：请用文字描述图片内容。")
                return
            
            # 处理图片数据
            image_data = resp.content
            if not image_data:
                self.update_card(initial_message_id, "❌ 图片内容为空")
                return
            
            # 检查图片大小（限制 5MB）
            if len(image_data) > 5 * 1024 * 1024:
                self.update_card(initial_message_id, f"⚠️ 图片太大 ({len(image_data)/1024/1024:.1f}MB)，请压缩后重试")
                return
            
            # 保存图片到 WORKPLACE 目录
            workplace_dir = os.path.join(os.path.dirname(__file__), 'WORKPLACE', 'user_images')
            os.makedirs(workplace_dir, exist_ok=True)
            image_filename = f"{chat_id}_{int(time.time())}.png"
            image_path = os.path.join(workplace_dir, image_filename)
            
            with open(image_path, 'wb') as f:
                f.write(image_data)
            
            # 标记为待处理图片，等待用户下一条消息
            self._pending_image[chat_id] = image_path
            self._log(f"[DEBUG] 已保存用户图片，等待下一步指令: {image_path}")
            
            # 图片获取成功，回复用户并询问接下来要做什么
            self.update_card(initial_message_id, f"✅ **收到图片！**\n\n请告诉我您想对这张图片做什么？\n\n例如：\n- 分析图片内容\n- 提取图片中的文字\n- 描述图片场景\n- 其他需求请直接告诉我")
            
        except Exception as e:
            self._log(f"[ERROR] 处理图片异常: {e}")
            self.reply_text(chat_id, f"❌ 处理图片失败: {str(e)}", streaming=False)

    def _handle_file_message(self, chat_id, file_key, file_name, message_id):
        """处理文件消息 - 使用 messages/:message_id/resources/:file_key 接口"""
        try:
            self._log(f"[DEBUG] 处理文件消息, file_key: {file_key}, name: {file_name}")
            
            # 先发送占位消息
            initial_message_id = self.reply_text(chat_id, f"⏳ 正在下载文件: {file_name}...", streaming=True)
            
            # 获取 tenant_access_token
            tenant_token = self._get_tenant_access_token()
            if not tenant_token:
                self.update_card(initial_message_id, "❌ 获取访问令牌失败")
                return
            
            # 使用 messages/:message_id/resources/:file_key 接口下载文件
            import requests
            import urllib.parse
            
            encoded_key = urllib.parse.quote(file_key, safe='')
            # 添加 type=file 查询参数（根据 file_res_api.md 文档要求）
            url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/resources/{encoded_key}?type=file"
            headers = {"Authorization": f"Bearer {tenant_token}"}
            
            self._log(f"[DEBUG] 下载文件: {url}")
            resp = requests.get(url, headers=headers, timeout=60)
            
            self._log(f"[DEBUG] 文件响应: status={resp.status_code}")
            
            if resp.status_code != 200:
                error_msg = resp.text[:500] if resp.text else f"HTTP {resp.status_code}"
                self._log(f"[ERROR] 下载文件失败: {error_msg}")
                self.update_card(initial_message_id, f"⚠️ **无法处理文件**\n\n飞书平台限制，无法获取用户发送的文件。\n\n**替代方案**：请将文件内容复制粘贴发送。")
                return
            
            # 处理文件数据
            file_data = resp.content
            if not file_data:
                self.update_card(initial_message_id, "❌ 文件内容为空")
                return
            
            # 保存文件到 WORKPLACE/user_files 目录
            files_dir = os.path.join(os.path.dirname(__file__), 'WORKPLACE', 'user_files')
            os.makedirs(files_dir, exist_ok=True)
            # 使用原始文件名，但添加时间戳避免冲突
            safe_filename = f"{int(time.time())}_{file_name}"
            file_path = os.path.join(files_dir, safe_filename)
            
            with open(file_path, 'wb') as f:
                f.write(file_data)
            
            # 标记为待处理文件，等待用户下一条消息
            self._pending_file[chat_id] = file_path
            self._log(f"[DEBUG] 已保存用户文件，等待下一步指令: {file_path}")
            
            # 文件获取成功，回复用户并询问接下来要做什么
            self.update_card(initial_message_id, f"✅ **收到文件: {file_name}！**\n\n请告诉我您想对这个文件做什么？\n\n例如：\n- 分析文件内容\n- 总结文件要点\n- 提取关键信息\n- 其他需求请直接告诉我")
            
        except Exception as e:
            self._log(f"[ERROR] 处理文件异常: {e}")
            self.reply_text(chat_id, f"❌ 处理文件失败: {str(e)}", streaming=False)

    def _call_acp_with_text(self, chat_id, initial_message_id, prompt):
        """调用 ACP 处理文本（复用流式输出逻辑）"""
        try:
            if self.acp_client is None:
                self.acp_client = ACPClient(bot_ref=self)

            last_update_time = [time.time()]
            last_content = [""]
            first_update = [True]
            is_completed = [False]
            waiting_symbols = ["◐", "○", "◑", "●"]
            symbol_index = [0]
            animation_timer = [None]
            
            def get_waiting_symbol():
                symbol = waiting_symbols[symbol_index[0] % len(waiting_symbols)]
                symbol_index[0] += 1
                return symbol
            
            def update_animation():
                """独立更新动画符号，每0.3秒执行一次"""
                if is_completed[0]:
                    return
                
                # 无条件更新动画符号（定时器本身就是每0.3秒触发）
                current_text = last_content[0] if last_content[0] else "⏳ 正在思考..."
                display_text = current_text + f"\n\n{get_waiting_symbol()} **生成中...**"
                self.executor.submit(self.update_card, initial_message_id, display_text)
                
                if not is_completed[0]:
                    animation_timer[0] = threading.Timer(0.3, update_animation)
                    animation_timer[0].start()
            
            # 立即显示第一帧动画（不要等待定时器）
            update_animation()
            
            def on_chunk(current_text):
                if is_completed[0]:
                    return
                
                # 仅更新内容（动画定时器会负责每0.3秒更新一次卡片）
                if current_text != last_content[0]:
                    last_content[0] = current_text
            
            def on_chunk_final(final_text):
                """最终回调 - 立即去掉动画"""
                is_completed[0] = True
                
                # 停止动画定时器
                if animation_timer[0]:
                    try:
                        animation_timer[0].cancel()
                    except:
                        pass
                
                # 等待一小段时间，确保线程池中的动画更新完成
                time.sleep(0.1)
                
                with self._update_lock:
                    self._completed_messages.add(initial_message_id)
                    if initial_message_id in self._update_timers:
                        try:
                            self._update_timers[initial_message_id].cancel()
                        except:
                            pass
                        del self._update_timers[initial_message_id]
                    self._pending_updates[initial_message_id] = ""
                
                # 等待一小段时间，确保已提交的动画更新完成
                time.sleep(0.2)
                # 立即更新卡片，去掉生成中字样
                self._do_update_card_now(initial_message_id, final_text)

            response = self.acp_client.chat(prompt, on_chunk=on_chunk, timeout=300)
            on_chunk_final(response)
            
        except Exception as e:
            self._log(f"[ERROR] 调用 ACP 出错: {e}")
            self.update_card(initial_message_id, f"❌ 处理失败: {str(e)}")
