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
        # 确保日志目录存在
        os.makedirs(os.path.dirname(self.log_file), exist_ok=True)
        os.makedirs(os.path.dirname(self.feishu_log_file), exist_ok=True)
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

    def _download_chat_image(self, message_id: str, image_key: str, chat_id: str) -> str:
        """下载群聊中的图片并返回本地路径"""
        try:
            # 获取 tenant_access_token
            tenant_token = self._get_tenant_access_token()
            if not tenant_token:
                self._log(f"[ERROR] 获取 tenant_access_token 失败，无法下载图片")
                return None
            
            import requests
            import urllib.parse
            
            # 方法1: 尝试从消息资源下载（适用于消息附件图片）
            if message_id:
                encoded_key = urllib.parse.quote(image_key, safe='')
                url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/resources/{encoded_key}?type=image"
                headers = {"Authorization": f"Bearer {tenant_token}"}
                
                self._log(f"[DEBUG] 尝试从消息资源下载图片: {image_key[:30]}...")
                resp = requests.get(url, headers=headers, timeout=30)
                
                if resp.status_code == 200:
                    image_data = resp.content
                    if image_data:
                        return self._save_image_data(image_data, chat_id, image_key)
                
                self._log(f"[DEBUG] 消息资源下载失败({resp.status_code})，尝试图片 API...")
            
            # 方法2: 使用图片 API 下载（适用于卡片图片）
            url = f"https://open.feishu.cn/open-apis/image/v4/get?image_key={urllib.parse.quote(image_key)}"
            headers = {"Authorization": f"Bearer {tenant_token}"}
            
            self._log(f"[DEBUG] 尝试从图片 API 下载: {image_key[:30]}...")
            resp = requests.get(url, headers=headers, timeout=30)
            
            if resp.status_code == 200:
                try:
                    result = resp.json()
                    # 检查飞书 API 业务码
                    if result.get('code') == 0 and 'data' in result and 'image' in result['data']:
                        import base64
                        image_data = base64.b64decode(result['data']['image'])
                        return self._save_image_data(image_data, chat_id, image_key)
                    else:
                        # API 返回 200 但业务失败
                        biz_code = result.get('code', 'unknown')
                        biz_msg = result.get('msg', 'no message')
                        self._log(f"[WARN] 图片 API 业务失败: code={biz_code}, msg={biz_msg}")
                except Exception as e:
                    self._log(f"[WARN] 解析图片 API 响应失败: {e}")
            else:
                self._log(f"[WARN] 图片 API HTTP 失败: status={resp.status_code}")
            
            # 图片下载失败，但这不是致命错误，返回 None 让调用方处理
            self._log(f"[DEBUG] 图片无法下载 (可能无权限或图片已过期): {image_key[:30]}...")
            return None
            
        except Exception as e:
            self._log(f"[ERROR] 下载图片异常: {e}")
            return None
    
    def _save_image_data(self, image_data: bytes, chat_id: str, image_key: str) -> str:
        """保存图片数据到本地"""
        try:
            # 检查图片大小（限制 5MB）
            if len(image_data) > 5 * 1024 * 1024:
                self._log(f"[WARN] 图片太大 ({len(image_data)/1024/1024:.1f}MB)，跳过")
                return None
            
            # 保存图片到 WORKPLACE 目录
            workplace_dir = get_absolute_path('WORKPLACE/user_images')
            os.makedirs(workplace_dir, exist_ok=True)
            
            # 生成唯一文件名
            image_filename = f"chat_{chat_id}_{int(time.time())}_{image_key[:16]}.png"
            image_path = os.path.join(workplace_dir, image_filename)
            
            with open(image_path, 'wb') as f:
                f.write(image_data)
            
            self._log(f"[DEBUG] 图片已保存: {image_path}")
            return image_path
            
        except Exception as e:
            self._log(f"[ERROR] 保存图片异常: {e}")
            return None
    
    def _find_local_image_by_key(self, image_key: str, chat_id: str) -> str:
        """
        根据 image_key 在本地查找图片。
        
        注意：Bot 发送的卡片消息会被飞书服务器渲染成预览图，这个渲染图的 image_key
        无法通过 API 下载，且本地也没有保存（渲染是在飞书服务端进行的）。
        这个方法主要用于查找用户上传后被 Bot 下载保存的图片。
        """
        try:
            workplace_dir = get_absolute_path('WORKPLACE/user_images')
            if not os.path.exists(workplace_dir):
                return None
            
            # 提取 image_key 的关键部分
            key_part = image_key.split('_')[-1] if '_' in image_key else image_key[:20]
            
            # 查找文件名包含 image_key 片段的图片
            matching_files = []
            for filename in os.listdir(workplace_dir):
                if not filename.endswith(('.png', '.jpg', '.jpeg')):
                    continue
                
                file_path = os.path.join(workplace_dir, filename)
                
                # 检查文件名是否包含 image_key 的关键部分
                if key_part[:16] in filename or image_key[:16] in filename:
                    mtime = os.path.getmtime(file_path)
                    matching_files.append((file_path, mtime))
            
            if matching_files:
                # 按修改时间排序，返回最新的匹配
                matching_files.sort(key=lambda x: x[1], reverse=True)
                latest_path = matching_files[0][0]
                self._log(f"[DEBUG] 找到匹配的图片: {latest_path}")
                return latest_path
            
            # 没有找到匹配的图片
            self._log(f"[DEBUG] 未找到匹配 image_key {image_key[:30]}... 的本地图片")
            return None
            
        except Exception as e:
            self._log(f"[DEBUG] 查找本地图片失败: {e}")
            return None

    def _get_chat_history(self, chat_id: str, limit: int = 30) -> list:
        """获取最近聊天记录（最近7天内），图片消息会下载并返回本地路径"""
        try:
            from lark_oapi.api.im.v1 import ListMessageRequest
            
            self._log(f"[DEBUG] 开始获取聊天记录: chat_id={chat_id}, limit={limit}")
            
            # 计算7天前的时间戳（毫秒）用于过滤
            days_ago = int((time.time() - 7 * 24 * 60 * 60) * 1000)
            
            # 请求消息列表 - 需要分页获取最新消息
            all_items = []
            page_token = None
            max_pages = 10
            
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
            fetch_limit = min(limit * 3, len(recent_items))
            recent_items = recent_items[:fetch_limit]
            
            self._log(f"[DEBUG] 取最新 {len(recent_items)} 条消息进行解析")
            
            history = []
            for idx, item in enumerate(recent_items):
                try:
                    # 获取 sender
                    sender = item.sender.id if item.sender and hasattr(item.sender, 'id') else "unknown"
                    content = json.loads(item.body.content) if item.body else {}
                    text = content.get('text', '')
                    msg_type = getattr(item, 'msg_type', 'unknown')
                    message_id = getattr(item, 'message_id', '')
                    
                    # 处理图片消息 - 下载并返回本地路径
                    if msg_type == 'image':
                        image_key = content.get('image_key', '')
                        if image_key:
                            self._log(f"[DEBUG] 消息 {idx} 是图片，尝试下载...")
                            local_path = self._download_chat_image(message_id, image_key, chat_id)
                            if local_path:
                                history.append({
                                    'type': 'image',
                                    'sender': sender,
                                    'content': local_path
                                })
                                self._log(f"[DEBUG] 图片消息已转换: {local_path}")
                            else:
                                history.append({
                                    'type': 'text',
                                    'sender': sender,
                                    'content': '[图片下载失败]'
                                })
                        continue
                    
                    # 处理文件消息 - 下载并返回本地路径
                    if msg_type == 'file':
                        file_key = content.get('file_key', '')
                        file_name = content.get('file_name', 'unknown')
                        if file_key:
                            self._log(f"[DEBUG] 消息 {idx} 是文件({file_name})，尝试下载...")
                            local_path = self._download_chat_file(message_id, file_key, file_name, chat_id)
                            if local_path:
                                history.append({
                                    'type': 'file',
                                    'sender': sender,
                                    'content': local_path,
                                    'file_name': file_name
                                })
                                self._log(f"[DEBUG] 文件消息已转换: {local_path}")
                            else:
                                history.append({
                                    'type': 'text',
                                    'sender': sender,
                                    'content': f'[文件: {file_name} - 下载失败]'
                                })
                        continue
                    
                    # 如果是卡片消息（interactive），尝试提取文本内容
                    if not text and msg_type == 'interactive':
                        elements = content.get('elements', [])
                        texts = []
                        has_image = False
                        card_image_keys = []
                        for element_list in elements:
                            if isinstance(element_list, list):
                                for elem in element_list:
                                    if isinstance(elem, dict):
                                        if elem.get('tag') == 'text':
                                            texts.append(elem.get('text', ''))
                                        elif elem.get('tag') == 'img':
                                            has_image = True
                                            # 获取图片 key
                                            img_key = elem.get('image_key', '')
                                            if img_key:
                                                card_image_keys.append(img_key)
                        text = ''.join(texts)
                        
                        if has_image and ('请升级至最新版本' in text or '查看内容' in text):
                            # 判断是否是 Bot 自己发送的卡片
                            is_bot_sender = sender.startswith('cli_') or sender == self._bot_user_id
                            
                            if is_bot_sender:
                                # Bot 自己发送的卡片，不尝试下载（预览图权限受限）
                                text = "[图片/卡片回复] (Bot 发送的卡片)"
                                self._log(f"[DEBUG] 消息 {idx} 是 Bot 发送的卡片，跳过下载")
                            elif card_image_keys:
                                # 用户或其他发送者发送的卡片，尝试获取图片
                                self._log(f"[DEBUG] 卡片包含 {len(card_image_keys)} 个图片，尝试获取...")
                                local_images = []
                                
                                for img_key in card_image_keys:
                                    local_path = None
                                    
                                    # 方法1: 尝试下载（适用于用户上传的图片）
                                    if message_id:
                                        local_path = self._download_chat_image(message_id, img_key, chat_id)
                                    
                                    # 方法2: 在本地查找（适用于之前下载过的图片）
                                    if not local_path:
                                        local_path = self._find_local_image_by_key(img_key, chat_id)
                                    
                                    if local_path:
                                        local_images.append(local_path)
                                
                                if local_images:
                                    text = f"[图片/卡片回复] {' '.join(local_images)}"
                                else:
                                    text = f"[图片/卡片回复] (无法获取图片)"
                            else:
                                text = "[图片/卡片回复]"
                        
                        if text:
                            self._log(f"[DEBUG] 消息 {idx} 是卡片，提取文本: {text[:100]}...")
                    
                    # 跳过空文本
                    if not text:
                        self._log(f"[DEBUG] 消息 {idx} 文本为空，跳过 (type={msg_type})")
                        continue
                    
                    # 跳过纯 @ 标记
                    if text.strip() == '@_user_1' or text.strip().startswith('@_user_1'):
                        self._log(f"[DEBUG] 消息 {idx} 是纯 @ 标记，跳过: {text}")
                        continue
                    
                    # 如果消息太长，截取最后100字
                    if len(text) > 100:
                        text = "..." + text[-100:]
                    
                    history.append({
                        'type': 'text',
                        'sender': sender,
                        'content': text
                    })
                except Exception as e:
                    self._log(f"[DEBUG] 处理消息 {idx} 出错: {e}")
                    continue
            
            # 限制返回数量，并按时间正序排列
            history = history[:limit]
            history.reverse()
            
            self._log(f"[DEBUG] 成功解析 {len(history)} 条聊天记录（含图片/文件）")
            return history
        except Exception as e:
            self._log(f"[ERROR] 获取聊天记录异常: {e}")
            import traceback
            self._log(f"[ERROR] 异常详情: {traceback.format_exc()}")
            return []

    def _download_chat_file(self, message_id: str, file_key: str, file_name: str, chat_id: str) -> str:
        """下载群聊中的文件并返回本地路径"""
        try:
            # 获取 tenant_access_token
            tenant_token = self._get_tenant_access_token()
            if not tenant_token:
                self._log(f"[ERROR] 获取 tenant_access_token 失败，无法下载文件")
                return None
            
            import requests
            import urllib.parse
            
            encoded_key = urllib.parse.quote(file_key, safe='')
            url = f"https://open.feishu.cn/open-apis/im/v1/messages/{message_id}/resources/{encoded_key}?type=file"
            headers = {"Authorization": f"Bearer {tenant_token}"}
            
            self._log(f"[DEBUG] 下载群聊文件: {file_name}")
            resp = requests.get(url, headers=headers, timeout=60)
            
            if resp.status_code != 200:
                self._log(f"[ERROR] 下载文件失败: {resp.status_code}")
                return None
            
            file_data = resp.content
            if not file_data:
                self._log(f"[ERROR] 文件内容为空")
                return None
            
            # 检查文件大小（限制 20MB）
            if len(file_data) > 20 * 1024 * 1024:
                self._log(f"[WARN] 文件太大 ({len(file_data)/1024/1024:.1f}MB)，跳过")
                return None
            
            # 保存文件到 WORKPLACE 目录
            files_dir = get_absolute_path('WORKPLACE/user_files')
            os.makedirs(files_dir, exist_ok=True)
            
            # 生成安全文件名
            safe_name = f"chat_{chat_id}_{int(time.time())}_{file_name}"
            file_path = os.path.join(files_dir, safe_name)
            
            with open(file_path, 'wb') as f:
                f.write(file_data)
            
            self._log(f"[DEBUG] 文件已保存: {file_path}")
            return file_path
            
        except Exception as e:
            self._log(f"[ERROR] 下载文件异常: {e}")
            return None

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
            
            # 构建上下文提示（支持图片和文件）
            context_prompt = ""
            if chat_history:
                context_parts = ["以下是最近聊天记录上下文：\n"]
                for msg in chat_history[-30:]:
                    if isinstance(msg, dict):
                        sender = msg.get('sender', 'unknown')
                        msg_type = msg.get('type', 'text')
                        content = msg.get('content', '')
                        
                        if msg_type == 'image':
                            # 图片消息：发送本地路径，Kimi 可以读取图片
                            context_parts.append(f"{sender}: [图片] {content}")
                        elif msg_type == 'file':
                            # 文件消息：发送本地路径
                            file_name = msg.get('file_name', 'unknown')
                            context_parts.append(f"{sender}: [文件: {file_name}] {content}")
                        else:
                            # 文本消息
                            context_parts.append(f"{sender}: {content}")
                    else:
                        # 兼容旧格式（字符串）
                        context_parts.append(msg)
                
                context_prompt = "\n".join(context_parts) + "\n\n"

            # 根据消息类型处理
            if msg_type == 'text':
                text = current_text
                
                # 构建最终提示词
                final_prompt = context_prompt + f"用户当前消息：{text}\n\n请基于上下文回复用户的消息。"
                
                # 日志打印发送给 ACP 的完整 prompt
                self._log(f"[DEBUG] ===== 发送给 ACP 的 Prompt =====")
                self._log(f"[DEBUG] Chat ID: {chat_id}, Chat Type: {chat_type}")
                self._log(f"[DEBUG] Prompt 长度: {len(final_prompt)} 字符")
                self._log(f"[DEBUG] 完整 Prompt:\n{final_prompt}")
                self._log(f"[DEBUG] ===== Prompt 结束 =====")
                
                # 检查是否有待处理的图片或文件
                if chat_id in self._pending_image:
                    image_path = self._pending_image[chat_id]
                    if os.path.exists(image_path):
                        combined_prompt = f"{context_prompt}用户发送了一张图片，路径为: {image_path}\n\n用户对该图片的指令: {text}\n\n请根据用户的指令分析处理这张图片。"
                        self._log(f"[DEBUG] 将图片和消息一起发送给 Kimi: {image_path}, 消息: {text[:50]}...")
                        # 日志打印发送给 ACP 的完整 prompt
                        self._log(f"[DEBUG] ===== 发送给 ACP 的 Prompt (带图片) =====")
                        self._log(f"[DEBUG] Chat ID: {chat_id}, Chat Type: {chat_type}")
                        self._log(f"[DEBUG] Prompt 长度: {len(combined_prompt)} 字符")
                        self._log(f"[DEBUG] 完整 Prompt:\n{combined_prompt}")
                        self._log(f"[DEBUG] ===== Prompt 结束 =====")
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
                        # 日志打印发送给 ACP 的完整 prompt
                        self._log(f"[DEBUG] ===== 发送给 ACP 的 Prompt (带文件) =====")
                        self._log(f"[DEBUG] Chat ID: {chat_id}, Chat Type: {chat_type}")
                        self._log(f"[DEBUG] Prompt 长度: {len(combined_prompt)} 字符")
                        self._log(f"[DEBUG] 完整 Prompt:\n{combined_prompt}")
                        self._log(f"[DEBUG] ===== Prompt 结束 =====")
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

    def run_msg_script_streaming(self, chat_id, text, async_mode=False):
        """使用 ACP 协议调用 Kimi Code CLI（流式输出）
        
        Args:
            chat_id: 聊天ID
            text: 用户输入文本
            async_mode: 是否使用异步模式（长时间任务在后台执行）
        """
        try:
            # 延迟初始化 ACP 客户端（传递 self 引用）
            if self.acp_client is None:
                self._log("[DEBUG] 初始化 ACP 客户端...")
                self.acp_client = ACPClient(bot_ref=self)

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
            is_background = [False]  # 是否已转为后台执行
            
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
                
                try:
                    # 无条件更新动画符号（定时器本身就是每0.3秒触发）
                    current_text = last_content[0] if last_content[0] else "⏳ 正在思考..."
                    display_text = current_text + f"\n\n{get_waiting_symbol()} **生成中...**"
                    self.executor.submit(self.update_card, initial_message_id, display_text)
                except Exception as e:
                    self._log(f"[WARN] 动画更新异常: {e}")
                
                # 安排下一次更新（即使本次异常也要继续）
                if not is_completed[0]:
                    try:
                        animation_timer[0] = threading.Timer(0.3, update_animation)
                        animation_timer[0].start()
                    except Exception as e:
                        self._log(f"[ERROR] 动画定时器启动失败: {e}")
            
            # 立即显示第一帧动画（不要等待定时器）
            update_animation()
            
            def on_chunk(current_text):
                """收到新的文本块时的回调 - 仅更新内容"""
                if is_completed[0]:
                    return
                
                # 检测是否转为后台执行
                if "后台执行" in current_text or "后台任务" in current_text:
                    if not is_background[0]:
                        is_background[0] = True
                        self._log(f"[INFO] 检测到任务转为后台执行: {chat_id}")
                
                # 仅更新内容（动画定时器会负责每0.3秒更新一次卡片）
                if current_text != last_content[0]:
                    last_content[0] = current_text
                    
                    # 检查动画定时器是否还在运行，如果停止则重新启动
                    # （处理长时间工具调用后定时器过期的情况）
                    if animation_timer[0] is None or not animation_timer[0].is_alive():
                        self._log(f"[DEBUG] 检测到动画定时器停止，重新启动")
                        animation_timer[0] = threading.Timer(0.3, update_animation)
                        animation_timer[0].start()
            
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

            # 检查是否是后台任务（Kimi 将任务放入后台执行）
            if is_background[0] and ("请稍后再试" in response or "请稍后查看" in response or len(response) < 50):
                self._log(f"[INFO] 检测到后台任务，启动守护线程等待结果: {chat_id}")
                # 启动后台任务等待线程
                self.executor.submit(self._wait_for_background_task, chat_id, text, initial_message_id)
                return

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
            workplace_dir = get_absolute_path('WORKPLACE/user_images')
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
            files_dir = get_absolute_path('WORKPLACE/user_files')
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
                
                try:
                    # 无条件更新动画符号（定时器本身就是每0.3秒触发）
                    current_text = last_content[0] if last_content[0] else "⏳ 正在思考..."
                    display_text = current_text + f"\n\n{get_waiting_symbol()} **生成中...**"
                    self.executor.submit(self.update_card, initial_message_id, display_text)
                except Exception as e:
                    self._log(f"[WARN] 动画更新异常: {e}")
                
                # 安排下一次更新（即使本次异常也要继续）
                if not is_completed[0]:
                    try:
                        animation_timer[0] = threading.Timer(0.3, update_animation)
                        animation_timer[0].start()
                    except Exception as e:
                        self._log(f"[ERROR] 动画定时器启动失败: {e}")
            
            # 立即显示第一帧动画（不要等待定时器）
            update_animation()
            
            def on_chunk(current_text):
                if is_completed[0]:
                    return
                
                # 仅更新内容（动画定时器会负责每0.3秒更新一次卡片）
                if current_text != last_content[0]:
                    last_content[0] = current_text
                    
                    # 检查动画定时器是否还在运行，如果停止则重新启动
                    if animation_timer[0] is None or not animation_timer[0].is_alive():
                        self._log(f"[DEBUG] 检测到动画定时器停止，重新启动")
                        animation_timer[0] = threading.Timer(0.3, update_animation)
                        animation_timer[0].start()
            
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

    def _wait_for_background_task(self, chat_id, original_prompt, original_message_id):
        """后台任务等待线程 - 当Kimi将任务放入后台执行后，等待结果并通知用户
        
        Args:
            chat_id: 聊天ID
            original_prompt: 原始提示词
            original_message_id: 原始消息ID（用于更新）
        """
        try:
            self._log(f"[INFO] 后台任务等待线程启动: {chat_id}")
            
            # 先更新原消息，提示用户任务在后台执行
            self._do_update_card_now(original_message_id, 
                "🔄 **任务已在后台执行**\n\n"
                "由于执行时间较长，任务已在后台运行。\n"
                "完成后将自动通知您。\n\n"
                "⏳ 预计等待时间：几分钟到十几分钟")
            
            # 等待一段时间后再查询结果（给Kimi时间执行）
            # 第一次等待：30秒
            time.sleep(30)
            
            # 尝试重新获取结果
            retry_count = 0
            max_retries = 20  # 最多重试20次，每次30秒，总共最多10分钟
            
            while retry_count < max_retries:
                retry_count += 1
                self._log(f"[INFO] 后台任务查询中... 第{retry_count}次: {chat_id}")
                
                try:
                    # 使用相同的prompt再次调用，Kimi会返回任务状态或结果
                    # 添加标记表示这是查询请求
                    query_prompt = f"[查询后台任务状态] {original_prompt}\n\n"
                    
                    response = self.acp_client.chat(query_prompt, timeout=60)
                    
                    # 检查结果是否包含"还在执行"、"请稍后"等提示
                    if any(keyword in response for keyword in ["还在执行", "请稍后", "未完成", "进行中"]):
                        self._log(f"[INFO] 任务仍在执行，继续等待: {chat_id}")
                        time.sleep(30)  # 继续等待30秒
                        continue
                    
                    # 如果获取到了结果（不是等待提示）
                    if len(response) > 100 and not any(keyword in response for keyword in ["请稍后再试", "请稍后查看"]):
                        self._log(f"[INFO] 后台任务完成，发送结果: {chat_id}")
                        
                        # 更新原消息为完成状态
                        self._do_update_card_now(original_message_id, response)
                        
                        # 同时发送一条新消息通知用户
                        self.reply_text(chat_id, 
                            f"✅ **后台任务已完成！**\n\n"
                            f"任务结果已更新到上一条消息。\n"
                            f"📊 结果长度: {len(response)} 字符", 
                            streaming=False)
                        return
                    
                    # 如果是其他响应，继续等待
                    time.sleep(30)
                    
                except Exception as e:
                    self._log(f"[WARN] 后台任务查询异常: {e}")
                    time.sleep(30)
            
            # 超过最大重试次数
            self._log(f"[WARN] 后台任务等待超时: {chat_id}")
            self.reply_text(chat_id,
                "⏱️ **后台任务状态**\n\n"
                "任务执行时间超过预期，可能仍在运行。\n"
                "请稍后手动询问任务结果。",
                streaming=False)
                
        except Exception as e:
            self._log(f"[ERROR] 后台任务等待线程异常: {e}")
            import traceback
            self._log(traceback.format_exc())
