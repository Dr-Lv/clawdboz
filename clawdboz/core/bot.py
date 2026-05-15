#!/usr/bin/env python3
"""Bot 核心模块 - LarkBot 主类"""

import glob
import json
import os
import re
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor
from typing import Optional

import lark_oapi as lark
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody, PatchMessageRequest, PatchMessageRequestBody

from ..config import CONFIG, get_absolute_path
from ..communication import ACPClient, HistoryManager
from .bot_base import BotBase


class LarkBot(BotBase):
    """飞书 Bot 核心类"""

    def __init__(self, app_id, app_secret, verification_token='', encrypt_key=''):
        # 调用父类初始化
        super().__init__(app_id, app_secret)

        self.verification_token = verification_token
        self.encrypt_key = encrypt_key
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
        
        # 设置内置 skills 到工作目录
        self._setup_builtin_skills()
        
        # 心跳相关配置
        self._heart_beat_interval = int(CONFIG.get('scheduler', {}).get('heart_beat', 30))  # 默认30秒
        self._last_heart_beat_time = time.time()
        self._heart_beat_thread = None
        self._heart_beat_stop_event = threading.Event()
        
        # 汇总相关
        self._last_daily_summary_date = None  # 上次汇总的日期
        
        # 启动心跳线程
        self._start_heart_beat()
    
    def _setup_builtin_skills(self):
        """将内置 skills 复制到工作目录的 .agents/skills"""
        try:
            import shutil
            from pathlib import Path
            
            # 获取工作目录
            workplace_dir = get_absolute_path(CONFIG.get('paths', {}).get('workplace', 'WORKPLACE'))
            
            # 获取包安装目录
            package_dir = Path(__file__).parent.resolve()
            builtin_skills_dir = package_dir / '.agents' / 'skills'
            
            if not builtin_skills_dir.exists():
                self._log("[INIT] 未找到内置 skills 目录")
                return
            
            # 用户工作目录的 skills 路径
            user_skills_dir = Path(workplace_dir) / '.agents' / 'skills'
            
            copied = []
            existing = []
            
            # 遍历内置 skills
            for skill_name in os.listdir(builtin_skills_dir):
                builtin_skill_path = builtin_skills_dir / skill_name
                user_skill_path = user_skills_dir / skill_name
                
                if builtin_skill_path.is_dir():
                    if user_skill_path.exists():
                        existing.append(skill_name)
                    else:
                        shutil.copytree(builtin_skill_path, user_skill_path)
                        copied.append(skill_name)
            
            if copied:
                self._log(f"[INIT] 已复制内置 skills: {', '.join(copied)}")
            if existing:
                self._log(f"[INIT] 已存在 skills: {', '.join(existing)}")
                
        except Exception as e:
            self._log(f"[INIT] 复制内置 skills 失败: {e}")

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

                    # 检测是否 @ Bot（通过 <at> 标签）
                    # 优先使用已知的 Bot user_id
                    if self._bot_user_id:
                        at_pattern = f'<at id="{self._bot_user_id}">'
                        at_pattern_user_id = f'<at id="{self._bot_user_id}"'
                        if at_pattern in current_text or at_pattern_user_id in current_text:
                            is_mentioned = True
                            self._log(f"[DEBUG] 消息内容中检测到 @ Bot (通过 user_id): {at_pattern}")
                    else:
                        # 如果没有已知的 user_id，检测任何 <at id="..."> 标签且 type="app"
                        import re
                        # 匹配 <at id="..." ...> 或 <at id="..."/>
                        at_matches = re.findall(r'<at id="([^"]+)"(?:\s+[^>]*)?>', current_text)
                        self._log(f"[DEBUG] 正则匹配到的所有 @ ID: {at_matches}")
                        for at_id in at_matches:
                            self._log(f"[DEBUG] 检查 @ ID: {at_id}")
                            # 这里我们无法直接知道被 @ 的是不是 Bot，暂时认为只要被 @ 就可能是
                            # 后续可以通过 mentions 字段确认
                            is_mentioned = True
                            self._log(f"[DEBUG] 消息内容中可能包含 @ Bot")
                            break

                except json.JSONDecodeError:
                    self._log(f"[ERROR] 无法解析消息内容 JSON: {msg_content[:100]}")
                    return
                except Exception as e:
                    self._log(f"[ERROR] 处理消息内容时出错: {e}")
                    return

            # 群聊中，如果没有被 @，不回复
            if is_group and not is_mentioned:
                self._log(f"[DEBUG] 群聊消息但未 @ Bot，跳过")
                return

            self._log(f"[HANDLE] 处理 {'群聊' if is_group else '单聊'} 消息, chat_id={chat_id}, is_mentioned={is_mentioned}")

            # 根据消息类型处理
            if msg_type == 'text':
                # 清理文本（去除 @ 标签）
                cleaned_text = current_text
                if self._bot_user_id:
                    # 移除各种形式的 @ Bot
                    patterns = [
                        f'<at id="{self._bot_user_id}"></at>',
                        f'<at id="{self._bot_user_id}"/>',
                        f'<at id="{self._bot_user_id}">@{self._bot_user_id}</at>',
                    ]
                    for pattern in patterns:
                        cleaned_text = cleaned_text.replace(pattern, '')
                else:
                    # 如果没有已知的 user_id，移除所有 <at> 标签
                    import re
                    cleaned_text = re.sub(r'<at[^>]*>([^<]*)</at>', r'\1', cleaned_text)
                    cleaned_text = re.sub(r'<at[^>]*/>', '', cleaned_text)

                cleaned_text = cleaned_text.strip()
                self._log(f"[HANDLE] 清理后的文本: {cleaned_text[:100]}")

                # 提交到线程池异步处理
                self.executor.submit(self._handle_text_message, chat_id, message_id, cleaned_text, is_group)

            elif msg_type == 'image':
                # 处理图片消息
                self.executor.submit(self._handle_image_message, chat_id, message_id, msg_content)

            elif msg_type == 'file':
                # 处理文件消息
                self.executor.submit(self._handle_file_message, chat_id, message_id, msg_content)

            else:
                self._log(f"[WARN] 不支持的消息类型: {msg_type}")

        except Exception as e:
            self._log(f"[ERROR] 处理消息事件时出错: {e}")
            import traceback
            traceback.print_exc()

    def _fetch_bot_user_id(self):
        """获取 Bot 的 user_id（用于精确检测 @）"""
        try:
            # 创建请求
            request = lark.Request()
            request.method = "GET"
            request.url = "https://open.feishu.cn/open-apis/bot/v3/info"
            request.headers = {
                "Authorization": f"Bearer {self._get_tenant_access_token()}"
            }
            
            # 发送请求
            response = self.client.request(request)
            
            if response.code == 0:
                bot_info = response.data.get("bot", {})
                self._bot_user_id = bot_info.get("open_id")
                self._log(f"[INIT] Bot user_id: {self._bot_user_id}")
            else:
                self._log(f"[INIT] 获取 Bot user_id 失败: {response.msg}")
        except Exception as e:
            self._log(f"[INIT] 获取 Bot user_id 异常: {e}")
    
    def _get_tenant_access_token(self) -> str:
        """获取 tenant_access_token"""
        try:
            # 使用 SDK 获取 token
            request = lark.Request()
            request.method = "POST"
            request.url = "https://open.feishu.cn/open-apis/auth/v3/tenant_access_token/internal"
            request.body = {
                "app_id": self.app_id,
                "app_secret": self.app_secret
            }
            
            response = self.client.request(request)
            
            if response.code == 0:
                return response.data.get("tenant_access_token", "")
            else:
                self._log(f"[ERROR] 获取 token 失败: {response.msg}")
                return ""
        except Exception as e:
            self._log(f"[ERROR] 获取 token 异常: {e}")
            return ""
    
    def _start_heart_beat(self):
        """启动心跳线程"""
        if self._heart_beat_thread is not None:
            return  # 已经在运行
        
        self._heart_beat_stop_event.clear()
        self._heart_beat_thread = threading.Thread(target=self._heart_beat_loop, daemon=True)
        self._heart_beat_thread.start()
        # 心跳日志已禁用以减少日志文件大小
        # self._log(f"[HEART_BEAT] 心跳线程已启动，间隔: {self._heart_beat_interval}秒")

    def _heart_beat_loop(self):
        """心跳循环"""
        beat_count = 0
        while not self._heart_beat_stop_event.is_set():
            try:
                beat_count += 1
                # 周期性心跳日志已禁用
                # self._log(f"[HEART_BEAT] 第 {beat_count} 次心跳，开始检查任务...")

                # 调用 scheduler skill 检查任务
                self._check_scheduler_tasks()

                # 检查是否需要执行每日汇总
                self._check_daily_summary()

                # 周期性心跳日志已禁用
                # self._log(f"[HEART_BEAT] 第 {beat_count} 次心跳完成")
                
            except Exception as e:
                self._log(f"[HEART_BEAT] 心跳检查异常: {e}")
                import traceback
                self._log(f"[HEART_BEAT] 异常详情: {traceback.format_exc()}")

            # 避免CPU空转
            time.sleep(self._heart_beat_interval)

    def _check_scheduler_tasks(self):
        """调用 scheduler skill 检查并执行定时任务"""
        try:
            import os
            import glob
            # 添加 skill 路径到 sys.path
            skill_path = get_absolute_path('.agents/skills')
            if skill_path not in sys.path:
                sys.path.insert(0, skill_path)

            from scheduler.scheduler import tick, update_task

            current_time = time.time()
            window_start = self._last_heart_beat_time

            # 指定数据目录为 WORKPLACE
            workplace_dir = get_absolute_path('WORKPLACE')

            # 收集所有可能的任务文件目录
            task_data_dirs = [workplace_dir]  # 根目录（向后兼容）

            # 1. 遍历所有 workplace_*/w_session_* 目录（单聊会话）
            for bot_workplace in glob.glob(os.path.join(workplace_dir, 'workplace_*')):
                if os.path.isdir(bot_workplace):
                    for session_dir in glob.glob(os.path.join(bot_workplace, 'w_session_*')):
                        if os.path.isdir(session_dir):
                            task_data_dirs.append(session_dir)

            # 2. 遍历 groupspace/g_session_* 目录（群聊会话）
            groupspace_dir = os.path.join(workplace_dir, 'groupspace')
            if os.path.isdir(groupspace_dir):
                for session_dir in glob.glob(os.path.join(groupspace_dir, 'g_session_*')):
                    if os.path.isdir(session_dir):
                        task_data_dirs.append(session_dir)

            # 心跳目录扫描日志已禁用

            all_pending_tasks = []

            # 遍历所有目录检查任务
            for data_dir in task_data_dirs:
                try:
                    # 调用 skill 的 tick() 获取待执行任务（传递 bot_id 用于任务隔离）
                    bot_id = getattr(self, '_bot_id', None) or getattr(self, 'bot_id', None)
                    pending_tasks = tick(current_time, window_start, bot_id=bot_id, data_dir=data_dir)
                    if pending_tasks:
                        # 为每个任务记录其所在的 data_dir
                        for task in pending_tasks:
                            task['_data_dir'] = data_dir  # 保存目录信息供执行时使用
                            all_pending_tasks.append(task)
                except Exception as e:
                    self._log(f"[HEART_BEAT] 检查目录失败 {data_dir}: {e}")
                    continue

            # 更新上次检查时间
            self._last_heart_beat_time = current_time

# 心跳日志已禁用（减少日志文件大小）
            #             self._log(f"[HEART_BEAT] 共发现 {len(all_pending_tasks)} 个待执行任务")

            if all_pending_tasks:
# 心跳日志已禁用
                #                 self._log(f"[HEART_BEAT] 开始执行 {len(all_pending_tasks)} 个待执行任务")
                for task in all_pending_tasks:
                    task_id = task['id']
                    data_dir = task.pop('_data_dir', workplace_dir)  # 获取并移除临时字段
                    # 立即更新状态为 running，防止重复执行
                    try:
                        update_task(task_id, data_dir=data_dir, status='running')
# 心跳日志已禁用
                        #                         self._log(f"[HEART_BEAT] 任务 #{task_id} 状态已更新为 running，提交执行 (dir: {data_dir})")
                        # 将 data_dir 传递给执行任务，并附加异常回调防止静默吞掉错误
                        future = self.executor.submit(self._execute_scheduled_task_with_dir, task, data_dir)
                        future.add_done_callback(lambda f: f.result() if not f.exception() else self._log(f"[HEART_BEAT] 任务 #{task_id} 执行线程异常: {f.exception()}"))
                    except Exception as e:
                        self._log(f"[HEART_BEAT] 更新任务 #{task_id} 状态失败: {e}")

        except Exception as e:
            self._log(f"[HEART_BEAT] 检查任务失败: {e}")
            import traceback
            self._log(f"[HEART_BEAT] 异常详情: {traceback.format_exc()}")

    def _execute_scheduled_task_with_dir(self, task: dict, data_dir: str):
        """执行定时任务的包装器，支持传递 data_dir"""
        # 临时修改 _execute_scheduled_task 使用的环境变量
        original_work_dir = os.environ.get('CLAWDBOZ_SESSION_WORK_DIR')
        original_bot_work_dir = os.environ.get('CLAWDBOZ_BOT_WORK_DIR')
        original_mcp_mode = os.environ.get('CLAWDBOZ_MCP_MODE')

        try:
            # 设置正确的环境变量
            os.environ['CLAWDBOZ_SESSION_WORK_DIR'] = data_dir
            # 对于单聊任务，解析 bot_id 并设置 BOT_WORK_DIR
            if 'bot_id' in task:
                bot_id = task['bot_id']
                bot_work_dir = os.path.join(get_absolute_path('WORKPLACE'), f'workplace_{bot_id}')
                if os.path.exists(bot_work_dir):
                    os.environ['CLAWDBOZ_BOT_WORK_DIR'] = bot_work_dir
            # 设置 MCP 模式为 webchat（强制设置，确保在 WebChat 模式下执行）
            os.environ['CLAWDBOZ_MCP_MODE'] = 'webchat'

            # 调用原执行方法
            self._execute_scheduled_task(task)
        finally:
            # 恢复环境变量
            if original_work_dir is not None:
                os.environ['CLAWDBOZ_SESSION_WORK_DIR'] = original_work_dir
            elif 'CLAWDBOZ_SESSION_WORK_DIR' in os.environ:
                del os.environ['CLAWDBOZ_SESSION_WORK_DIR']
            if original_bot_work_dir is not None:
                os.environ['CLAWDBOZ_BOT_WORK_DIR'] = original_bot_work_dir
            elif 'CLAWDBOZ_BOT_WORK_DIR' in os.environ:
                del os.environ['CLAWDBOZ_BOT_WORK_DIR']
            if original_mcp_mode is not None:
                os.environ['CLAWDBOZ_MCP_MODE'] = original_mcp_mode
            elif 'CLAWDBOZ_MCP_MODE' in os.environ:
                del os.environ['CLAWDBOZ_MCP_MODE']

    def _execute_scheduled_task(self, task: dict):
        """执行定时任务（简化方案）
        
        流程：
        1. 保存 user 的 @bot 消息到 history.json
        2. 调用 ACP 获取 bot 回复
        3. 发送 bot 回复到群里
        """
        task_id = task['id']
        chat_id = task['chat_id']
        description = task['description']
        time_interval = task.get('time_interval')
        task_bot_id = task.get('bot_id')

        # 获取当前 bot_id
        current_bot_id = getattr(self, '_bot_id', None) or getattr(self, 'bot_id', None)
        target_bot_id = task_bot_id or current_bot_id or 'default'

        # 设置环境变量
        data_dir = os.environ.get('CLAWDBOZ_SESSION_WORK_DIR') or get_absolute_path('WORKPLACE')
        os.environ['CLAWDBOZ_SESSION_WORK_DIR'] = data_dir
        os.environ['CLAWDBOZ_BOT_WORK_DIR'] = data_dir
        mcp_mode = os.environ.get('CLAWDBOZ_MCP_MODE', 'feishu')

        try:
            skill_path = get_absolute_path('.agents/skills')
            if skill_path not in sys.path:
                sys.path.insert(0, skill_path)
            from scheduler.scheduler import update_task

# 心跳日志已禁用
            #             self._log(f"[HEART_BEAT] 执行任务 #{task_id}: {description[:50]}...")
# 心跳日志已禁用
            #             self._log(f"[HEART_BEAT] 目标 Bot: {target_bot_id}, 模式: {mcp_mode}")

            # 判断是否为群聊：根据 data_dir 是否包含 groupspace
            is_group_chat = 'groupspace' in data_dir
            
            if mcp_mode == 'webchat':
                # WebChat 模式：直接在 bot.py 中处理完整流程
                self._execute_webchat_scheduled_task(
                    task_id, chat_id, description, target_bot_id, is_group_chat, data_dir
                )
            else:
                # 飞书模式：保持原有逻辑
                self._execute_feishu_scheduled_task(task_id, chat_id, description, time_interval, data_dir)

        except Exception as e:
            error_msg = str(e)
# 心跳日志已禁用
            #             self._log(f"[HEART_BEAT] 执行任务 #{task_id} 失败: {error_msg}")
            import traceback
            self._log(f"[HEART_BEAT] 异常详情: {traceback.format_exc()}")
            try:
                from scheduler.scheduler import update_task
                update_task(task_id, data_dir=data_dir, status='failed')
            except:
                pass

    def _get_thinking_mode_from_meta(self, chat_id: str, is_group: bool = True, target_bot_id: str = None) -> bool:
        """从 session.json 或 meta.json 读取思考模式设置"""
        try:
            if is_group:
                # 优先读取 session.json（新格式）
                session_file = os.path.join(
                    get_absolute_path('WORKPLACE'),
                    'groupspace', f'g_{chat_id}', 'session.json'
                )
                # 向后兼容：尝试读取旧的 meta.json
                meta_file = os.path.join(
                    get_absolute_path('WORKPLACE'),
                    'groupspace', f'g_{chat_id}', 'meta.json'
                )
            else:
                # 单聊：使用目标 bot 的 workplace
                bot_id = target_bot_id or getattr(self, '_bot_id', None) or getattr(self, 'bot_id', None) or 'default'
                session_file = os.path.join(
                    get_absolute_path('WORKPLACE'),
                    f'workplace_{bot_id}', f'w_{chat_id}', 'session.json'
                )
                meta_file = os.path.join(
                    get_absolute_path('WORKPLACE'),
                    f'workplace_{bot_id}', f'w_{chat_id}', 'meta.json'
                )

            # 优先尝试 session.json
            if os.path.exists(session_file):
                with open(session_file, 'r', encoding='utf-8') as f:
                    session_data = json.load(f)
                meta = session_data.get('meta', {})
                # 默认为 True（开启思考模式）
                return meta.get('thinking_mode', True)

            # 向后兼容：尝试旧的 meta.json
            if os.path.exists(meta_file):
                with open(meta_file, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                return meta.get('thinking_mode', True)

        except Exception as e:
            self._log(f"[HEART_BEAT] 读取思考模式失败: {e}")

        return True  # 默认开启

    def _execute_webchat_scheduled_task(self, task_id: str, chat_id: str, description: str,
                                        target_bot_id: str, is_group_chat: bool, data_dir: str):
        """WebChat 模式下执行定时任务（使用系统命令调用 CLI）"""
        import subprocess
        from scheduler.scheduler import update_task

        try:
            # 0. 读取会话思考模式
            thinking_mode = self._get_thinking_mode_from_meta(chat_id, is_group_chat, target_bot_id)

            # 1. 构建 user 消息（群聊需要 @bot）
            if is_group_chat:
                user_message = f"@{target_bot_id} {description}"
            else:
                user_message = description

            # 2. 使用系统命令调用 CLI 发送消息（CLI 会自动保存消息到 history）
            try:
                # 从 config.json 读取 webchat 配置
                config_path = os.path.join(get_absolute_path('WORKPLACE'), '..', 'config.json')
                config_path = os.path.abspath(config_path)

                base_url = None
                token = None
                if os.path.exists(config_path):
                    try:
                        with open(config_path, 'r', encoding='utf-8') as f:
                            cfg = json.load(f)
                        webchat_cfg = cfg.get('webchat', {})
                        token = webchat_cfg.get('token', '')
                        port = webchat_cfg.get('port', 8080)
                        use_https = webchat_cfg.get('https', False)
                        protocol = "https" if use_https else "http"
                        base_url = f"{protocol}://localhost:{port}"
                    except Exception as e:
                        self._log(f"[HEART_BEAT] 读取 config.json 失败: {e}")

                if not base_url or not token:
                    raise ValueError("WebChat 配置不完整，请检查 config.json 中的 webchat 配置")

                # 构建命令
                # 使用项目根目录下的 cli_web.py
                project_root = os.path.dirname(config_path) if config_path else get_absolute_path('WORKPLACE')
                cli_web_path = os.path.join(project_root, 'cli_web.py')

                # 如果 cli_web.py 不存在，尝试查找当前工作目录
                if not os.path.exists(cli_web_path):
                    cli_web_path = os.path.abspath('cli_web.py')

                cmd = [
                    sys.executable, cli_web_path,
                    'chat', 'send',
                    chat_id,
                    user_message,
                    '--hide'  # 定时任务默认使用隐藏模式，消息不显示在页面但记录到 history
                ]

                # 如果启用思考模式，添加 --thinking 参数
                if thinking_mode:
                    cmd.append('--thinking')

                self._log(f"[HEART_BEAT] 执行 CLI 命令发送定时任务: chat_id={chat_id}, bot_id={target_bot_id}")
                # 构建命令字符串，消息加双引号
                cmd_str = f"{sys.executable} {cli_web_path} chat send {chat_id} '{user_message}' --hide"
                if thinking_mode:
                    cmd_str += " --thinking"
                self._log(f"[HEART_BEAT] 命令: {cmd_str}")

                # 执行命令，设置超时时间为 60 秒
                result = subprocess.run(
                    cmd,
                    capture_output=True,
                    text=True,
                    timeout=60,
                    cwd=project_root
                )

                if result.returncode == 0:
                    self._log(f"[HEART_BEAT] CLI 命令执行成功")
                    if result.stdout:
                        self._log(f"[HEART_BEAT] 输出: {result.stdout[:200]}")
                else:
                    error_msg = result.stderr or result.stdout or "未知错误"
                    self._log(f"[HEART_BEAT] CLI 命令执行失败: {error_msg[:200]}")

            except subprocess.TimeoutExpired:
                self._log(f"[HEART_BEAT] CLI 命令执行超时")
            except Exception as e:
                self._log(f"[HEART_BEAT] CLI 命令执行异常: {e}")
                import traceback
                self._log(f"[HEART_BEAT] 异常详情: {traceback.format_exc()}")

            # 4. 处理重复任务
            time_interval = None
            # 重新读取任务获取 time_interval
            try:
                from scheduler.scheduler import list_tasks
                tasks = list_tasks(data_dir=data_dir)
                for t in tasks:
                    if t.get('id') == task_id:
                        time_interval = t.get('time_interval')
                        break
            except:
                pass

            if time_interval and time_interval > 0:
                next_time = time.time() + time_interval
                update_task(task_id, data_dir=data_dir, execute_time=next_time, status='pending')
            else:
                update_task(task_id, data_dir=data_dir, status='completed')

        except Exception as e:
            self._log(f"[HEART_BEAT] WebChat 任务执行失败: {e}")
            import traceback
            self._log(f"[HEART_BEAT] 异常详情: {traceback.format_exc()}")
            update_task(task_id, data_dir=data_dir, status='failed')

    def _get_authorized_mention_targets(self, sender_bot_id: str, chat_id: str, mentioned_bots: list) -> list:
        """获取有权限的 @ 目标列表（定时任务用，与 web chat 权限文件保持一致）

        Args:
            sender_bot_id: 发送者 Bot ID
            chat_id: 聊天会话 ID
            mentioned_bots: 被提及的 Bot 列表

        Returns:
            有权限的 Bot ID 列表
        """
        authorized_targets = []

        # 从权限文件加载设置
        file_permissions = {}
        permissions_file = os.path.join(
            get_absolute_path('WORKPLACE'),
            'groupspace', f'g_{chat_id}', '.permissions.json'
        )
        if os.path.exists(permissions_file):
            try:
                with open(permissions_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                    file_permissions = data.get('permissions', {})
                    self._log(f"[CASCADE] 从文件加载权限: {file_permissions}")
            except Exception as e:
                self._log(f"[CASCADE] 加载权限文件失败: {e}")

        for target_id in mentioned_bots:
            # 自己不能 @ 自己
            if target_id == sender_bot_id:
                continue

            # 检查权限
            has_permission = False
            if sender_bot_id in file_permissions and target_id in file_permissions[sender_bot_id]:
                has_permission = True

            if has_permission:
                authorized_targets.append(target_id)
            else:
                self._log(f"[CASCADE] Bot {sender_bot_id} 无权 @ {target_id}，跳过")

        return authorized_targets

    def _check_and_trigger_cascade_for_task(self, chat_id: str, sender_bot_id: str, message: str, thinking_mode: bool = True, max_depth: int = 3, current_depth: int = 0):
        """检查并触发级联回复（定时任务用）

        Args:
            chat_id: 聊天会话 ID
            sender_bot_id: 发送消息的 Bot ID
            message: 消息内容
            thinking_mode: 是否显示思考过程
            max_depth: 最大级联深度
            current_depth: 当前深度
        """
        if current_depth >= max_depth:
            self._log(f"[CASCADE] 达到最大级联深度 {max_depth}，停止")
            return

        # 解析 @ 提及
        mentioned_bots = self._parse_mentions_in_message(message, chat_id)
        if not mentioned_bots:
            return

        # 过滤出有权限的目标
        authorized_targets = self._get_authorized_mention_targets(sender_bot_id, chat_id, mentioned_bots)
        if not authorized_targets:
            self._log(f"[CASCADE] Bot {sender_bot_id} 的回复中 @ 了: {mentioned_bots}，但没有授权的目标")
            return

        self._log(f"[CASCADE] Bot {sender_bot_id} 的回复中 @ 了: {authorized_targets}，深度: {current_depth}")

        for target_bot_id in authorized_targets:
            try:
                self._log(f"[CASCADE] 触发 Bot {target_bot_id} 的级联回复")
                
                # 构建 @ 消息
                mention_message = f"@{target_bot_id} 请继续处理上述话题。"
                
                # 保存 @ 消息到历史
                self._save_message_to_history(chat_id, sender_bot_id, mention_message, True)
                
                # 获取历史上下文
                history = self._get_chat_history_from_file(chat_id, True)
                
                # 构建 prompt
                context_prompt = ""
                if history:
                    context_parts = ["以下是最近聊天记录上下文：\n"]
                    for msg in history[-10:]:
                        if isinstance(msg, dict):
                            sender = msg.get('sender', 'unknown')
                            content = msg.get('content', '')
                            context_parts.append(f"{sender}: {content}")
                    context_prompt = "\n".join(context_parts) + "\n\n"
                
                prompt = f"{context_prompt}用户消息：{mention_message}\n\n请回复上述消息。"
                
                # 调用 ACP 获取回复
                result = self.acp_client.chat(prompt, timeout=120, include_thinking_in_result=thinking_mode)
                
                if result:
                    # 保存回复到历史
                    self._save_message_to_history(chat_id, target_bot_id, result, True)
                    
                    # 发送回复到 WebChat
                    try:
                        bot_work_dir = os.environ.get('CLAWDBOZ_BOT_WORK_DIR') or get_absolute_path('WORKPLACE')
                        skill_path = os.path.join(bot_work_dir, '.agents', 'skills', 'webchat-sender')
                        if skill_path not in sys.path:
                            sys.path.insert(0, skill_path)
                        from webchat_sender import send_message
                        send_message(result, chat_id=chat_id, bot_id=target_bot_id)
                        self._log(f"[CASCADE] Bot {target_bot_id} 的级联回复已发送")
                    except Exception as e:
                        self._log(f"[CASCADE] 发送 Bot {target_bot_id} 回复失败: {e}")
                    
                    # 递归检查级联回复（防止无限递归，限制深度）
                    self._check_and_trigger_cascade_for_task(
                        chat_id, target_bot_id, result, thinking_mode, max_depth, current_depth + 1
                    )
                
            except Exception as e:
                self._log(f"[CASCADE] 触发 Bot {target_bot_id} 级联回复失败: {e}")

    def _parse_mentions_in_message(self, message: str, chat_id: str) -> list:
        """解析消息中的 @ 提及
        
        Args:
            message: 消息内容
            chat_id: 聊天会话 ID
            
        Returns:
            被提及的 Bot ID 列表
        """
        mentioned_bots = []
        if not message:
            self._log(f"[CASCADE] 消息为空，不解析 @ 提及")
            return mentioned_bots
        
        # 从 meta.json 获取可用的 bot_ids
        available_bots = set()
        try:
            meta_file = os.path.join(
                get_absolute_path('WORKPLACE'),
                'groupspace', f'g_{chat_id}', 'meta.json'
            )
            self._log(f"[CASCADE] 读取 meta 文件: {meta_file}")
            if os.path.exists(meta_file):
                with open(meta_file, 'r', encoding='utf-8') as f:
                    meta = json.load(f)
                    available_bots = set(meta.get('bot_ids', []))
                    self._log(f"[CASCADE] 可用 bots: {available_bots}")
            else:
                self._log(f"[CASCADE] meta 文件不存在: {meta_file}")
        except Exception as e:
            self._log(f"[CASCADE] 读取 meta 失败: {e}")
        
        if not available_bots:
            self._log(f"[CASCADE] 没有可用 bots")
            return mentioned_bots
        
        # 匹配 @bot_id
        import re
        mention_pattern = r'@(\w+)'
        matches = re.findall(mention_pattern, message)
        self._log(f"[CASCADE] 消息中匹配到的 @: {matches}")
        
        for match in matches:
            bot_id = match.strip()
            if bot_id in available_bots:
                mentioned_bots.append(bot_id)
                self._log(f"[CASCADE] 找到有效 @: {bot_id}")
        
        self._log(f"[CASCADE] 最终提及列表: {mentioned_bots}")
        return list(set(mentioned_bots))  # 去重

    def _save_message_to_history(self, chat_id: str, sender: str, content: str, is_group: bool):
        """保存消息到 history.json 和 session.json（用于 web 界面同步）"""
        try:
            # 获取 WORKPLACE 根目录
            # 优先使用环境变量，其次使用配置中的路径
            workplace_root = os.environ.get('CLAWDBOZ_BOT_WORK_DIR')
            if not workplace_root:
                workplace_root = CONFIG.get('paths', {}).get('workplace')
            if not workplace_root:
                workplace_root = get_absolute_path('WORKPLACE')
            # 如果 workplace_root 是 workplace_{bot_id}，需要获取其父目录
            if os.path.basename(workplace_root).startswith('workplace_'):
                workplace_root = os.path.dirname(workplace_root)

            # 确定 history.json 路径
            if is_group:
                history_file = os.path.join(
                    workplace_root,
                    'groupspace', f'g_{chat_id}', 'history.json'
                )
                session_file = os.path.join(
                    workplace_root,
                    'groupspace', f'g_{chat_id}', 'session.json'
                )
            else:
                current_bot_id = getattr(self, '_bot_id', None) or getattr(self, 'bot_id', None) or 'default'
                # 飞书会话使用 f_ 前缀（用于与 web 会话 w_ 区分）
                session_dir = os.path.join(
                    workplace_root,
                    f'workplace_{current_bot_id}', f'f_{chat_id}'
                )
                history_file = os.path.join(session_dir, 'history.json')
                session_file = os.path.join(session_dir, 'session.json')

            # 读取现有历史
            history = {"messages": []}
            if os.path.exists(history_file):
                try:
                    with open(history_file, 'r', encoding='utf-8') as f:
                        history = json.load(f)
                except:
                    pass

            # 添加新消息
            if 'messages' not in history:
                history['messages'] = []

            msg_data = {
                "sender": sender,
                "content": content,
                "time": time.time()
            }
            history['messages'].append(msg_data)

            # 保存 history.json
            os.makedirs(os.path.dirname(history_file), exist_ok=True)
            with open(history_file, 'w', encoding='utf-8') as f:
                json.dump(history, f, ensure_ascii=False, indent=2)

            # 同时保存 session.json（用于 web 界面显示）
            try:
                session_data = {"meta": {}, "messages": [], "stats": {}}
                if os.path.exists(session_file):
                    with open(session_file, 'r', encoding='utf-8') as f:
                        session_data = json.load(f)

                # 确保基本结构存在
                if 'meta' not in session_data:
                    session_data['meta'] = {}
                if 'messages' not in session_data:
                    session_data['messages'] = []
                if 'stats' not in session_data:
                    session_data['stats'] = {}

                # 更新 meta（飞书会话标识）
                if not session_data['meta'].get('chat_id'):
                    session_data['meta']['chat_id'] = chat_id
                if not session_data['meta'].get('type'):
                    session_data['meta']['type'] = 'feishu'
                if not session_data['meta'].get('bot_id'):
                    session_data['meta']['bot_id'] = getattr(self, '_bot_id', 'default')
                if not session_data['meta'].get('mode'):
                    session_data['meta']['mode'] = 'single'
                if not session_data['meta'].get('created_at'):
                    session_data['meta']['created_at'] = time.time()
                session_data['meta']['updated_at'] = time.time()

                # 添加消息到 session
                session_data['messages'].append(msg_data)

                # 更新统计
                session_data['stats']['total_messages'] = len(session_data['messages'])

                # 保存 session.json
                with open(session_file, 'w', encoding='utf-8') as f:
                    json.dump(session_data, f, ensure_ascii=False, indent=2)

            except Exception as e:
                self._log(f"[HEART_BEAT] 保存 session.json 失败: {e}")

        except Exception as e:
            self._log(f"[HEART_BEAT] 保存消息到 history 失败: {e}")

    def _execute_feishu_scheduled_task(self, task_id: str, chat_id: str, description: str, time_interval: int, data_dir: str):
        """飞书模式下的定时任务执行（保持原有逻辑）"""
        try:
            skill_path = get_absolute_path('.agents/skills')
            if skill_path not in sys.path:
                sys.path.insert(0, skill_path)
            from scheduler.scheduler import update_task

            # 初始化 ACP 客户端（如果未初始化）
            if self.acp_client is None:
                try:
                    self.acp_client = ACPClient(bot_ref=self)
                    self._log("[DEBUG] ACP 客户端已初始化")
                except Exception as e:
                    self._log(f"[ERROR] ACP 客户端初始化失败: {e}")
                    update_task(task_id, data_dir=data_dir, status='failed')
                    return

            # 获取群聊历史记录作为上下文
            chat_history = []
            is_group_chat = chat_id.startswith('oc_') or chat_id.startswith('g_') or 'session_' in chat_id
            if is_group_chat:
                chat_history = self._get_chat_history_from_file(chat_id, is_group=True)
# 心跳日志已禁用
                #                 self._log(f"[HEART_BEAT] 加载群聊历史: {len(chat_history)} 条消息")

            # 构建带上下文的提示词
            context_prompt = ""
            if chat_history:
                context_parts = ["以下是最近聊天记录上下文：\n"]
                for msg in chat_history[-10:]:
                    if isinstance(msg, dict):
                        sender = msg.get('sender', 'unknown')
                        content = msg.get('content', '')
                        context_parts.append(f"{sender}: {content}")
                    else:
                        context_parts.append(str(msg))
                context_prompt = "\n".join(context_parts) + "\n\n"

            prompt = f"{context_prompt}这是一个定时任务，请执行以下内容并返回结果:\n\n{description}"

            # 调用 ACP 获取结果
            try:
                result = self.acp_client.chat(prompt, timeout=60)
                if not result or '无有效回复' in result or '处理完成' in result:
                    message = f"⏰ **定时任务执行**\n\n{description}"
                else:
                    message = f"⏰ **定时任务提醒**\n\n任务: {description}\n\n{result}"
            except Exception as chat_error:
                self._log(f"[HEART_BEAT] ACP 调用失败: {chat_error}")
                message = f"⏰ **定时任务执行**\n\n{description}"

            # 使用飞书 API 发送
            self.reply_text(chat_id, message, streaming=False)

            # 处理重复任务
            if time_interval and time_interval > 0:
                next_time = time.time() + time_interval
                update_task(task_id, data_dir=data_dir, execute_time=next_time, status='pending')
# 心跳日志已禁用
                #                 self._log(f"[HEART_BEAT] 任务 #{task_id} 已重置，下次执行: {next_time}")
            else:
                update_task(task_id, data_dir=data_dir, status='completed')

            # 心跳日志已禁用（减少日志文件大小）
            # self._log(f"[HEART_BEAT] 任务 #{task_id} 执行完成")

        except Exception as e:
            self._log(f"[HEART_BEAT] 飞书任务执行失败: {e}")
            try:
                from scheduler.scheduler import update_task
                update_task(task_id, data_dir=data_dir, status='failed')
            except:
                pass

    def _get_chat_history_from_file(self, chat_id: str, is_group: bool = False, limit: int = 30) -> list:
        """从历史文件读取聊天记录"""
        try:
            # 获取 WORKPLACE 根目录
            workplace_root = os.environ.get('CLAWDBOZ_BOT_WORK_DIR')
            if not workplace_root:
                workplace_root = CONFIG.get('paths', {}).get('workplace')
            if not workplace_root:
                workplace_root = get_absolute_path('WORKPLACE')
            if os.path.basename(workplace_root).startswith('workplace_'):
                workplace_root = os.path.dirname(workplace_root)

            if is_group:
                history_file = os.path.join(
                    workplace_root,
                    'groupspace', f'g_{chat_id}', 'history.json'
                )
            else:
                current_bot_id = getattr(self, '_bot_id', None) or getattr(self, 'bot_id', None) or 'default'
                # 飞书会话使用 f_ 前缀
                history_file = os.path.join(
                    workplace_root,
                    f'workplace_{current_bot_id}', f'f_{chat_id}', 'history.json'
                )
            
            if not os.path.exists(history_file):
                return []
            
            with open(history_file, 'r', encoding='utf-8') as f:
                data = json.load(f)
            
            if isinstance(data, dict) and 'messages' in data:
                messages = data['messages']
            elif isinstance(data, list):
                messages = data
            else:
                messages = []
            
            return messages[-limit:] if len(messages) > limit else messages
            
        except Exception as e:
            self._log(f"[HEART_BEAT] 读取历史文件失败: {e}")
            return []

    def _check_daily_summary(self):
        """检查是否需要执行每日汇总（每天早上9点）"""
        try:
            from datetime import datetime, time as dt_time
            
            now = datetime.now()
            current_time = now.time()
            
            # 检查是否是早上9点（9:00-9:01之间）
            is_nine_am = (current_time.hour == 9 and current_time.minute == 0)
            
            # 检查今天是否已经汇总过
            today_str = now.strftime('%Y-%m-%d')
            if self._last_daily_summary_date == today_str:
                return
            
            if is_nine_am:
                self._log("[HEART_BEAT] 执行每日任务汇总")
                self._do_daily_summary()
                self._last_daily_summary_date = today_str
                
        except Exception as e:
            self._log(f"[HEART_BEAT] 每日汇总检查失败: {e}")

    def _do_daily_summary(self):
        """执行每日任务汇总（使用 skill）"""
        try:
            skill_path = get_absolute_path('.agents/skills')
            if skill_path not in sys.path:
                sys.path.insert(0, skill_path)
            from scheduler.scheduler import list_tasks
            
            # 指定数据目录
            data_dir = get_absolute_path('WORKPLACE')
            
            # 获取所有 failed 和 running 状态的任务
            all_tasks = list_tasks(data_dir=data_dir)
            failed_tasks = [t for t in all_tasks if t.get('status') == 'failed']
            running_tasks = [t for t in all_tasks if t.get('status') == 'running']
            
            if not failed_tasks and not running_tasks:
                self._log("[HEART_BEAT] 没有未成功的任务需要汇总")
                return
            
            # 按 chat_id 分组
            from collections import defaultdict
            chat_tasks = defaultdict(list)
            
            for task in failed_tasks + running_tasks:
                chat_tasks[task.get('chat_id')].append(task)
            
            # 向每个聊天发送汇总消息
            for chat_id, tasks_list in chat_tasks.items():
                message_lines = ["📊 **每日任务执行汇总**", ""]
                message_lines.append(f"共有 {len(tasks_list)} 个任务未成功执行：")
                message_lines.append("")
                
                for i, task in enumerate(tasks_list, 1):
                    desc = task.get('description', '无描述')[:50]
                    status = task.get('status', '未知')
                    
                    message_lines.append(f"{i}. {desc}")
                    message_lines.append(f"   状态: {status}")
                    message_lines.append("")
                
                message_lines.append("请检查这些任务并重试。")
                
                message = "\n".join(message_lines)
                self.reply_text(chat_id, message, streaming=False)
            
# 心跳日志已禁用
            #             self._log(f"[HEART_BEAT] 已发送每日汇总到 {len(chat_tasks)} 个聊天")
            
        except Exception as e:
            self._log(f"[HEART_BEAT] 每日汇总执行失败: {e}")

    def reply_text(self, chat_id: str, text: str, streaming: bool = False) -> str:
        """发送文本消息到飞书"""
        try:
            # 创建请求（新版本的 lark_oapi，receive_id 在 request_body 中）
            request = CreateMessageRequest.builder() \
                .receive_id_type("chat_id") \
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type("text")
                    .content(json.dumps({"text": text}))
                    .build()
                ) \
                .build()
            
            # 发送请求
            response = self.client.im.v1.message.create(request)
            
            if response.code == 0:
                message_id = response.data.message_id
                self._log(f"[REPLY] 消息已发送: {message_id}")
                return message_id
            else:
                self._log(f"[REPLY] 发送失败: {response.msg}")
                return ""
                
        except Exception as e:
            self._log(f"[REPLY] 发送异常: {e}")
            return ""

    def reply_with_card(self, chat_id: str, title: str, content: str, streaming: bool = False) -> str:
        """
        发送卡片消息到飞书

        Args:
            chat_id: 聊天 ID
            title: 卡片标题
            content: 卡片内容（支持 Markdown）
            streaming: 是否为流式消息（会先发送占位卡片，后续可更新）

        Returns:
            message_id: 消息 ID，用于后续更新
        """
        try:
            # 构建卡片内容
            card_content = {
                "config": {
                    "wide_screen_mode": True
                },
                "header": {
                    "title": {
                        "tag": "plain_text",
                        "content": title
                    },
                    "template": "blue"
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": content
                        }
                    }
                ]
            }

            # 创建请求
            request = CreateMessageRequest.builder() \
                .receive_id_type("chat_id") \
                .request_body(
                    CreateMessageRequestBody.builder()
                    .receive_id(chat_id)
                    .msg_type("interactive")
                    .content(json.dumps(card_content))
                    .build()
                ) \
                .build()

            # 发送请求
            response = self.client.im.v1.message.create(request)

            if response.code == 0:
                message_id = response.data.message_id
                self._log(f"[CARD] 卡片已发送: {message_id}")
                return message_id
            else:
                self._log(f"[CARD] 发送失败: {response.msg}")
                return ""

        except Exception as e:
            self._log(f"[CARD] 发送异常: {e}")
            return ""

    def send_message(self, chat_id: str, message: str) -> bool:
        """
        发送文本消息（实现 BotBase 抽象方法）

        Args:
            chat_id: 会话 ID
            message: 消息内容

        Returns:
            是否发送成功
        """
        return self.reply_text(chat_id, message) != ""

    def send_message_card(self, chat_id: str, title: str, content: str) -> bool:
        """
        发送消息卡片（实现 BotBase 抽象方法）

        Args:
            chat_id: 会话 ID
            title: 标题
            content: 内容

        Returns:
            是否发送成功
        """
        return self.reply_with_card(chat_id, title, content) != ""

    def update_card(self, message_id: str, content: str, title: str = None, finished: bool = False) -> bool:
        """
        更新已发送的卡片消息

        Args:
            message_id: 消息 ID
            content: 新的卡片内容（支持 Markdown）
            title: 新的卡片标题（可选）
            finished: 是否已完成（会改变卡片样式）

        Returns:
            bool: 是否更新成功
        """
        try:
            # 构建卡片内容
            card_content = {
                "config": {
                    "wide_screen_mode": True
                },
                "elements": [
                    {
                        "tag": "div",
                        "text": {
                            "tag": "lark_md",
                            "content": content
                        }
                    }
                ]
            }

            # 添加标题（如果提供）
            if title:
                card_content["header"] = {
                    "title": {
                        "tag": "plain_text",
                        "content": title
                    },
                    "template": "green" if finished else "blue"
                }

            # 创建更新请求
            request = PatchMessageRequest.builder() \
                .message_id(message_id) \
                .request_body(
                    PatchMessageRequestBody.builder()
                    .content(json.dumps(card_content))
                    .build()
                ) \
                .build()

            # 发送更新请求
            response = self.client.im.v1.message.patch(request)

            if response.code == 0:
                return True
            else:
                self._log(f"[UPDATE] 更新失败: {response.msg}")
                return False

        except Exception as e:
            self._log(f"[UPDATE] 更新异常: {e}")
            return False

    def chat(self, message: str) -> str:
        """直接调用 ACP 进行对话（简化版）"""
        try:
            # 初始化 ACP 客户端（如果未初始化）
            if self.acp_client is None:
                self.acp_client = ACPClient(bot_ref=self)

            # 调用 ACP
            result = self.acp_client.chat(message, timeout=60)
            return result if result else "[无回复]"

        except Exception as e:
            self._log(f"[CHAT] 调用失败: {e}")
            return f"[调用失败: {e}]"

    def _handle_text_message(self, chat_id, message_id, text, is_group):
        """处理文本消息"""
        try:
            self._log(f"[DEBUG] 处理文本消息, chat_id={chat_id}, text={text[:100]}")

            # 保存消息到历史记录
            self._save_message_to_history(chat_id, "user", text, is_group)

            # 检查是否是特殊命令
            if text.strip() == "/clear":
                self._log(f"[DEBUG] 收到 /clear 命令")
                self.reply_text(chat_id, "🗑️ 上下文已清除", streaming=False)
                return

            # 处理待处理的图片或文件
            if hasattr(self, '_pending_image') and chat_id in self._pending_image:
                image_path = self._pending_image[chat_id]
                if os.path.exists(image_path):
                    prompt = f"用户发送了一张图片，路径为: {image_path}\n\n用户对图片的指令: {text}\n\n请根据用户的指令分析处理这张图片。"
                    self._log(f"[DEBUG] 将图片和消息一起发送给 ACP: {image_path}")
                    # 这里应该调用 ACP 处理，但暂时简化处理
                    self.reply_text(chat_id, f"收到图片和指令: {text}", streaming=False)
                del self._pending_image[chat_id]
            elif hasattr(self, '_pending_file') and chat_id in self._pending_file:
                file_path = self._pending_file[chat_id]
                if os.path.exists(file_path):
                    prompt = f"用户发送了一个文件，路径为: {file_path}\n\n用户对文件的指令: {text}\n\n请根据用户的指令分析处理这个文件。"
                    self._log(f"[DEBUG] 将文件和消息一起发送给 ACP: {file_path}")
                    self.reply_text(chat_id, f"收到文件和指令: {text}", streaming=False)
                del self._pending_file[chat_id]
            else:
                # 普通文本消息 - 使用流式卡片输出
                # 获取历史记录
                history = self._get_chat_history_from_file(chat_id, is_group)

                # 构建 prompt
                context_prompt = ""
                if history:
                    context_prompt = "历史对话:\n"
                    for msg in history[-10:]:  # 最近10条
                        sender = msg.get('sender', 'unknown')
                        content = msg.get('content', '')
                        context_prompt += f"{sender}: {content}\n"
                    context_prompt += "\n"

                final_prompt = f"{context_prompt}用户: {text}\n\n请回复用户的问题。"

                # 调用 ACP 处理
                self._log(f"[DEBUG] 发送给 ACP 的 prompt: {final_prompt[:200]}")

                # 初始化 ACP 客户端（如果未初始化）
                if self.acp_client is None:
                    from .acp_client import ACPClient
                    self.acp_client = ACPClient(bot_ref=self)

                # 先发送一个初始卡片（显示正在生成）
                card_message_id = self.reply_with_card(
                    chat_id,
                    title="💭 正在思考...",
                    content="⏳ 正在生成回复，请稍候...",
                    streaming=True
                )

                if not card_message_id:
                    # 卡片发送失败，回退到普通文本
                    self._log("[ERROR] 发送初始卡片失败，使用普通文本模式")
                    try:
                        response = self.acp_client.chat(final_prompt, timeout=120)
                        if response:
                            self.reply_text(chat_id, response, streaming=False)
                        else:
                            self.reply_text(chat_id, "抱歉，我没有生成回复。", streaming=False)
                    except Exception as e:
                        self._log(f"[ERROR] ACP 调用失败: {e}")
                        self.reply_text(chat_id, f"❌ 处理失败: {str(e)}", streaming=False)
                    return

                # 使用流式方式获取回复
                last_content = ""  # 记录上次回调的内容
                last_update_time = time.time()
                update_interval = 0.5  # 每0.5秒更新一次卡片

                def on_chunk(chunk_text):
                    """处理流式内容片段 - chunk_text 是完整内容"""
                    nonlocal last_content, last_update_time

                    # chunk_text 已经是完整内容，直接使用
                    last_content = chunk_text

                    # 按间隔更新卡片
                    current_time = time.time()
                    if current_time - last_update_time >= update_interval:
                        # 添加光标效果
                        display_content = chunk_text + "▌"
                        self.update_card(card_message_id, display_content, title="💭 正在思考...")
                        last_update_time = current_time

                def on_thinking(thinking_text):
                    """处理思考过程"""
                    # 可选：将思考过程也显示在卡片中
                    pass

                try:
                    # 调用 ACP 获取流式回复
                    response = self.acp_client.chat(
                        final_prompt,
                        on_chunk=on_chunk,
                        on_thinking=on_thinking,
                        timeout=120
                    )

                    # 最终更新卡片（移除光标，标记完成）
                    final_content = last_content if last_content else response
                    if final_content:
                        self.update_card(
                            card_message_id,
                            final_content,
                            title="✅ 回复完成",
                            finished=True
                        )
                        # 保存到历史记录
                        self._save_message_to_history(chat_id, "assistant", final_content, is_group)
                    else:
                        self.update_card(
                            card_message_id,
                            "抱歉，我没有生成回复。",
                            title="⚠️ 回复为空",
                            finished=True
                        )

                except Exception as e:
                    self._log(f"[ERROR] ACP 流式调用失败: {e}")
                    self.update_card(
                        card_message_id,
                        f"❌ 处理失败: {str(e)}",
                        title="❌ 处理失败",
                        finished=True
                    )

        except Exception as e:
            self._log(f"[ERROR] 处理文本消息异常: {e}")
            self.reply_text(chat_id, f"❌ 处理消息失败: {str(e)}", streaming=False)

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
            if not hasattr(self, '_pending_image'):
                self._pending_image = {}
            self._pending_image[chat_id] = image_path
            self._log(f"[DEBUG] 已保存用户图片，等待下一步指令: {image_path}")

            # 图片获取成功，回复用户并询问接下来要做什么
            self.update_card(initial_message_id, f"✅ **收到图片！**\n\n请告诉我您想对这张图片做什么？\n\n例如：\n- 分析图片内容\n- 提取图片中的文字\n- 描述图片场景\n- 其他需求请直接告诉我")

        except Exception as e:
            self._log(f"[ERROR] 处理图片异常: {e}")
            self.reply_text(chat_id, f"❌ 处理图片失败: {str(e)}", streaming=False)

    def _handle_file_message(self, chat_id, message_id, msg_content):
        """处理文件消息 - 使用 messages/:message_id/resources/:file_key 接口"""
        try:
            # 解析文件信息
            import json
            try:
                content_dict = json.loads(msg_content)
                file_key = content_dict.get('file_key', '')
                file_name = content_dict.get('file_name', 'unknown')
            except:
                file_key = msg_content
                file_name = 'unknown'

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
            if not hasattr(self, '_pending_file'):
                self._pending_file = {}
            self._pending_file[chat_id] = file_path
            self._log(f"[DEBUG] 已保存用户文件，等待下一步指令: {file_path}")

            # 文件获取成功，回复用户并询问接下来要做什么
            self.update_card(initial_message_id, f"✅ **收到文件: {file_name}！**\n\n请告诉我您想对这个文件做什么？\n\n例如：\n- 分析文件内容\n- 总结文件要点\n- 提取关键信息\n- 其他需求请直接告诉我")

        except Exception as e:
            self._log(f"[ERROR] 处理文件异常: {e}")
            self.reply_text(chat_id, f"❌ 处理文件失败: {str(e)}", streaming=False)
