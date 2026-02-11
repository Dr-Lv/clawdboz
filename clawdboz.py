# install: pip install lark-oapi
import lark_oapi as lark
from lark_oapi.api.im.v1 import CreateMessageRequest, CreateMessageRequestBody
import json
import subprocess
import os
import threading
import time
from concurrent.futures import ThreadPoolExecutor

class ACPClient:
    """Kimi Code CLI ACP 客户端"""
    def __init__(self, bot_ref=None):
        self.process = None
        self.response_map = {}
        self.notifications = []
        self._lock = threading.Lock()
        self._reader_thread = None
        self._bot_ref = bot_ref  # 保存 bot 引用，用于日志
        self._initialize()

    def _log(self, message):
        """通过 bot 写入日志"""
        if self._bot_ref:
            self._bot_ref._log(f"[ACP] {message}")
        else:
            print(f"[ACP] {message}")

    def _initialize(self):
        """初始化 ACP 连接，自动加载项目目录下的 MCP 配置和 skills"""
        self.process = subprocess.Popen(
            ['kimi', 'acp'],
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            bufsize=1
        )

        # 启动响应读取线程
        self._reader_thread = threading.Thread(target=self._read_responses, daemon=True)
        self._reader_thread.start()

        # 初始化协议
        init_result, init_error = self.call_method('initialize', {'protocolVersion': 1})
        self._log(f"初始化结果: {init_result}, 错误: {init_error}")

        # 加载项目目录下的 MCP 配置
        mcp_servers = self._load_mcp_config()
        
        # 加载项目目录下的 skills
        skills = self._load_skills()
        
        # 创建新会话
        session_params = {
            'cwd': os.getcwd(),
            'mcpServers': mcp_servers
        }
        if skills:
            session_params['skills'] = skills
            
        self._log(f"[ACP] 创建会话，cwd: {os.getcwd()}, MCP服务器: {[s.get('name') for s in mcp_servers]}, Skills: {len(skills)}")
        result, error = self.call_method('session/new', session_params)
        if error:
            raise Exception(f"创建会话失败: {error}")
        self.session_id = result['sessionId']
        self._log(f"ACP 会话创建成功: {self.session_id}")
    
    def _load_mcp_config(self):
        """加载项目目录下的 MCP 配置文件 (.kimi/mcp.json)
        
        返回格式为列表，每个元素包含 name、type 和配置信息
        注意：根据 Kimi ACP 协议，headers 需要是列表格式
        """
        mcp_config_path = os.path.join(os.getcwd(), '.kimi', 'mcp.json')
        if not os.path.exists(mcp_config_path):
            self._log(f"[ACP] 未找到 MCP 配置文件: {mcp_config_path}")
            return []
        
        try:
            with open(mcp_config_path, 'r', encoding='utf-8') as f:
                config = json.load(f)
            mcp_servers_dict = config.get('mcpServers', {})
            # 转换为列表格式，并添加必需的字段
            mcp_servers = []
            for name, server_config in mcp_servers_dict.items():
                server_info = {
                    'name': name,
                    'type': 'http',  # 默认为 http 类型
                    'headers': []    # 默认空 headers 列表
                }
                # 根据配置自动推断类型
                if 'url' in server_config:
                    url = server_config['url']
                    if '/sse' in url or url.endswith('/sse'):
                        server_info['type'] = 'sse'
                server_info.update(server_config)
                # 确保 headers 是列表
                if 'headers' in server_info and isinstance(server_info['headers'], dict):
                    headers_list = []
                    for key, value in server_info['headers'].items():
                        headers_list.append({'name': key, 'value': value})
                    server_info['headers'] = headers_list
                elif 'headers' not in server_info:
                    server_info['headers'] = []
                mcp_servers.append(server_info)
            self._log(f"[ACP] 加载 MCP 配置成功，服务器数量: {len(mcp_servers)}")
            return mcp_servers
        except Exception as e:
            self._log(f"[ACP] 加载 MCP 配置失败: {e}")
            return []
    
    def _load_skills(self):
        """加载项目目录下的 skills (.kimi/skills/)"""
        skills_dir = os.path.join(os.getcwd(), '.kimi', 'skills')
        if not os.path.exists(skills_dir):
            self._log(f"[ACP] 未找到 skills 目录: {skills_dir}")
            return []
        
        skills = []
        try:
            for item in os.listdir(skills_dir):
                skill_path = os.path.join(skills_dir, item)
                if os.path.isdir(skill_path):
                    # 检查是否有 SKILL.md 文件
                    skill_md = os.path.join(skill_path, 'SKILL.md')
                    if os.path.exists(skill_md):
                        skills.append({
                            'name': item,
                            'path': skill_path
                        })
            self._log(f"[ACP] 加载 Skills 成功，数量: {len(skills)}")
            return skills
        except Exception as e:
            self._log(f"[ACP] 加载 Skills 失败: {e}")
            return []

    def _read_responses(self):
        """持续读取响应"""
        for line in self.process.stdout:
            line = line.strip()
            if not line:
                continue
            try:
                response = json.loads(line)
                msg_id = response.get('id')
                method = response.get('method')

                # 处理权限请求 - 自动批准工具调用
                # 注意: id 可能是 0，所以不能用 "if msg_id" 来判断
                if method == 'session/request_permission' and 'id' in response:
                    self._log(f"收到权限请求: {msg_id}")
                    # 自动批准
                    approve_response = {
                        "jsonrpc": "2.0",
                        "id": msg_id,
                        "result": {
                            "outcome": {
                                "outcome": "selected",
                                "option_id": "approve"  # 允许本次
                            }
                        }
                    }
                    try:
                        self.process.stdin.write(json.dumps(approve_response) + '\n')
                        self.process.stdin.flush()
                        self._log(f"自动批准权限请求: {msg_id}")
                    except Exception as e:
                        self._log(f"发送批准响应失败: {e}")
                    continue

                # 处理通知（无 id 的消息）
                if method and msg_id is None:
                    with self._lock:
                        self.notifications.append(response)
                    # 如果是 session/update 通知，打印内容
                    if method == 'session/update':
                        params = response.get('params', {})
                        update = params.get('update', {})
                        update_type = update.get('sessionUpdate')

                        if update_type == 'agent_message_chunk':
                            content = update.get('content', {})
                            if content.get('type') == 'text':
                                text = content.get('text', '')
                                self._log(f"[ACP RAW] 消息 chunk: {repr(text)}")
                                print(f"[ACP] 消息: {text[:100]}...")

                        elif update_type == 'thinking' or update_type == 'agent_thought_chunk':
                            # 思考内容
                            content = update.get('content', {})
                            if content.get('type') == 'text':
                                text = content.get('text', '')
                                self._log(f"[ACP RAW] 思考 chunk: {repr(text)}")
                                print(f"[ACP] 思考: {text[:100]}...")

                        elif update_type == 'tool_call':
                            # 工具调用开始
                            tool_call_id = update.get('toolCallId', '')
                            title = update.get('title', 'Unknown Tool')
                            print(f"[ACP] 工具调用: {title} ({tool_call_id})")

                        elif update_type == 'tool_call_update':
                            # 工具调用状态更新
                            tool_call_id = update.get('toolCallId', '')
                            status = update.get('status', '')
                            print(f"[ACP] 工具状态: {tool_call_id} -> {status}")

                            # 如果工具完成，提取结果内容
                            if status == 'completed' or status == 'failed':
                                content = update.get('content', [])
                                if content:
                                    print(f"[ACP] 工具结果: {content[:200] if len(str(content)) > 200 else content}...")

                    continue

                # 处理请求响应
                if msg_id is not None:
                    with self._lock:
                        self.response_map[msg_id] = response
            except json.JSONDecodeError as e:
                print(f"[DEBUG] JSON 解析错误: {e}, 行: {line}")
            except Exception as e:
                print(f"[DEBUG] 读取响应错误: {e}")

    def call_method(self, method, params, timeout=120):
        """调用 ACP 方法"""
        import uuid
        msg_id = str(uuid.uuid4())
        request = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method,
            "params": params
        }

        # 发送请求
        try:
            self.process.stdin.write(json.dumps(request) + '\n')
            self.process.stdin.flush()
            self._log(f"发送请求: {method}, id: {msg_id[:8]}...")
        except Exception as e:
            return None, f"发送请求失败: {str(e)}"

        # 等待响应
        start_time = time.time()
        while time.time() - start_time < timeout:
            with self._lock:
                if msg_id in self.response_map:
                    response = self.response_map.pop(msg_id)
                    if 'error' in response:
                        self._log(f"收到错误响应: {response['error']}")
                        return None, response['error']
                    self._log(f"收到响应: {list(response.keys())[:3]}...")
                    return response.get('result'), None
            time.sleep(0.05)

        self._log(f"请求超时: {method}")
        return None, "请求超时"

    def chat(self, message, on_chunk=None, timeout=120):
        """发送聊天消息，支持流式接收"""
        # 收集思考内容、工具调用和消息内容
        collected_thinking = []
        collected_tools = {}  # 使用字典存储工具调用，key 为 tool_call_id
        collected_messages = []
        processed_notifications = set()  # 跟踪已处理的通知

        # 清空旧的通知
        with self._lock:
            self.notifications.clear()

        # 记录开始时间
        chat_start_time = time.time()
        last_chunk_time = chat_start_time

        # 发送 prompt（不等待响应，直接开始监听通知）
        import uuid
        msg_id = str(uuid.uuid4())
        request = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": "session/prompt",
            "params": {
                'sessionId': self.session_id,
                'prompt': [{'type': 'text', 'text': message}]
            }
        }
        
        try:
            self.process.stdin.write(json.dumps(request) + '\n')
            self.process.stdin.flush()
            self._log(f"[CHAT] 发送 prompt: {msg_id[:8]}...")
        except Exception as e:
            return f"发送请求失败: {str(e)}"

        # 等待响应完成（检查 stopReason）
        last_callback_text = ""  # 记录上次回调的内容，避免重复调用
        result = None
        
        while time.time() - chat_start_time < timeout:
            time.sleep(0.01)  # 更短的睡眠间隔，更快响应

            # 快速获取锁，复制新通知，然后释放锁
            new_notifications = []
            unprocessed_count = 0
            with self._lock:
                # 检查是否有 prompt 的响应
                if result is None and msg_id in self.response_map:
                    result = self.response_map.pop(msg_id)
                    if 'error' in result:
                        self._log(f"[CHAT] 收到错误响应: {result['error']}")
                        return f"错误: {result['error']}"
                    result = result.get('result')
                    self._log(f"[CHAT] 收到 prompt 响应")
                
                # 只获取未处理的通知
                current_count = len(self.notifications)
                unprocessed_count = current_count - len(processed_notifications)
                if unprocessed_count > 0:
                    for idx in range(len(processed_notifications), current_count):
                        new_notifications.append(self.notifications[idx])
                        processed_notifications.add(idx)
            
            if unprocessed_count > 0:
                self._log(f"[CHAT] 获取 {unprocessed_count} 个新通知")
            
            # 在锁外处理通知（不阻塞 _read_responses）
            # 分批处理，每批最多10个通知，每批处理后回调
            batch_size = 10
            for i in range(0, len(new_notifications), batch_size):
                batch = new_notifications[i:i+batch_size]
                
                for notification in batch:
                    params = notification.get('params', {})
                    update = params.get('update', {})
                    update_type = update.get('sessionUpdate')

                    if update_type == 'thinking' or update_type == 'agent_thought_chunk':
                        content = update.get('content', {})
                        if content.get('type') == 'text':
                            text = content.get('text', '')
                            if text:
                                collected_thinking.append(text)
                                last_chunk_time = time.time()

                    elif update_type == 'tool_call':
                        tool_call_id = update.get('toolCallId', '')
                        title = update.get('title', 'Unknown Tool')
                        kind = update.get('kind', 'other')
                        collected_tools[tool_call_id] = {
                            'id': tool_call_id,
                            'title': title,
                            'kind': kind,
                            'status': 'pending',
                            'start_time': time.time()  # 记录工具开始时间
                        }
                        last_chunk_time = time.time()
                        self._log(f"[CHAT] 工具调用开始: {title} ({tool_call_id[:8]}...)")

                    elif update_type == 'tool_call_update':
                        tool_call_id = update.get('toolCallId', '')
                        status = update.get('status', '')
                        if tool_call_id in collected_tools:
                            old_status = collected_tools[tool_call_id]['status']
                            collected_tools[tool_call_id]['status'] = status
                            # 当状态变为 in_progress 时，更新开始时间
                            if status == 'in_progress' and old_status != 'in_progress':
                                collected_tools[tool_call_id]['start_time'] = time.time()
                            # 当状态变为 completed 时，记录完成时间
                            if status == 'completed' and old_status != 'completed':
                                collected_tools[tool_call_id]['complete_time'] = time.time()
                            # 只在状态变化时记录
                            if old_status != status:
                                self._log(f"[CHAT] 工具状态变化: {tool_call_id[:8]}... {old_status} -> {status}")
                        last_chunk_time = time.time()

                    elif update_type == 'agent_message_chunk':
                        content = update.get('content', {})
                        if content.get('type') == 'text':
                            text = content.get('text', '')
                            if text:
                                collected_messages.append(text)
                                last_chunk_time = time.time()

                # 每批处理后回调（流式更新）
                if on_chunk:
                    thinking_text = ''.join(collected_thinking).strip()
                    message_text = ''.join(collected_messages).strip()

                    # 构建工具调用显示
                    tools_text = ""
                    if collected_tools:
                        tools_text = "\n\n🔧 **工具调用**\n"
                        for tool in collected_tools.values():
                            status_emoji = {
                                'pending': '⏳',
                                'in_progress': '🔄',
                                'completed': '✅',
                                'failed': '❌'
                            }.get(tool['status'], '📌')
                            tools_text += f"- {status_emoji} {tool['title']}\n"

                    # 组合最终内容
                    combined_parts = []
                    if thinking_text:
                        combined_parts.append(f"💭 **思考过程**\n```\n{thinking_text}\n```")
                    if tools_text:
                        combined_parts.append(tools_text)
                    if message_text:
                        combined_parts.append(message_text)

                    # 确保至少有一些内容
                    if not combined_parts:
                        combined_parts.append("⏳ 处理中...")

                    callback_data = '\n\n'.join(combined_parts)
                    
                    # 只有内容变化时才回调
                    if callback_data != last_callback_text:
                        self._log(f"[CHAT] 触发 on_chunk, 内容长度: {len(callback_data)}")
                        on_chunk(callback_data)
                        last_callback_text = callback_data

            # 检查是否有工具正在运行（提前检查，供后续使用）
            has_in_progress_tool = any(
                tool.get('status') == 'in_progress' 
                for tool in collected_tools.values()
            )
            
            # 检查是否完成（result 会有 stopReason）
            # 注意：收到 stopReason 后不要立即退出，给流式通知处理时间
            if result and isinstance(result, dict):
                stop_reason = result.get('stopReason')
                if stop_reason:
                    # 如果还有工具在运行，继续等待，不要退出
                    if has_in_progress_tool:
                        self._log(f"[CHAT] 收到 stopReason: {stop_reason}，但工具仍在运行，继续等待...")
                    # 如果收到了 stopReason 且没有工具在运行，等待3秒确保收集完所有通知
                    elif time.time() - last_chunk_time > 3:  # 3秒
                        self._log(f"[CHAT] 收到 stopReason: {stop_reason}，且工具已完成，退出")
                        break
            
            # 计算工具运行时间，以及最后一个工具完成的时间
            tool_running_time = 0
            last_tool_complete_time = 0
            if collected_tools:
                for tool in collected_tools.values():
                    if tool.get('status') == 'in_progress' and 'start_time' in tool:
                        run_time = time.time() - tool['start_time']
                        if run_time > tool_running_time:
                            tool_running_time = run_time
                    elif tool.get('status') == 'completed' and 'start_time' in tool:
                        # 记录最后一个完成工具的时间
                        complete_time = tool.get('complete_time', 0)
                        if complete_time > last_tool_complete_time:
                            last_tool_complete_time = complete_time
            
            # 如果所有工具都完成了，记录当前时间为最后完成时间（用于后续判断）
            if collected_tools and not has_in_progress_tool and all(
                t.get('status') == 'completed' for t in collected_tools.values()
            ):
                if not hasattr(self, '_all_tools_completed_time'):
                    self._all_tools_completed_time = time.time()
                    self._log(f"[CHAT] 所有工具已完成，开始缓冲期...")
            else:
                # 重置标记
                if hasattr(self, '_all_tools_completed_time'):
                    delattr(self, '_all_tools_completed_time')
            
            # 统一超时时间：5分钟（300秒）
            TIMEOUT_5_MIN = 300
            
            # 检查是否处于工具完成后的缓冲期（给5分钟让服务器发送后续消息）
            tools_completed_buffer = 0
            if hasattr(self, '_all_tools_completed_time'):
                tools_completed_buffer = time.time() - self._all_tools_completed_time
            
            # 如果超过 5 分钟没有新 chunk，且没有正在运行的工具，且不在缓冲期内，认为已完成
            idle_time = time.time() - last_chunk_time
            if (idle_time > TIMEOUT_5_MIN and not has_in_progress_tool and 
                tools_completed_buffer > TIMEOUT_5_MIN and  # 所有工具完成后至少等5分钟
                (collected_thinking or collected_tools or collected_messages)):
                self._log(f"[CHAT] 5分钟无新内容，工具已完成{tools_completed_buffer:.1f}秒，准备退出...")
                # 退出前等待一小段时间，确保所有通知都被处理
                exit_wait_start = time.time()
                while time.time() - exit_wait_start < 10:  # 最后确认等待10秒
                    time.sleep(0.05)
                    # 检查是否还有新通知
                    with self._lock:
                        current_count = len(self.notifications)
                        unprocessed = current_count - len(processed_notifications)
                        if unprocessed > 0:
                            # 有新通知，重置等待时间
                            self._log(f"[CHAT] 退出前发现 {unprocessed} 个新通知，继续处理")
                            break
                else:
                    # 10秒内没有新通知，可以安全退出
                    self._log(f"[CHAT] 确认无新内容，退出")
                    # 清理标记
                    if hasattr(self, '_all_tools_completed_time'):
                        delattr(self, '_all_tools_completed_time')
                    break
            elif has_in_progress_tool and tool_running_time > TIMEOUT_5_MIN:
                # 有工具运行超过5分钟，提示超时
                self._log(f"[CHAT] 工具运行超过5分钟，提示超时")
                timeout_warning = "\n\n⚠️ **提示**：部分工具调用耗时过长（超过5分钟），可能已超时。如未收到完整结果，请重试。"
                collected_messages.append(timeout_warning)
                break
        
        # 退出前最后处理一次所有剩余通知
        self._log(f"[CHAT] 最后处理剩余通知...")
        with self._lock:
            current_count = len(self.notifications)
            if current_count > len(processed_notifications):
                for idx in range(len(processed_notifications), current_count):
                    notification = self.notifications[idx]
                    params = notification.get('params', {})
                    update = params.get('update', {})
                    update_type = update.get('sessionUpdate')
                    
                    if update_type == 'thinking' or update_type == 'agent_thought_chunk':
                        content = update.get('content', {})
                        if content.get('type') == 'text':
                            collected_thinking.append(content.get('text', ''))
                    elif update_type == 'agent_message_chunk':
                        content = update.get('content', {})
                        if content.get('type') == 'text':
                            collected_messages.append(content.get('text', ''))
                self._log(f"[CHAT] 最后处理了 {current_count - len(processed_notifications)} 个通知")
        
        # 组合最终回复
        thinking_text = ''.join(collected_thinking).strip()
        message_text = ''.join(collected_messages).strip()

        # 构建工具调用显示
        tools_text = ""
        if collected_tools:
            tools_text = "\n\n🔧 **工具调用**\n"
            for tool in collected_tools.values():
                status_emoji = {
                    'pending': '⏳',
                    'in_progress': '🔄',
                    'completed': '✅',
                    'failed': '❌'
                }.get(tool['status'], '📌')
                tools_text += f"- {status_emoji} {tool['title']}\n"

        # 组合最终内容
        combined_parts = []
        if thinking_text:
            combined_parts.append(f"💭 **思考过程**\n```\n{thinking_text}\n```")
        if tools_text:
            combined_parts.append(tools_text)
        if message_text:
            combined_parts.append(message_text)

        reply = '\n\n'.join(combined_parts)
        self._log(f"[CHAT] 最终回复长度: {len(reply)}")
        return reply if reply else "处理完成，无回复"

    def close(self):
        """关闭连接"""
        if self.process:
            self.process.terminate()
            if self._reader_thread:
                self._reader_thread.join(timeout=2)
            self.process.wait()

class LarkBot:
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
        # 日志文件路径
        self.log_file = os.path.join(os.path.dirname(__file__), 'bot_debug.log')
        # 飞书 API 调用日志
        self.feishu_log_file = os.path.join(os.path.dirname(__file__), 'feishu_api.log')
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
        """获取最近聊天记录"""
        try:
            from lark_oapi.api.im.v1 import ListMessageRequest
            
            request = ListMessageRequest.builder() \
                .container_id_type("chat") \
                .container_id(chat_id) \
                .page_size(limit) \
                .build()
            
            response = self.client.im.v1.message.list(request)
            
            if response.success():
                items = response.data.items if response.data else []
                history = []
                for item in reversed(items):  # 按时间顺序排列
                    try:
                        sender = item.sender.sender_id.user_id if item.sender and item.sender.sender_id else "unknown"
                        content = json.loads(item.body.content) if item.body else {}
                        text = content.get('text', '')
                        if text:
                            history.append(f"{sender}: {text}")
                    except:
                        continue
                return history
            else:
                self._log(f"[ERROR] 获取聊天记录失败: {response.code} - {response.msg}")
                return []
        except Exception as e:
            self._log(f"[ERROR] 获取聊天记录异常: {e}")
            return []

    def on_message(self, data: lark.im.v1.P2ImMessageReceiveV1):
        """处理收到的消息（支持文本、图片、文件）"""
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
            chat_id_looks_like_group = chat_id.startswith('oc_') if chat_id else False
            
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
            self._log(f"[DEBUG] chat_id_looks_like_group={chat_id_looks_like_group}")
            
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
                    import json
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
                            import re
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

            # 更新 MCP 上下文文件，让 MCP Server 知道当前聊天的 chat_id
            try:
                import json
                context_dir = os.path.join(os.path.dirname(__file__), 'WORKPLACE')
                os.makedirs(context_dir, exist_ok=True)
                context_file = os.path.join(context_dir, 'mcp_context.json')
                with open(context_file, 'w') as f:
                    json.dump({'chat_id': chat_id, 'timestamp': time.time()}, f)
                self._log(f"[DEBUG] 更新 MCP 上下文: chat_id={chat_id}")
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
                
                # 检查是否有待处理的图片或文件
                if chat_id in self._pending_image:
                    image_path = self._pending_image[chat_id]
                    if os.path.exists(image_path):
                        combined_prompt = f"{context_prompt}用户发送了一张图片，路径为: {image_path}\n\n用户对该图片的指令: {text}\n\n请根据用户的指令分析处理这张图片。"
                        self._log(f"[DEBUG] 将图片和消息一起发送给 Kimi: {image_path}, 消息: {text[:50]}...")
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
            waiting_symbols = ["◐", "◓", "◑", "◒"]
            symbol_index = [0]
            
            # 立即更新一次占位符，让用户知道已经开始处理
            self.executor.submit(self.update_card, initial_message_id, "⏳ 正在思考...")
            
            def get_waiting_symbol():
                """获取当前等待符号并更新索引"""
                symbol = waiting_symbols[symbol_index[0] % len(waiting_symbols)]
                symbol_index[0] += 1
                return symbol
            
            def on_chunk(current_text):
                """收到新的文本块时的回调 - 更新到飞书卡片"""
                if is_completed[0]:
                    return
                    
                current_time = time.time()
                
                # 第一次更新立即执行，后续每 0.3 秒最多更新一次
                if first_update[0]:
                    first_update[0] = False
                    time_elapsed = True
                else:
                    time_elapsed = current_time - last_update_time[0] >= 0.3
                
                content_changed = current_text != last_content[0]
                
                if content_changed and time_elapsed:
                    # 在内容末尾添加等待符号表示还在生成中
                    display_text = current_text + f"\n\n{get_waiting_symbol()} **生成中...**"
                    # 异步更新卡片，避免阻塞 ACP 接收
                    self.executor.submit(self.update_card, initial_message_id, display_text)
                    last_content[0] = current_text
                    last_update_time[0] = current_time
            
            def on_chunk_final(final_text):
                """最终回调 - 不带生成中字样"""
                # 标记已完成，阻止 on_chunk 继续更新
                is_completed[0] = True
                
                # 检查是否有工具刚完成，给用户3秒时间看到完成状态
                has_completed_tools = "✅" in final_text and "🔧 **工具调用**" in final_text
                if has_completed_tools:
                    self._log(f"[DEBUG] 工具已完成，等待3秒让用户看到完成状态...")
                    # 先更新一次显示工具完成状态（带生成中）
                    display_text = final_text + f"\n\n{get_waiting_symbol()} **生成中...**"
                    self._do_update_card_now(initial_message_id, display_text)
                    time.sleep(3)  # 给用户3秒看到工具完成状态
                
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
                    # 清空待更新内容，防止旧更新覆盖
                    self._pending_updates[initial_message_id] = ""
                
                # 等待一小段时间，确保正在执行的更新完成
                time.sleep(0.3)
                # 直接更新卡片，不添加生成中字样
                self._do_update_card_now(initial_message_id, final_text)
                # 再更新一次确保生效
                time.sleep(0.2)
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

    def run_msg_script(self, text):
        """使用 ACP 协议调用 Kimi Code CLI"""
        try:
            # 延迟初始化 ACP 客户端
            if self.acp_client is None:
                print("[DEBUG] 初始化 ACP 客户端...")
                self.acp_client = ACPClient()

            print(f"[DEBUG] 调用 ACP: {text[:50]}...")
            response = self.acp_client.chat(text, timeout=120)
            print(f"[DEBUG] ACP 响应: {response[:100]}...")
            return response

        except Exception as e:
            import traceback
            traceback.print_exc()
            return f"调用 ACP 出错: {str(e)}"

    def reply_text(self, chat_id, text, streaming=False):
        """发送消息卡片（支持 Markdown 格式）"""
        text_length = len(text)

        # 构建新版消息卡片内容 (V2)
        card_content = self._build_v2_card_content(text)
        
        # 记录发送给飞书的消息
        self._log_feishu("SEND", {
            "type": "CREATE_MESSAGE",
            "chat_id": chat_id,
            "text_length": text_length,
            "text_preview": text[:200] if len(text) > 200 else text
        }, f"streaming={streaming}")
        
        request = CreateMessageRequest.builder() \
            .receive_id_type("chat_id") \
            .request_body(CreateMessageRequestBody.builder()
                .receive_id(chat_id)
                .msg_type("interactive")
                .content(json.dumps(card_content))
                .build()) \
            .build()
        msg_type = "card"

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

    def _format_lark_md(self, text):
        """格式化文本，保留原始格式"""
        if not text:
            return text
        
        # 保留原始文本，不做任何转换
        # plain_text 会原样显示
        return text
    
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
        import re
        
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
        import threading
        
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
            
            # 创建定时器，1秒后执行实际更新
            timer = threading.Timer(1.0, self._do_update_card, args=[message_id])
            self._update_timers[message_id] = timer
            timer.start()
    
    def _do_update_card(self, message_id):
        """实际执行卡片更新（批量策略）"""
        from lark_oapi.api.im.v1 import PatchMessageRequest, PatchMessageRequestBody
        import time
        
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
        import time
        
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
            import json
            
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
            import time
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
            import time
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
            waiting_symbols = ["◐", "◓", "◑", "◒"]
            symbol_index = [0]
            
            def get_waiting_symbol():
                symbol = waiting_symbols[symbol_index[0] % len(waiting_symbols)]
                symbol_index[0] += 1
                return symbol
            
            def on_chunk(current_text):
                if is_completed[0]:
                    return
                current_time = time.time()
                if first_update[0]:
                    first_update[0] = False
                    time_elapsed = True
                else:
                    time_elapsed = current_time - last_update_time[0] >= 0.3
                
                if current_text != last_content[0] and time_elapsed:
                    display_text = current_text + f"\n\n{get_waiting_symbol()} **生成中...**"
                    self.executor.submit(self.update_card, initial_message_id, display_text)
                    last_content[0] = current_text
                    last_update_time[0] = current_time
            
            def on_chunk_final(final_text):
                is_completed[0] = True
                with self._update_lock:
                    self._completed_messages.add(initial_message_id)
                    if initial_message_id in self._update_timers:
                        try:
                            self._update_timers[initial_message_id].cancel()
                        except:
                            pass
                        del self._update_timers[initial_message_id]
                    self._pending_updates[initial_message_id] = ""
                time.sleep(0.3)
                self._do_update_card_now(initial_message_id, final_text)
                time.sleep(0.2)
                self._do_update_card_now(initial_message_id, final_text)

            response = self.acp_client.chat(prompt, on_chunk=on_chunk, timeout=300)
            on_chunk_final(response)
            
        except Exception as e:
            self._log(f"[ERROR] 调用 ACP 出错: {e}")
            self.update_card(initial_message_id, f"❌ 处理失败: {str(e)}")


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

if __name__ == "__main__":
    import sys
    
    appid = 'cli_a90ded6b63f89cd6'
    app_secret = '3WDKvIVUHPYVXbEVYjRgRg2wORBDb5z3'

    bot = LarkBot(appid, app_secret)
    
    # 检查是否是测试模式
    if len(sys.argv) > 1 and sys.argv[1] == "--test-streaming":
        chat_id = sys.argv[2] if len(sys.argv) > 2 else "oc_d24a689f16656bb78b5a6b75c5a2b552"
        test_msg = sys.argv[3] if len(sys.argv) > 3 else "写一个50字的问候语"
        print(f"[TEST] 开始流式测试: chat_id={chat_id}, msg='{test_msg}'")
        bot.run_msg_script_streaming(chat_id, test_msg)
        # 等待流式完成
        import time
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
