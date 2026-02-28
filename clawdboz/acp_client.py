#!/usr/bin/env python3
"""ACP 客户端模块 - Kimi Code CLI ACP 协议通信"""
import json
import os
import subprocess
import sys
import threading
import time
import uuid

from .config import CONFIG, get_absolute_path, PROJECT_ROOT


class ACPClient:
    """Kimi Code CLI ACP 客户端"""
    
    def __init__(self, bot_ref=None):
        self.process = None
        self.response_map = {}
        self.notifications = []
        self._lock = threading.Lock()
        self._reader_thread = None
        self._bot_ref = bot_ref  # 保存 bot 引用，用于日志
        self._cancelled = False  # 取消标志
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
        
        # 加载项目目录下的 .bots.md 规则文件（传入 skills 列表）
        system_prompt = self._load_bots_md(skills)
        
        # 创建新会话，使用 WORKPLACE 作为工作目录
        workplace_path = get_absolute_path(CONFIG.get('paths', {}).get('workplace', 'WORKPLACE'))
        session_params = {
            'cwd': workplace_path,
            'mcpServers': mcp_servers
        }
        if skills:
            session_params['skills'] = skills
        if system_prompt:
            session_params['systemPrompt'] = system_prompt
        
        # 保存 system_prompt 供后续 chat 使用
        self.system_prompt = system_prompt
            
        self._log(f"[ACP] 创建会话，cwd: {workplace_path}, MCP服务器: {[s.get('name') for s in mcp_servers]}, Skills: {len(skills)}, 系统提示词: {'已加载' if system_prompt else '未加载'}")
        result, error = self.call_method('session/new', session_params)
        if error:
            raise Exception(f"创建会话失败: {error}")
        self.session_id = result['sessionId']
        self._log(f"ACP 会话创建成功: {self.session_id}")
    
    def _get_builtin_mcp_config(self):
        """获取内置的 MCP 配置（基于包安装位置）
        
        当项目目录没有 MCP 配置时，使用包自带的配置
        同时传递飞书应用凭证给 MCP server
        """
        import sys
        from pathlib import Path
        
        # 获取包安装目录
        package_dir = Path(__file__).parent.resolve()
        feishu_tools_dir = package_dir.parent / 'feishu_tools'
        
        # 获取 Python 解释器路径
        python_exe = sys.executable
        
        # 构建 MCP server 路径
        feishu_file_server = feishu_tools_dir / 'mcp_feishu_file_server.py'
        feishu_msg_server = feishu_tools_dir / 'mcp_feishu_msg_server.py'
        
        if not feishu_file_server.exists():
            self._log(f"[ACP] 内置 MCP 工具不存在: {feishu_file_server}")
            return {}
        
        # 从 CONFIG 获取飞书凭证
        feishu_config = CONFIG.get('feishu', {})
        app_id = feishu_config.get('app_id', '')
        app_secret = feishu_config.get('app_secret', '')
        
        if not app_id or not app_secret:
            self._log(f"[ACP] 警告: 飞书凭证未配置，MCP server 可能无法正常工作")
        
        self._log(f"[ACP] 使用内置 MCP 配置")
        self._log(f"[ACP]   Python: {python_exe}")
        self._log(f"[ACP]   FeishuFileSender: {feishu_file_server}")
        self._log(f"[ACP]   FeishuMessageSender: {feishu_msg_server}")
        
        mcp_servers = {
            'FeishuFileSender': {
                'type': 'stdio',
                'command': python_exe,
                'args': [str(feishu_file_server)],
                'env': {
                    'FEISHU_APP_ID': app_id,
                    'FEISHU_APP_SECRET': app_secret
                }
            }
        }
        
        # 添加消息发送 MCP（如果文件存在）
        if feishu_msg_server.exists():
            mcp_servers['FeishuMessageSender'] = {
                'type': 'stdio',
                'command': python_exe,
                'args': [str(feishu_msg_server)],
                'env': {
                    'FEISHU_APP_ID': app_id,
                    'FEISHU_APP_SECRET': app_secret
                }
            }
        
        return mcp_servers
    
    def _load_mcp_config(self):
        """加载项目目录下的 MCP 配置文件 (.kimi/mcp.json)
        
        如果项目目录没有配置，则使用包内置的 MCP 配置。
        返回格式为列表，每个元素包含 name、type 和配置信息
        注意：根据 Kimi ACP 协议，headers 需要是列表格式
        """
        mcp_config_path = get_absolute_path('.kimi/mcp.json')
        mcp_servers_dict = {}
        
        if os.path.exists(mcp_config_path):
            try:
                with open(mcp_config_path, 'r', encoding='utf-8') as f:
                    config = json.load(f)
                mcp_servers_dict = config.get('mcpServers', {})
                self._log(f"[ACP] 从项目目录加载 MCP 配置: {mcp_config_path}")
            except Exception as e:
                self._log(f"[ACP] 加载 MCP 配置失败: {e}")
        else:
            self._log(f"[ACP] 未找到 MCP 配置文件: {mcp_config_path}")
            # 使用内置配置
            mcp_servers_dict = self._get_builtin_mcp_config()
        
        if not mcp_servers_dict:
            return []
        
        try:
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
                
                # 确保 env 是列表 (用于 stdio 类型)
                if 'env' in server_info and isinstance(server_info['env'], dict):
                    env_list = []
                    for key, value in server_info['env'].items():
                        env_list.append({'name': key, 'value': value})
                    server_info['env'] = env_list
                mcp_servers.append(server_info)
            self._log(f"[ACP] 加载 MCP 配置成功，服务器数量: {len(mcp_servers)}")
            return mcp_servers
        except Exception as e:
            self._log(f"[ACP] 加载 MCP 配置失败: {e}")
            return []
    
    def _load_skills(self):
        """加载 skills（用户目录 + 内置 skills）"""
        skills = []
        
        # 1. 加载用户项目目录下的 skills
        user_skills_dir = get_absolute_path('.kimi/skills')
        if os.path.exists(user_skills_dir):
            try:
                for item in os.listdir(user_skills_dir):
                    skill_path = os.path.join(user_skills_dir, item)
                    if os.path.isdir(skill_path):
                        skill_md = os.path.join(skill_path, 'SKILL.md')
                        if os.path.exists(skill_md):
                            # 读取 SKILL.md 内容
                            try:
                                with open(skill_md, 'r', encoding='utf-8') as f:
                                    skill_content = f.read()
                                skills.append({
                                    'name': item,
                                    'path': skill_path,
                                    'content': skill_content
                                })
                            except Exception as e:
                                self._log(f"[ACP] 读取 Skill {item} 失败: {e}")
                                skills.append({
                                    'name': item,
                                    'path': skill_path
                                })
                self._log(f"[ACP] 加载用户 Skills: {len(skills)} 个")
            except Exception as e:
                self._log(f"[ACP] 加载用户 Skills 失败: {e}")
        else:
            self._log(f"[ACP] 未找到用户 skills 目录: {user_skills_dir}")
        
        # 2. 加载包内置的 skills
        try:
            import inspect
            builtin_skills_dir = os.path.join(
                os.path.dirname(os.path.abspath(inspect.getfile(self.__class__))),
                '.kimi', 'skills'
            )
            
            if os.path.exists(builtin_skills_dir):
                builtin_count = 0
                for item in os.listdir(builtin_skills_dir):
                    skill_path = os.path.join(builtin_skills_dir, item)
                    if os.path.isdir(skill_path):
                        skill_md = os.path.join(skill_path, 'SKILL.md')
                        if os.path.exists(skill_md):
                            # 避免重复加载同名 skill
                            if not any(s['name'] == item for s in skills):
                                # 读取 SKILL.md 内容
                                try:
                                    with open(skill_md, 'r', encoding='utf-8') as f:
                                        skill_content = f.read()
                                    skills.append({
                                        'name': item,
                                        'path': skill_path,
                                        'content': skill_content
                                    })
                                except Exception as e:
                                    self._log(f"[ACP] 读取内置 Skill {item} 失败: {e}")
                                    skills.append({
                                        'name': item,
                                        'path': skill_path
                                    })
                                builtin_count += 1
                self._log(f"[ACP] 加载内置 Skills: {builtin_count} 个")
            else:
                self._log(f"[ACP] 未找到内置 skills 目录: {builtin_skills_dir}")
        except Exception as e:
            self._log(f"[ACP] 加载内置 Skills 失败: {e}")
        
        self._log(f"[ACP] 总共加载 Skills: {len(skills)} 个")
        return skills
    
    def _load_bots_md(self, skills=None):
        """加载项目目录下的 .bots.md 规则文件作为系统提示词
        
        Args:
            skills: 已加载的 skills 列表，会追加到 system prompt 中
        """
        bots_md_path = get_absolute_path('.bots.md')
        
        content = ""
        
        # 加载 .bots.md 文件
        if os.path.exists(bots_md_path):
            try:
                with open(bots_md_path, 'r', encoding='utf-8') as f:
                    content = f.read()
                self._log(f"[ACP] 加载 .bots.md 成功，长度: {len(content)} 字符")
            except Exception as e:
                self._log(f"[ACP] 加载 .bots.md 失败: {e}")
        else:
            self._log(f"[ACP] 未找到 .bots.md 文件: {bots_md_path}")
        
        # 添加可用 skills 列表到 system prompt
        if skills:
            skills_section = "\n\n## 可用 Skills（功能模块）\n\n"
            skills_section += "**重要：当用户询问你有什么功能、技能、能做什么、支持什么时，必须主动详细介绍以下内容：**\n\n"
            
            for skill in skills:
                skill_name = skill['name']
                skill_path = skill['path']
                skill_md_path = os.path.join(skill_path, 'SKILL.md')
                
                try:
                    with open(skill_md_path, 'r', encoding='utf-8') as f:
                        skill_content = f.read()
                    
                    # 解析 SKILL.md 内容
                    lines = skill_content.split('\n')
                    description = ""  # 初始化描述变量
                    
                    # 处理 frontmatter (--- 开头的 YAML)
                    content_start = 0
                    if lines and lines[0].strip() == '---':
                        # 查找第二个 ---
                        for i in range(1, len(lines)):
                            if lines[i].strip() == '---':
                                content_start = i + 1
                                break
                        # 从 frontmatter 提取 description
                        for i in range(1, content_start):
                            if lines[i].startswith('description:'):
                                description = lines[i].split(':', 1)[1].strip()
                                break
                    
                    # 获取标题（第一个 # 开头的行）
                    title = skill_name
                    for i in range(content_start, len(lines)):
                        if lines[i].strip().startswith('#'):
                            title = lines[i].strip().lstrip('#').strip()
                            break
                    
                    # 如果没有从 frontmatter 获取到描述，尝试从 ## 描述/功能 部分获取
                    if not description:
                        in_desc = False
                        desc_lines = []
                        for i in range(content_start, len(lines)):
                            line = lines[i]
                            if line.strip().startswith('## 描述') or line.strip().startswith('## 功能'):
                                in_desc = True
                                continue
                            elif line.strip().startswith('##') and in_desc:
                                break
                            elif in_desc and line.strip():
                                desc_lines.append(line.strip())
                        
                        description = ' '.join(desc_lines) if desc_lines else "暂无描述"
                    
                    # 获取使用示例
                    examples = []
                    in_examples = False
                    for line in lines:
                        if '使用示例' in line or '使用场景' in line or '使用方式' in line:
                            in_examples = True
                            continue
                        elif in_examples and line.strip().startswith('-'):
                            example = line.strip().lstrip('-').strip()
                            if example:
                                examples.append(example)
                        elif in_examples and line.strip().startswith('##'):
                            break
                    
                    # 构建 skill 描述
                    skills_section += f"### {skill_name} - {title}\n"
                    skills_section += f"- **功能**：{description}\n"
                    
                    if examples:
                        skills_section += "- **使用示例**：\n"
                        for ex in examples[:3]:  # 最多3个示例
                            skills_section += f"  - {ex}\n"
                    
                    skills_section += "\n"
                    
                except Exception as e:
                    # 如果读取失败，使用简单描述
                    skills_section += f"### {skill_name}\n"
                    skills_section += f"- 功能：暂无描述\n\n"
            
            skills_section += "**规则**：当用户问\"你有什么技能\"、\"你能做什么\"、\"你有什么功能\"时，必须主动、详细地介绍以上所有 skills 的功能和使用方法。\n"
            content = content + skills_section if content else skills_section
        
        return content if content.strip() else None

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
                                # 流式输出日志已禁用（减少日志噪声）
                                # self._log(f"[ACP RAW] 消息 chunk: {repr(text)}")
                                # print(f"[ACP] 消息: {text[:100]}...")

                        elif update_type == 'thinking' or update_type == 'agent_thought_chunk':
                            # 思考内容
                            content = update.get('content', {})
                            if content.get('type') == 'text':
                                text = content.get('text', '')
                                # 流式输出日志已禁用（减少日志噪声）
                                # self._log(f"[ACP RAW] 思考 chunk: {repr(text)}")
                                # print(f"[ACP] 思考: {text[:100]}...")

                        elif update_type == 'tool_call':
                            # 工具调用开始
                            tool_call_id = update.get('toolCallId', '')
                            title = update.get('title', 'Unknown Tool')
                            # 流式输出日志已禁用（减少日志噪声）
                            # print(f"[ACP] 工具调用: {title} ({tool_call_id})")

                        elif update_type == 'tool_call_update':
                            # 工具调用状态更新
                            tool_call_id = update.get('toolCallId', '')
                            status = update.get('status', '')
                            # 流式输出日志已禁用（减少日志噪声）
                            # print(f"[ACP] 工具状态: {tool_call_id} -> {status}")

                            # 如果工具完成，提取结果内容
                            if status == 'completed' or status == 'failed':
                                content = update.get('content', [])
                                if content:
                                    # 流式输出日志已禁用（减少日志噪声）
                                    # print(f"[ACP] 工具结果: {content[:200] if len(str(content)) > 200 else content}...")
                                    pass

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
        msg_id = str(uuid.uuid4())
        request = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": method,
            "params": params
        }

        # 发送请求，支持自动重试
        max_retries = 2
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # 检查进程是否存活
                if self.process.poll() is not None:
                    self._log(f"[CALL] ACP 进程已终止，尝试重新初始化")
                    self._initialize()
                
                self.process.stdin.write(json.dumps(request) + '\n')
                self.process.stdin.flush()
                self._log(f"发送请求: {method}, id: {msg_id[:8]}...")
                break  # 发送成功，跳出重试循环
                
            except BrokenPipeError:
                retry_count += 1
                self._log(f"[CALL] Broken pipe 错误 (重试 {retry_count}/{max_retries})")
                
                if retry_count >= max_retries:
                    return None, "ACP 连接已断开"
                
                # 尝试重新初始化
                try:
                    if self.process:
                        try:
                            self.process.kill()
                        except:
                            pass
                    self._initialize()
                    time.sleep(0.5)
                except Exception as reinit_error:
                    return None, f"重新初始化失败: {reinit_error}"
                    
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

        # 构建完整消息：system_prompt + user message
        # ACP 可能不处理 session/new 中的 systemPrompt，所以在每次 chat 时前置
        full_message = message
        if hasattr(self, 'system_prompt') and self.system_prompt:
            full_message = f"{self.system_prompt}\n\n---\n\n{message}"
        
        # 发送 prompt（不等待响应，直接开始监听通知）
        msg_id = str(uuid.uuid4())
        request = {
            "jsonrpc": "2.0",
            "id": msg_id,
            "method": "session/prompt",
            "params": {
                'sessionId': self.session_id,
                'prompt': [{'type': 'text', 'text': full_message}]
            }
        }
        
        # 发送请求，支持自动重试
        max_retries = 2
        retry_count = 0
        
        while retry_count < max_retries:
            try:
                # 检查进程是否仍然存活
                if self.process.poll() is not None:
                    self._log("[CHAT] ACP 进程已终止，尝试重新初始化")
                    self._initialize()
                    self._log("[CHAT] 重新初始化完成")
                
                self.process.stdin.write(json.dumps(request) + '\n')
                self.process.stdin.flush()
                break  # 发送成功，跳出重试循环
                
            except BrokenPipeError:
                retry_count += 1
                self._log(f"[CHAT] Broken pipe 错误，ACP 进程可能已崩溃 (重试 {retry_count}/{max_retries})")
                
                if retry_count >= max_retries:
                    return "ACP 连接已断开，请稍后重试"
                
                # 尝试重新初始化
                try:
                    self._log("[CHAT] 尝试重新初始化 ACP 连接...")
                    # 清理旧进程
                    if self.process:
                        try:
                            self.process.kill()
                        except:
                            pass
                    # 重新初始化
                    self._initialize()
                    self._log("[CHAT] 重新初始化成功，准备重试...")
                    # 需要更新 session_id 到请求中
                    request['params']['sessionId'] = self.session_id
                    time.sleep(0.5)  # 短暂延迟确保连接稳定
                except Exception as reinit_error:
                    self._log(f"[CHAT] 重新初始化失败: {reinit_error}")
                    return f"ACP 连接已断开，重新初始化失败: {reinit_error}"
                    
            except Exception as e:
                return f"发送请求失败: {str(e)}"

        # 等待响应完成（检查 stopReason）
        last_callback_text = ""  # 记录上次回调的内容，避免重复调用
        result = None
        
        while time.time() - chat_start_time < timeout:
            time.sleep(0.01)  # 更短的睡眠间隔，更快响应
            
            # 检查是否被取消
            if self._cancelled:
                self._log("[CHAT] 检测到取消标志，停止接收新内容")
                break  # 跳出循环，继续组装已收集的内容

            # 快速获取锁，复制新通知，然后释放锁
            new_notifications = []
            unprocessed_count = 0
            with self._lock:
                # 检查是否有 prompt 的响应
                if result is None and msg_id in self.response_map:
                    result = self.response_map.pop(msg_id)
                    if 'error' in result:
                        # 错误日志保留
                        self._log(f"[CHAT] 收到错误响应: {result['error']}")
                        return f"错误: {result['error']}"
                    result = result.get('result')
                    # 流式日志已禁用
                    # self._log(f"[CHAT] 收到 prompt 响应")
                
                # 只获取未处理的通知
                current_count = len(self.notifications)
                unprocessed_count = current_count - len(processed_notifications)
                if unprocessed_count > 0:
                    for idx in range(len(processed_notifications), current_count):
                        new_notifications.append(self.notifications[idx])
                        processed_notifications.add(idx)
            
            # 流式日志已禁用
            # if unprocessed_count > 0:
            #     self._log(f"[CHAT] 获取 {unprocessed_count} 个新通知")
            
            # 在锁外处理通知（不阻塞 _read_responses）
            # 分批处理，每批最多10个通知，每批处理后回调
            batch_size = 10
            for i in range(0, len(new_notifications), batch_size):
                batch = new_notifications[i:i+batch_size]
                
                for notification in batch:
                    # 检查是否被取消
                    if self._cancelled:
                        self._log("[CHAT] 处理通知时检测到取消标志")
                        break  # 跳出内层循环
                    
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
                        # 流式日志已禁用
                        # self._log(f"[CHAT] 工具调用开始: {title} ({tool_call_id[:8]}...)")

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
                                # 流式日志已禁用
                                # self._log(f"[CHAT] 工具状态变化: {tool_call_id[:8]}... {old_status} -> {status}")
                                pass
                        last_chunk_time = time.time()

                    elif update_type == 'agent_message_chunk':
                        content = update.get('content', {})
                        if content.get('type') == 'text':
                            text = content.get('text', '')
                            if text:
                                collected_messages.append(text)
                                last_chunk_time = time.time()

                # 每批处理后回调（流式更新）- 回调前检查取消标志
                if self._cancelled:
                    self._log("[CHAT] 回调前检测到取消标志，继续组装已收集内容")
                
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
                        # 流式日志已禁用
                        # self._log(f"[CHAT] 触发 on_chunk, 内容长度: {len(callback_data)}")
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
                        # 流式日志已禁用
                        # self._log(f"[CHAT] 收到 stopReason: {stop_reason}，但工具仍在运行，继续等待...")
                        pass
                    # 如果收到了 stopReason 且没有工具在运行，等待3秒确保收集完所有通知
                    elif time.time() - last_chunk_time > 3:  # 3秒
                        # 流式日志已禁用
                        # self._log(f"[CHAT] 收到 stopReason: {stop_reason}，且工具已完成，退出")
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
                    # 流式日志已禁用
                    # self._log(f"[CHAT] 所有工具已完成，开始缓冲期...")
            else:
                # 重置标记
                if hasattr(self, '_all_tools_completed_time'):
                    delattr(self, '_all_tools_completed_time')
            
            # 统一超时时间：30分钟（1800秒）
            TIMEOUT_30_MIN = 1800
            
            # 检查是否处于工具完成后的缓冲期（给30分钟让服务器发送后续消息）
            tools_completed_buffer = 0
            if hasattr(self, '_all_tools_completed_time'):
                tools_completed_buffer = time.time() - self._all_tools_completed_time
            
            # 如果超过 30 分钟没有新 chunk，且没有正在运行的工具，且不在缓冲期内，认为已完成
            idle_time = time.time() - last_chunk_time
            if (idle_time > TIMEOUT_30_MIN and not has_in_progress_tool and 
                tools_completed_buffer > TIMEOUT_30_MIN and  # 所有工具完成后至少等30分钟
                (collected_thinking or collected_tools or collected_messages)):
                # 流式日志已禁用
                # self._log(f"[CHAT] 30分钟无新内容，工具已完成{tools_completed_buffer:.1f}秒，准备退出...")
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
                            # 流式日志已禁用
                            # self._log(f"[CHAT] 退出前发现 {unprocessed} 个新通知，继续处理")
                            break
                else:
                    # 10秒内没有新通知，可以安全退出
                    # 流式日志已禁用
                    # self._log(f"[CHAT] 确认无新内容，退出")
                    # 清理标记
                    if hasattr(self, '_all_tools_completed_time'):
                        delattr(self, '_all_tools_completed_time')
                    break
            elif has_in_progress_tool and tool_running_time > TIMEOUT_30_MIN:
                # 有工具运行超过30分钟，提示超时
                # 流式日志已禁用
                # self._log(f"[CHAT] 工具运行超过30分钟，提示超时")
                timeout_warning = "\n\n⚠️ **提示**：部分工具调用耗时过长（超过30分钟），可能已超时。如未收到完整结果，请重试。"
                collected_messages.append(timeout_warning)
                break
        
        # 退出前最后处理一次所有剩余通知
        # 流式日志已禁用
        # self._log(f"[CHAT] 最后处理剩余通知...")
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
                # 流式日志已禁用
                # self._log(f"[CHAT] 最后处理了 {current_count - len(processed_notifications)} 个通知")
        
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
        
        # 如果被取消，添加取消标记
        if self._cancelled:
            cancel_marker = "\n\n---\n⏹️ **生成已取消**"
            reply = reply + cancel_marker if reply else "⏹️ **生成已取消**"
            self._log("[CHAT] 添加取消标记到回复末尾")
        
        # 流式日志已禁用
        # self._log(f"[CHAT] 最终回复长度: {len(reply)}")
        return reply if reply else "处理完成，无回复"

    def cancel(self):
        """取消当前生成任务"""
        self._log("[CANCEL] 设置取消标志")
        self._cancelled = True
    
    def reset_cancel(self):
        """重置取消标志（用于新任务）"""
        self._cancelled = False

    def close(self):
        """关闭连接"""
        if self.process:
            self.process.terminate()
            if self._reader_thread:
                self._reader_thread.join(timeout=2)
            self.process.wait()
