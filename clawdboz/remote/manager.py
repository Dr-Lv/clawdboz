"""
远程 Bot 管理器
集成远程 Bot 发布、发现和调用功能
"""
import asyncio
from typing import Dict, List, Optional
from pathlib import Path

from clawdboz.remote.config import RemoteConfig
from clawdboz.remote.registry_client import RegistryClient
from clawdboz.remote.friend_manager import FriendManager
from clawdboz.remote.bot_publisher import BotPublisher
from clawdboz.remote.remote_client import RemoteBotClient
from clawdboz.remote.instance import RemoteInstance
from clawdboz.remote.auth import TokenManager
from clawdboz.remote.registry_ws_client import RegistryConnectionState
from clawdboz.remote.docker_sandbox import DockerSandboxManager, DockerSandboxConfig


class RemoteBotManager:
    """远程 Bot 管理器"""

    def __init__(
        self,
        instance_id: str,
        config: RemoteConfig,
        base_workplace: str,
        bots: Optional[dict] = None
    ):
        """
        初始化远程 Bot 管理器

        Args:
            instance_id: 实例 ID
            config: 远程功能配置
            base_workplace: 基础工作目录
            bots: Bot 字典引用
        """
        self.instance_id = instance_id
        self.config = config
        self.base_workplace = base_workplace
        self._bots = bots or {}

        # Token 管理器
        # 优先使用配置文件中的密钥，否则使用默认密钥
        token_secret = config.token_secret or "clawdboz-remote-secret-key-2024"
        self.token_manager = TokenManager(secret_key=token_secret)

        # 注册信息
        self.instance_info = {
            "instance_id": instance_id,
            "name": config.instance_name or instance_id,
            "host": config.host,
            "port": config.port,
            "token": self.token_manager.generate_instance_token(instance_id),
            "published_bots": [],
            "fs_api_enabled": True
        }

        # 注册服务器客户端
        self.registry_client: Optional[RegistryClient] = None

        # 好友管理器
        self.friend_manager: Optional[FriendManager] = None

        # Bot 发布管理器
        self.bot_publisher: Optional[BotPublisher] = None

        # 远程 Bot 客户端 {instance_id: RemoteBotClient}
        self.remote_clients: Dict[str, RemoteBotClient] = {}

        # NEW: 注册服务器 WebSocket 客户端（中心转发模式）
        self._registry_ws_client = None

        # 已发现的远程实例 {instance_id: RemoteInstance}
        self.discovered_instances: Dict[str, RemoteInstance] = {}

        # 远程 Bot 缓存 {bot_id: RemoteInstance}
        self.remote_bot_cache: Dict[str, RemoteInstance] = {}

        # 是否已启动
        self._started = False

        # 是否正在启动中（防止并发调用 start()）
        self._starting = False

        # Dependencies for bot calls (set after initialization)
        self._acp_mgr = None
        self._workspace_mgr = None

        # Docker 沙箱管理器
        self._sandbox_mgr = None

    def set_dependencies(self, acp_mgr, workspace_mgr):
        """Set dependencies for bot calls"""
        self._acp_mgr = acp_mgr
        self._workspace_mgr = workspace_mgr
        print(f"[RemoteBot] Dependencies set: acp_mgr={acp_mgr is not None}, workspace_mgr={workspace_mgr is not None}")

        # 后台任务
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._discovery_task: Optional[asyncio.Task] = None
        self._listen_task: Optional[asyncio.Task] = None

    async def start(self):
        """启动远程功能"""
        if not self.config.enabled:
            print("[RemoteBot] 远程功能未启用")
            return

        if self._starting:
            print(f"[RemoteBot] 启动中，跳过重复调用")
            return

        if self._started:
            # 已经在临时事件循环中初始化过，确保后台任务在 uvicorn 事件循环中重新启动
            if self._registry_ws_client and self._registry_ws_client.is_connected:
                print(f"[RemoteBot] 已经启动且 WS 已连接，跳过")
                return
            print(f"[RemoteBot] 重新启动后台任务 (uvicorn 事件循环)")
            await self._ensure_background_tasks()
            return

        self._starting = True
        print(f"[RemoteBot] 启动远程 Bot 管理 (instance_id={self.instance_id})")

        try:
            # 初始化注册服务器客户端
            self.registry_client = RegistryClient(
                registry_url=self.config.registry_url,
                instance_info=self.instance_info,
                auto_heartbeat=True
            )

            # 连接到注册服务器
            await self.registry_client.__aenter__()
            print(f"[RemoteBot] RegistryClient session initialized: {self.registry_client.session is not None}")

            # 注册实例
            if self.config.auto_register:
                success = await self.registry_client.register()
                if success:
                    print(f"[RemoteBot] 实例注册成功")
                else:
                    print(f"[RemoteBot] 实例注册失败")

            # 启动心跳
            if self.config.auto_register:
                await self.registry_client.start_heartbeat(self.config.heartbeat_interval)

            # 初始化好友管理器
            self.friend_manager = FriendManager(self.registry_client)

            # 初始化 Docker 沙箱管理器（必须在 BotPublisher 之前）
            try:
                self._sandbox_mgr = DockerSandboxManager(DockerSandboxConfig())
                if self._sandbox_mgr.is_available():
                    print("[RemoteBot] Docker 沙箱管理器已初始化")
                else:
                    print("[RemoteBot] Docker 不可用，沙箱功能禁用")
            except Exception as e:
                print(f"[RemoteBot] 沙箱管理器初始化失败: {e}")
                self._sandbox_mgr = None

            # 初始化 Bot 发布管理器
            storage_path = Path(self.base_workplace) / ".remote" / "published_bots.json"
            self.bot_publisher = BotPublisher(
                instance_id=self.instance_id,
                registry_client=self.registry_client,
                storage_path=storage_path,
                sandbox_mgr=self._sandbox_mgr
            )

            # 通知注册服务器已发布的 Bot 列表
            self.bot_publisher._notify_registry()

            # 同步已发布的沙箱 bot 到容器
            if self._sandbox_mgr and self._sandbox_mgr.is_available():
                await self.bot_publisher.sync_sandbox_registrations()

            # NEW: 如果是中心转发模式，连接到注册服务器 WebSocket
            if self.config.connection_mode == "center":
                from clawdboz.remote.registry_ws_client import RegistryWebSocketClient

                # 构建 WebSocket URL
                ws_url = self.config.registry_ws_url
                if not ws_url:
                    # 从 registry_url 推导
                    ws_url = self.config.registry_url.replace("http://", "ws://").replace("https://", "wss://")
                    ws_url = f"{ws_url}/ws/registry"

                print(f"[RemoteBot] 中心转发模式: 连接到注册服务器 WebSocket: {ws_url}")
                # 每次连接前重新生成 token（避免过期）
                token_to_use = self.token_manager.generate_instance_token(self.instance_id)
                print(f"[RemoteBot] DEBUG: Generated fresh token (first 30 chars): {token_to_use[:30]}...")
                # 先断开旧连接（避免旧任务 pending 被销毁时报错）
                if self._registry_ws_client:
                    try:
                        await self._registry_ws_client.disconnect()
                    except Exception:
                        pass

                self._registry_ws_client = RegistryWebSocketClient(
                    registry_ws_url=ws_url,
                    instance_id=self.instance_id,
                    token=token_to_use  # Use same token as registration
                )

                try:
                    await self._registry_ws_client.connect()
                    # 启动监听任务
                    asyncio.create_task(self._listen_for_registry_messages())
                    print(f"[RemoteBot] 已连接到注册服务器 WebSocket")
                except Exception as e:
                    print(f"[RemoteBot] 连接注册服务器 WebSocket 失败: {e}，将回退到 P2P 模式")
                    print(f"[RemoteBot] 提示: 请检查注册服务器是否支持 WebSocket (/ws/registry)")
                    self._registry_ws_client = None

            # 启动发现任务
            self._discovery_task = asyncio.create_task(self._discovery_loop())

            # 启动心跳任务
            self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())

            self._starting = False
            self._started = True
            print(f"[RemoteBot] 远程 Bot 管理已启动")

        except Exception as e:
            self._starting = False
            print(f"[RemoteBot] 启动失败: {e}")
            import traceback
            traceback.print_exc()

    async def _ensure_background_tasks(self):
        """确保后台任务在当前事件循环中运行（用于 uvicorn 事件循环切换后重新启动）"""
        # 如果 RegistryClient 心跳已停止，重新启动
        if self.registry_client and self.config.auto_register:
            if not getattr(self.registry_client, '_heartbeat_task', None) or self.registry_client._heartbeat_task.done():
                self.registry_client._running = False
                self.registry_client._heartbeat_task = None
                await self.registry_client.start_heartbeat(self.config.heartbeat_interval)

        # 重新启动发现任务（仅当不存在或已完成）
        if not self._discovery_task or self._discovery_task.done():
            try:
                self._discovery_task = asyncio.create_task(self._discovery_loop())
            except Exception as e:
                print(f"[RemoteBot] 重新启动发现任务失败: {e}")

        # 重新启动心跳任务（仅当不存在或已完成）
        if not self._heartbeat_task or self._heartbeat_task.done():
            try:
                self._heartbeat_task = asyncio.create_task(self._heartbeat_loop())
            except Exception as e:
                print(f"[RemoteBot] 重新启动心跳任务失败: {e}")

        # 重新连接注册服务器 WebSocket（中心转发模式）——仅当未连接时
        if self.config.connection_mode == "center":
            if self._registry_ws_client and self._registry_ws_client.is_connected:
                print(f"[RemoteBot] WebSocket 已连接，跳过重新连接")
                # 确保监听任务在运行
                if not self._listen_task or self._listen_task.done():
                    asyncio.create_task(self._listen_for_registry_messages())
                return
            try:
                from clawdboz.remote.registry_ws_client import RegistryWebSocketClient

                ws_url = self.config.registry_ws_url
                if not ws_url:
                    ws_url = self.config.registry_url.replace("http://", "ws://").replace("https://", "wss://")
                    ws_url = f"{ws_url}/ws/registry"

                token_to_use = self.token_manager.generate_instance_token(self.instance_id)
                if self._registry_ws_client:
                    try:
                        await self._registry_ws_client.disconnect()
                    except Exception:
                        pass

                self._registry_ws_client = RegistryWebSocketClient(
                    registry_ws_url=ws_url,
                    instance_id=self.instance_id,
                    token=token_to_use
                )
                print(f"[RemoteBot] 重新连接注册服务器 WebSocket...")
                await self._registry_ws_client.connect()
                if self._registry_ws_client.is_connected:
                    self._listen_task = asyncio.create_task(self._listen_for_registry_messages())
                    print(f"[RemoteBot] 注册服务器 WebSocket 重新连接成功")
                else:
                    self._registry_ws_client = None
            except Exception as e:
                print(f"[RemoteBot] 重新连接注册服务器 WebSocket 失败: {e}")
                self._registry_ws_client = None

    async def stop(self):
        """停止远程功能"""
        if not self._started:
            return

        print(f"[RemoteBot] 停止远程 Bot 管理")

        try:
            # 停止心跳
            if self.registry_client:
                await self.registry_client.stop_heartbeat()

            # 关闭所有远程客户端
            for client in self.remote_clients.values():
                await client.disconnect()
            self.remote_clients.clear()

            # 关闭注册服务器 WebSocket 客户端
            if self._registry_ws_client:
                try:
                    await self._registry_ws_client.disconnect()
                except Exception:
                    pass
                self._registry_ws_client = None

            # 关闭注册服务器客户端
            if self.registry_client:
                await self.registry_client.__aexit__(None, None, None)

            self._started = False

        except Exception as e:
            print(f"[RemoteBot] 停止失败: {e}")

    async def _discovery_loop(self):
        """定期从中心服务器获取 Bot 信息"""
        # 启动时立即执行一次
        if self._started:
            try:
                await self._discover_bots()
            except Exception as e:
                print(f"[RemoteBot] 启动发现失败: {e}")

        while self._started:
            try:
                await asyncio.sleep(60)  # 每分钟发现一次
                await self._discover_bots()
            except Exception as e:
                print(f"[RemoteBot] 发现失败: {e}")
                import traceback
                traceback.print_exc()

    async def _heartbeat_loop(self):
        """定期向注册服务器发送心跳"""
        while self._started:
            try:
                await asyncio.sleep(30)  # 每 30 秒发送一次心跳
                # 刷新已发布 bot 的头像信息（确保 .bot.md 修改后同步到注册中心）
                if self.bot_publisher:
                    self.bot_publisher._notify_registry()
                if self.registry_client:
                    result = self.registry_client.send_heartbeat()
                    # 如果心跳返回 404 (Instance not found)，说明注册中心数据丢失，需要重新注册
                    if result and not result.get("success") and result.get("status_code") == 404:
                        print(f"[RemoteBot] 心跳 404，注册中心数据可能已丢失，尝试重新注册...")
                        register_success = await self.registry_client.register()
                        if register_success:
                            print(f"[RemoteBot] 重新注册成功，再次发送心跳")
                            result = self.registry_client.send_heartbeat()
                        else:
                            print(f"[RemoteBot] 重新注册失败")
                    # 处理心跳返回的好友列表（被对方接受的好友请求）
                    if result and result.get("success") and self.friend_manager:
                        # 同步 bot 级别好友
                        friend_bots = result.get("friend_bots", {})
                        for friend_instance_id, bot_ids in friend_bots.items():
                            for bot_id in bot_ids:
                                if bot_id == "__all__":
                                    if not self.friend_manager.is_friend(friend_instance_id):
                                        print(f"[RemoteBot] 心跳同步: 添加好友实例 {friend_instance_id}")
                                        self.friend_manager.add_friend(friend_instance_id)
                                elif not self.friend_manager.is_friend(friend_instance_id, bot_id):
                                    print(f"[RemoteBot] 心跳同步: 添加好友 bot {friend_instance_id}:{bot_id}")
                                    self.friend_manager.add_friend(friend_instance_id, bot_id)

                        # 向后兼容：同步实例级别好友
                        friends = result.get("friends", [])
                        for friend_inst in friends:
                            friend_id = friend_inst.get("instance_id")
                            if friend_id and not self.friend_manager.is_friend(friend_id):
                                print(f"[RemoteBot] 心跳同步: 添加好友实例 {friend_id}")
                                self.friend_manager.add_friend(friend_id)
            except Exception as e:
                print(f"[RemoteBot] 心跳失败: {e}")
                import traceback
                traceback.print_exc()

    async def _discover_bots(self):
        """执行一次发现"""
        if not self.registry_client:
            print(f"[RemoteBot] Discovery skipped: registry_client is None")
            return

        print(f"[RemoteBot] Starting discovery from {self.config.registry_url}")
        try:
            # 获取所有已发布的 Bot（以 Bot 为中心）
            all_bots = await asyncio.wait_for(
                self.registry_client.get_all_bots(),
                timeout=10.0
            )
            print(f"[RemoteBot] Discovery returned {len(all_bots)} bots from registry")
            if all_bots:
                print(f"[RemoteBot] Sample bot: {all_bots[0]}")
        except asyncio.TimeoutError:
            print(f"[RemoteBot] Discovery timeout after 10 seconds")
        except Exception as e:
            print(f"[RemoteBot] Discovery failed: {e}")
            import traceback
            traceback.print_exc()

        # 按 instance_id 分组 bot
        instance_bots = {}
        for bot in all_bots:
            instance_id = bot["instance_id"]

            # 排除自己
            if instance_id == self.instance_id:
                continue

            if instance_id not in instance_bots:
                instance_bots[instance_id] = {
                    "instance_id": instance_id,
                    "name": bot["instance_name"],
                    "host": bot["instance_host"],
                    "port": bot["instance_port"],
                    "published_bots": [],
                    "published_bots_info": []
                }

            # 添加 bot 信息
            avatar_image = bot.get("avatar_image") or bot.get("avatar_url", "")
            avatar_color = bot.get("avatar_color", "")
            avatar_icon = bot.get("avatar_icon", "")
            # 如果 avatar 是默认的紫色机器人且没有图片，清空 color/icon 让前端走哈希逻辑
            if not avatar_image and avatar_color == "from-purple-400 to-purple-600" and avatar_icon == "fa-robot":
                avatar_color = ""
                avatar_icon = ""
            bot_info = {
                "bot_id": bot["bot_id"],
                "display_name": bot["display_name"],
                "description": bot["description"],
                "capabilities": bot.get("capabilities", []),
                "is_sandboxed": bot.get("is_sandboxed", True),
                "requires_fs_access": bot.get("requires_fs_access", False),
                "avatar_color": avatar_color,
                "avatar_icon": avatar_icon,
                "avatar_image": avatar_image
            }

            instance_bots[instance_id]["published_bots"].append(bot["bot_id"])
            instance_bots[instance_id]["published_bots_info"].append(bot_info)

            # 更新远程 Bot 缓存
            full_bot_id = bot["full_bot_id"]
            if full_bot_id not in self.remote_bot_cache:
                # 创建 RemoteInstance 对象用于缓存
                instance = RemoteInstance.from_dict(instance_bots[instance_id])
                self.remote_bot_cache[full_bot_id] = instance

        # 更新已发现的实例
        for instance_id, inst_data in instance_bots.items():
            instance = RemoteInstance.from_dict(inst_data)
            # 同步好友状态
            if self.friend_manager:
                instance.is_friend = self.friend_manager.is_friend(instance_id)
            self.discovered_instances[instance_id] = instance

        if instance_bots:
            print(f"[RemoteBot] 发现 {len(instance_bots)} 个实例，共 {len(all_bots)} 个 Bot")

    def is_remote_bot(self, bot_id: str) -> bool:
        """检查是否是远程 Bot"""
        return ":" in bot_id  # 格式: instance_id:bot_id

    async def _listen_for_registry_messages(self):
        """监听来自注册服务器的转发消息（中心转发模式）"""
        if not self._registry_ws_client:
            return

        try:
            await self._registry_ws_client.listen_for_messages(self._handle_forwarded_message)
        except Exception as e:
            print(f"[RemoteBot] 监听注册服务器消息异常: {e}")

    async def _handle_forwarded_message(self, message: dict):
        """
        处理从注册服务器转发的消息

        Args:
            message: 转发的消息内容
        """
        msg_type = message.get("type")
        payload = message.get("payload", {})

        if msg_type == "forward":
            # 这是一个转发的消息
            payload_type = payload.get("type")
            from_instance = message.get("from_instance")

            print(f"[RemoteBot] 收到来自 {from_instance} 的转发消息: {payload_type}")

            # 如果是 bot_response，找到对应的等待器并设置结果
            if payload_type == "bot_response":
                message_id = payload.get("message_id")
                print(f"[RemoteBot] bot_response message_id={message_id}, clients={len(self.remote_clients)}")
                for cid, c in self.remote_clients.items():
                    print(f"[RemoteBot]   client {cid}: waiters={list(c._response_waiters.keys())}")
                # 遍历所有客户端查找匹配的等待器
                for client in self.remote_clients.values():
                    if message_id in client._response_waiters:
                        future = client._response_waiters.pop(message_id, None)
                        if future and not future.done():
                            future.set_result(payload.get("result"))
                            print(f"[RemoteBot] bot_response 已匹配并设置结果")
                        break
                else:
                    print(f"[RemoteBot] bot_response 未找到匹配的等待器")

            elif payload_type == "bot_call":
                # 中心转发模式：收到远程实例的 bot 调用请求
                bot_id = payload.get("bot_id")
                method = payload.get("method")
                params = payload.get("params", {})
                message_id = payload.get("message_id")

                print(f"[RemoteBot] 中心转发模式调用本地Bot: bot_id={bot_id}, method={method}")

                # 在后台任务中处理，避免阻塞消息监听
                asyncio.create_task(self._handle_center_bot_call(
                    from_instance=from_instance,
                    bot_id=bot_id,
                    method=method,
                    params=params,
                    message_id=message_id
                ))

    async def _handle_center_bot_call(self, from_instance: str, bot_id: str, method: str, params: dict, message_id: str):
        """处理中心转发模式的 bot 调用"""
        try:
            if not self._acp_mgr or not self._workspace_mgr:
                raise Exception("Bot dependencies not set (acp_mgr, workspace_mgr)")

            if bot_id not in self._bots:
                raise Exception(f"Bot '{bot_id}' not found")

            # 检查是否沙箱发布
            published_bot = None
            if self.bot_publisher:
                published_bot = self.bot_publisher.get_published_bot(bot_id)

            is_sandboxed = published_bot is not None and published_bot.is_sandboxed

            if is_sandboxed and self._sandbox_mgr and self._sandbox_mgr.is_available():
                print(f"[RemoteBot] Bot '{bot_id}' 将在沙箱中执行")
                result = await self._execute_in_sandbox(bot_id, method, params)

                # 通过注册中心发送响应回去
                if self._registry_ws_client and self._registry_ws_client.is_connected:
                    response_payload = {
                        "type": "bot_response",
                        "message_id": message_id,
                        "result": result
                    }
                    await self._registry_ws_client.send_to_instance(from_instance, response_payload)
                    print(f"[RemoteBot] 沙箱执行完成，已发送响应给 {from_instance}")
                else:
                    print(f"[RemoteBot] 注册中心未连接，无法发送响应")
                return

            if method == "chat":
                message = params.get("message", "")
                chat_id = params.get("chat_id", "remote-call")
                context_history = params.get("context_history", [])

                if context_history:
                    context_parts = ["以下是最近聊天记录上下文：\n"]
                    for msg in context_history[-30:]:
                        sender = msg.get('sender', 'unknown')
                        content = msg.get('content', '')
                        if sender == "user":
                            context_parts.append(f"用户: {content}")
                        elif sender == "system":
                            context_parts.append(content)
                        elif sender == bot_id:
                            context_parts.append(f"你(Bot): {content}")
                        else:
                            context_parts.append(f"其他Bot({sender}): {content}")
                    context_parts.append(f"\n用户当前消息：{message}\n\n请基于上下文回复用户的消息。")
                    final_prompt = "\n".join(context_parts)
                else:
                    final_prompt = message

                import os
                from concurrent.futures import ThreadPoolExecutor

                loop = asyncio.get_event_loop()
                collected_chunks = []

                def send_chunk(text: str, is_thinking: bool = False):
                    collected_chunks.append(text)

                def on_thinking(text: str):
                    pass

                def do_chat():
                    session_work_dir = self._workspace_mgr.get_session_workspace(
                        bot_id, chat_id, is_group=False
                    )
                    original_dir = os.getcwd()
                    os.chdir(session_work_dir)
                    os.environ['CLAWDBOZ_SESSION_WORK_DIR'] = session_work_dir
                    try:
                        future = asyncio.run_coroutine_threadsafe(
                            self._acp_mgr.get_or_create_client(chat_id, bot_id, is_group=False),
                            loop
                        )
                        acp_client = future.result(timeout=10)
                        if acp_client is None:
                            return "[无法创建 ACP 会话]"
                        result = acp_client.chat(
                            final_prompt,
                            on_chunk=send_chunk,
                            on_thinking=on_thinking,
                            timeout=180,
                            include_thinking_in_result=False
                        )
                        return result
                    finally:
                        os.chdir(original_dir)

                with ThreadPoolExecutor(max_workers=1) as executor:
                    future = executor.submit(do_chat)
                    response = await asyncio.wrap_future(future)

                result = {"success": True, "result": response}
            else:
                result = {"success": False, "error": f"Unknown method: {method}"}

            # 通过注册中心发送响应回去
            if self._registry_ws_client and self._registry_ws_client.is_connected:
                response_payload = {
                    "type": "bot_response",
                    "message_id": message_id,
                    "result": result
                }
                await self._registry_ws_client.send_to_instance(from_instance, response_payload)
                print(f"[RemoteBot] 中心转发模式 Bot调用完成，已发送响应给 {from_instance}")
            else:
                print(f"[RemoteBot] 注册中心未连接，无法发送响应")

        except Exception as e:
            print(f"[RemoteBot] 中心转发模式 Bot调用失败: {e}")
            import traceback
            traceback.print_exc()
            if self._registry_ws_client and self._registry_ws_client.is_connected:
                error_payload = {
                    "type": "bot_response",
                    "message_id": message_id,
                    "result": {"success": False, "error": str(e)}
                }
                await self._registry_ws_client.send_to_instance(from_instance, error_payload)

    async def _execute_in_sandbox(self, bot_id: str, method: str, params: dict) -> dict:
        """在 Docker 沙箱中执行 bot 调用"""
        try:
            if not self._sandbox_mgr:
                return {"success": False, "error": "Sandbox manager not initialized"}

            # 获取会话目录
            chat_id = params.get("chat_id", "remote-sandbox")
            workspace_dir = self._workspace_mgr.get_session_workspace(
                bot_id, chat_id, is_group=False
            )

            # 构建执行参数
            execute_params = {
                "message": params.get("message", ""),
                "chat_id": chat_id,
                "workspace_dir": workspace_dir,
                "context_history": params.get("context_history", [])
            }

            # 调用沙箱容器执行
            result = await self._sandbox_mgr.execute_bot(
                bot_id=bot_id,
                method=method,
                params=execute_params,
                timeout=180
            )

            if result.get("success"):
                sandbox_info = result.get("sandbox_info", {})
                print(f"[RemoteBot] 沙箱执行成功: workspace={sandbox_info.get('workspace_dir')}, "
                      f"hostname={sandbox_info.get('hostname')}")
            else:
                print(f"[RemoteBot] 沙箱执行失败: {result.get('error')}")

            return result

        except Exception as e:
            print(f"[RemoteBot] 沙箱执行异常: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False, "error": f"Sandbox execution error: {str(e)}"}

    async def call_remote_bot(
        self,
        bot_id: str,
        method: str,
        params: dict,
        chat_id: str,
        fs_api_url: str,
        timeout: int = 120
    ) -> Optional[dict]:
        """
        调用远程 Bot

        Args:
            bot_id: Bot ID (格式: instance_id:bot_id)
            method: 调用方法
            params: 参数
            chat_id: 会话 ID
            fs_api_url: 文件访问 API URL
            timeout: 超时时间

        Returns:
            Bot 响应结果
        """
        if not self._started:
            print(f"[RemoteBot] 远程功能未启动")
            return None

        try:
            # 解析 bot_id
            parts = bot_id.split(":", 1)
            if len(parts) != 2:
                print(f"[RemoteBot] 无效的远程 bot_id: {bot_id}")
                return None

            instance_id, remote_bot_id = parts

            # 获取远程实例
            instance = self.discovered_instances.get(instance_id)
            if not instance:
                print(f"[RemoteBot] 远程实例不存在: {instance_id}")
                return None

            # 检查是否是好友 (TEMPORARILY DISABLED FOR TESTING)
            # if not instance.is_friend:
            #     print(f"[RemoteBot] 实例不是好友: {instance_id}")
            #     return None
            print(f"[RemoteBot] WARNING: 跳过好友检查，允许与非好友实例通信")

            # 获取或创建客户端
            client = self.remote_clients.get(instance_id)
            if not client or not client.is_connected():
                # NEW: 传递连接模式、注册服务器 WebSocket 客户端和本地令牌
                # Use same token as local webchat for remote authentication
                remote_token = self.instance_info.get("token", "clawdboz-test-2024")

                client = RemoteBotClient(
                    instance_id=self.instance_id,
                    auto_reconnect=True,
                    connection_mode=self.config.connection_mode,
                    registry_ws_client=self._registry_ws_client,
                    local_token=remote_token
                )
                await client.connect_to_instance(instance)
                self.remote_clients[instance_id] = client

            # 生成 chat_token
            chat_token = self.token_manager.generate_chat_token(
                instance_id=self.instance_id,
                bot_id=remote_bot_id,
                chat_id=chat_id,
                ttl=3600
            )

            # 调用远程 Bot
            # client.call_remote_bot expects bot_id in format "instance_id:bot_id"
            full_bot_id = f"{instance_id}:{remote_bot_id}"
            result = await client.call_remote_bot(
                bot_id=full_bot_id,
                method=method,
                params=params,
                fs_api_url=fs_api_url,
                chat_token=chat_token,
                chat_id=chat_id,
                timeout=timeout
            )

            return result

        except Exception as e:
            print(f"[RemoteBot] 调用远程 Bot 失败: {e}")
            import traceback
            traceback.print_exc()
            return None

    def get_all_bots(self, local_bots: Dict[str, object]) -> Dict[str, dict]:
        """
        获取所有 Bot（本地 + 远程实例发布的 + 已连接的远程）

        Args:
            local_bots: 本地 Bot 字典

        Returns:
            所有 Bot 的字典 {bot_id: bot_info}
        """
        all_bots = {}

        # 添加本地 Bot
        for bot_id, bot in local_bots.items():
            all_bots[bot_id] = {
                "id": bot_id,
                "name": bot_id,
                "type": "local",
                "description": getattr(bot, '_system_prompt', '')[:100]
            }

        # 添加从中心服务器发现的其他实例发布的 Bot
        for instance_id, instance in self.discovered_instances.items():
            # 跳过自己
            if instance_id == self.instance_id:
                continue

            # 获取该实例的published_bots_info（包含完整信息）
            published_bots_info = getattr(instance, 'published_bots_info', None) or []

            # 如果有完整信息，使用完整信息
            if published_bots_info:
                for bot_info in published_bots_info:
                    full_bot_id = f"{instance_id}:{bot_info['bot_id']}"
                    all_bots[full_bot_id] = {
                        "id": full_bot_id,
                        "name": bot_info.get('display_name', bot_info['bot_id']),
                        "type": "remote",
                        "instance_id": instance_id,
                        "instance_name": instance.name,
                        "description": bot_info.get('description', f"Published bot from {instance.name}"),
                        "avatar_color": bot_info.get('avatar_color', ''),
                        "avatar_icon": bot_info.get('avatar_icon', ''),
                        "avatar_image": bot_info.get('avatar_image', ''),
                        "is_published": True
                    }
            else:
                # 兼容旧逻辑：只有bot ID列表
                for published_bot_id in instance.published_bots:
                    full_bot_id = f"{instance_id}:{published_bot_id}"
                    all_bots[full_bot_id] = {
                        "id": full_bot_id,
                        "name": published_bot_id,
                        "type": "remote",
                        "instance_id": instance_id,
                        "instance_name": instance.name,
                        "description": f"Published bot from {instance.name}",
                        "is_published": True
                    }

        # 添加已连接的远程 Bot（兼容旧逻辑）
        for full_bot_id, instance in self.remote_bot_cache.items():
            if instance.is_friend:  # 只显示好友的 Bot
                parts = full_bot_id.split(":", 1)
                if len(parts) == 2:
                    instance_id, remote_bot_id = parts
                    # 避免重复添加
                    if full_bot_id not in all_bots:
                        all_bots[full_bot_id] = {
                            "id": full_bot_id,
                            "name": remote_bot_id,
                            "type": "remote",
                            "instance_id": instance_id,
                            "instance_name": instance.name,
                            "description": f"Remote bot from {instance.name}"
                        }

        return all_bots

    async def get_all_bots_realtime(self, local_bots: Dict[str, object]) -> Dict[str, dict]:
        """
        实时从注册中心获取所有 Bot（本地 + 远程），不读缓存

        Args:
            local_bots: 本地 Bot 字典

        Returns:
            所有 Bot 的字典 {bot_id: bot_info}
        """
        all_bots = {}

        # 添加本地 Bot
        for bot_id, bot in local_bots.items():
            all_bots[bot_id] = {
                "id": bot_id,
                "name": bot_id,
                "type": "local",
                "description": getattr(bot, '_system_prompt', '')[:100]
            }

        # 实时从注册中心获取远程 Bot
        if self.registry_client:
            try:
                remote_bots = await self.registry_client.get_all_bots()
                for bot in remote_bots:
                    instance_id = bot.get("instance_id")
                    bot_id = bot.get("bot_id")

                    # 跳过自己
                    if not instance_id or not bot_id or instance_id == self.instance_id:
                        continue

                    full_bot_id = f"{instance_id}:{bot_id}"
                    avatar_image = bot.get("avatar_image") or bot.get("avatar_url", "")
                    avatar_color = bot.get("avatar_color", "")
                    avatar_icon = bot.get("avatar_icon", "")
                    # 如果 avatar 是默认的紫色机器人且没有图片，清空 color/icon 让前端走哈希逻辑
                    if not avatar_image and avatar_color == "from-purple-400 to-purple-600" and avatar_icon == "fa-robot":
                        avatar_color = ""
                        avatar_icon = ""
                    all_bots[full_bot_id] = {
                        "id": full_bot_id,
                        "bot_id": bot_id,
                        "name": bot.get("display_name") or bot_id,
                        "type": "remote",
                        "instance_id": instance_id,
                        "instance_name": bot.get("instance_name", instance_id),
                        "instance_host": bot.get("instance_host", ""),
                        "instance_port": bot.get("instance_port", 0),
                        "description": bot.get("description", ""),
                        "capabilities": bot.get("capabilities", []),
                        "is_sandboxed": bot.get("is_sandboxed", False),
                        "requires_fs_access": bot.get("requires_fs_access", False),
                        "avatar_color": avatar_color,
                        "avatar_icon": avatar_icon,
                        "avatar_image": avatar_image,
                        "status": bot.get("status", "unknown"),
                        "last_seen": bot.get("last_seen", 0),
                        "registered_at": bot.get("registered_at", 0),
                        "is_published": True
                    }
            except Exception as e:
                print(f"[RemoteBot] 实时获取远程 Bot 失败: {e}")

        return all_bots

    async def get_friends(self) -> List[dict]:
        """获取好友列表（Bot 级别，从注册中心同步最新状态）"""
        print(f"[RemoteBot] get_friends called, friend_manager={self.friend_manager is not None}, registry_client={self.registry_client is not None}")
        if not self.friend_manager or not self.registry_client:
            return []

        # 从注册中心获取实例列表（包含 friend_bots）
        try:
            instances = await self.registry_client.discover()
            print(f"[RemoteBot] discover returned {len(instances)} instances")
            for inst in instances:
                friend_bots = getattr(inst, 'friend_bots', [])
                print(f"[RemoteBot]   - {inst.instance_id}: is_friend={inst.is_friend}, friend_bots={friend_bots}")
        except Exception as e:
            print(f"[RemoteBot] 从注册中心获取好友状态失败: {e}")
            import traceback
            traceback.print_exc()
            instances = []

        # 筛选好友（排除自己）
        # 注意：不要在这里 add_friend 到本地缓存，get_friends 只是查询接口
        # 本地缓存的更新应该在 accept_friend_request 和 remove_friend 中进行
        friend_list = []
        for inst in instances:
            if inst.instance_id == self.instance_id:
                continue

            friend_bots = getattr(inst, 'friend_bots', [])
            if friend_bots:
                # Bot 级别好友
                for bot_id in friend_bots:
                    friend_list.append({
                        "instance_id": inst.instance_id,
                        "bot_id": bot_id,
                        "instance_name": inst.name,
                        "online": inst.is_online()
                    })
            elif inst.is_friend:
                # 向后兼容：实例级别好友
                friend_list.append({
                    "instance_id": inst.instance_id,
                    "bot_id": "__all__",
                    "instance_name": inst.name,
                    "online": inst.is_online()
                })

        # 去重：相同 instance_id + bot_id 只保留一条
        seen = set()
        unique_friends = []
        for f in friend_list:
            key = (f["instance_id"], f["bot_id"])
            if key not in seen:
                seen.add(key)
                unique_friends.append(f)

        print(f"[RemoteBot] get_friends returning {len(unique_friends)} unique friend entries")
        return unique_friends

    async def get_bot_friends(self, instance_id: str, bot_id: str) -> List[dict]:
        """获取添加了这个 bot 为好友的实例列表

        Args:
            instance_id: bot 所属实例 ID
            bot_id: bot ID

        Returns:
            好友实例列表
        """
        if not self.registry_client:
            print(f"[RemoteBot] registry_client is None, cannot get bot friends")
            return []

        try:
            friends = await self.registry_client.get_bot_friends(instance_id, bot_id)
            print(f"[RemoteBot] get_bot_friends({instance_id}:{bot_id}) returned {len(friends)} friends")
            return friends
        except Exception as e:
            print(f"[RemoteBot] 获取 bot 好友列表失败: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def remove_friend(self, instance_id: str, bot_id: str = "") -> bool:
        """移除好友（支持 Bot 级别）

        Args:
            instance_id: 实例 ID
            bot_id: Bot ID（为空则移除整个实例关系）

        Returns:
            是否移除成功
        """
        if not self.friend_manager:
            return False

        self.friend_manager.remove_friend(instance_id, bot_id)
        print(f"[RemoteBot] 已移除本地好友: {instance_id}:{bot_id or 'all'}")

        # 同步通知注册服务器移除好友关系
        if self.registry_client:
            try:
                result = await self.registry_client.remove_friend(instance_id, bot_id)
                if result.get("success"):
                    print(f"[RemoteBot] 已同步移除注册服务器好友关系: {instance_id}:{bot_id or 'all'}")
                else:
                    print(f"[RemoteBot] 同步移除注册服务器好友关系失败: {result}")
            except Exception as e:
                print(f"[RemoteBot] 同步移除注册服务器好友关系异常: {e}")

        return True

    def get_published_bots(self) -> List[dict]:
        """获取已发布的 Bot"""
        if not self.bot_publisher:
            return []

        published = self.bot_publisher.get_published_bots()
        return [
            {
                "bot_id": bot.bot_id,
                "display_name": bot.display_name,
                "description": bot.description,
                "enabled": bot.enabled,
                "is_sandboxed": bot.is_sandboxed,
                "requires_fs_access": bot.requires_fs_access
            }
            for bot in published
        ]

    async def add_remote_bot(self, instance_id: str, bot_id: str) -> bool:
        """
        添加远程Bot到本地实例

        Args:
            instance_id: 远程实例ID
            bot_id: 远程Bot ID

        Returns:
            是否添加成功
        """
        try:
            print(f"[RemoteBot] 添加远程Bot: {instance_id}:{bot_id}")

            # 注：不再自动添加为好友，好友关系应通过好友请求流程建立

            # 1. 保存到远程bot配置文件
            remote_bots_file = Path(self.base_workplace) / ".remote" / "added_bots.json"
            remote_bots_file.parent.mkdir(parents=True, exist_ok=True)

            # 读取已添加的远程bot
            added_bots = {}
            if remote_bots_file.exists():
                import json
                with open(remote_bots_file, 'r', encoding='utf-8') as f:
                    added_bots = json.load(f)

            # 添加新的bot
            full_bot_id = f"{instance_id}:{bot_id}"
            added_bots[full_bot_id] = {
                "instance_id": instance_id,
                "bot_id": bot_id,
                "added_at": 0  # 使用当前时间戳
            }

            # 保存
            import json
            with open(remote_bots_file, 'w', encoding='utf-8') as f:
                json.dump(added_bots, f, indent=2, ensure_ascii=False)

            print(f"[RemoteBot] 成功添加远程Bot: {full_bot_id}")
            return True

        except Exception as e:
            print(f"[RemoteBot] 添加远程Bot失败: {e}")
            import traceback
            traceback.print_exc()
            return False

    def get_remote_bot_info(self, full_bot_id: str) -> Optional[dict]:
        """获取远程Bot的完整信息（包括头像）

        Args:
            full_bot_id: 完整Bot ID (格式: instance_id:bot_id)

        Returns:
            Bot信息字典，或None
        """
        if not full_bot_id or ':' not in full_bot_id:
            return None

        parts = full_bot_id.split(':', 1)
        instance_id, bot_id = parts[0], parts[1]

        # 优先从 remote_bot_cache 查找（由 _discover_bots 填充）
        cached_instance = self.remote_bot_cache.get(full_bot_id)
        if cached_instance and hasattr(cached_instance, 'published_bots_info'):
            for bot_info in cached_instance.published_bots_info:
                if bot_info.get("bot_id") == bot_id:
                    return bot_info

        # 其次从 discovered_instances 查找
        instance = self.discovered_instances.get(instance_id)
        if instance:
            for bot_info in getattr(instance, 'published_bots_info', []):
                if bot_info.get("bot_id") == bot_id:
                    return bot_info

        return None

    def get_added_remote_bots(self) -> List[dict]:
        """
        获取已添加的远程Bot列表

        Returns:
            已添加的远程Bot列表
        """
        try:
            remote_bots_file = Path(self.base_workplace) / ".remote" / "added_bots.json"

            if not remote_bots_file.exists():
                return []

            import json
            with open(remote_bots_file, 'r', encoding='utf-8') as f:
                added_bots = json.load(f)

            # 添加详细信息（从发现缓存中补充头像）
            result = []
            for full_bot_id, info in added_bots.items():
                instance = self.discovered_instances.get(info["instance_id"])

                # 从远程 bot 缓存中查找头像信息
                avatar_color = ""
                avatar_icon = ""
                avatar_image = ""
                display_name = info["bot_id"]
                description = ""
                instance_name = info["instance_id"]
                
                # 优先从 remote_bot_cache 查找（由 _discover_bots 填充）
                cached_instance = self.remote_bot_cache.get(full_bot_id)
                if cached_instance and hasattr(cached_instance, 'published_bots_info'):
                    for bot_info in cached_instance.published_bots_info:
                        if bot_info.get("bot_id") == info["bot_id"]:
                            avatar_color = bot_info.get("avatar_color", "")
                            avatar_icon = bot_info.get("avatar_icon", "")
                            avatar_image = bot_info.get("avatar_image", "")
                            display_name = bot_info.get("display_name", info["bot_id"])
                            description = bot_info.get("description", "")
                            break
                
                # 其次从 discovered_instances 查找
                if instance and not avatar_color:
                    for bot_info in getattr(instance, 'published_bots_info', []):
                        if bot_info.get("bot_id") == info["bot_id"]:
                            avatar_color = bot_info.get("avatar_color", "")
                            avatar_icon = bot_info.get("avatar_icon", "")
                            avatar_image = bot_info.get("avatar_image", "")
                            display_name = bot_info.get("display_name", info["bot_id"])
                            description = bot_info.get("description", "")
                            break
                    instance_name = instance.name if instance.name else info["instance_id"]

                bot_info = {
                    "full_bot_id": full_bot_id,
                    "instance_id": info["instance_id"],
                    "bot_id": info["bot_id"],
                    "instance_name": instance_name,
                    "display_name": display_name,
                    "description": description,
                    "added_at": info.get("added_at", 0),
                    "avatar_color": avatar_color,
                    "avatar_icon": avatar_icon,
                    "avatar_image": avatar_image
                }

                result.append(bot_info)

            return result

        except Exception as e:
            print(f"[RemoteBot] 获取已添加的远程Bot失败: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def handle_remote_ws(self, websocket):
        """
        Handle incoming WebSocket connection from a remote instance

        Args:
            websocket: WebSocket connection
        """
        from fastapi import WebSocket
        import json

        try:
            print(f"[RemoteBot] 收到远程实例 WebSocket 连接")

            while True:
                # Receive message from remote instance
                data = await websocket.receive_json()
                print(f"[RemoteBot] 收到远程消息: {data.get('type')}")

                msg_type = data.get("type")

                if msg_type == "bot_call":
                    # Handle bot call
                    bot_id = data.get("bot_id")
                    method = data.get("method")
                    params = data.get("params", {})
                    message_id = data.get("message_id")

                    print(f"[RemoteBot] 调用本地Bot: bot_id={bot_id}, method={method}")

                    try:
                        # Check dependencies
                        if not self._acp_mgr or not self._workspace_mgr:
                            raise Exception("Bot dependencies not set (acp_mgr, workspace_mgr)")

                        # Get the bot
                        if bot_id not in self._bots:
                            raise Exception(f"Bot '{bot_id}' not found")

                        bot = self._bots[bot_id]

                        # Call the bot method
                        if method == "chat":
                            message = params.get("message", "")
                            chat_id = params.get("chat_id", "remote-call")
                            context_history = params.get("context_history", [])

                            # Build contextual prompt if history is provided
                            if context_history:
                                context_parts = ["以下是最近聊天记录上下文：\n"]
                                for msg in context_history[-30:]:
                                    sender = msg.get('sender', 'unknown')
                                    content = msg.get('content', '')
                                    if sender == "user":
                                        context_parts.append(f"用户: {content}")
                                    elif sender == "system":
                                        context_parts.append(content)
                                    elif sender == bot_id:
                                        context_parts.append(f"你(Bot): {content}")
                                    else:
                                        context_parts.append(f"其他Bot({sender}): {content}")
                                context_parts.append(f"\n用户当前消息：{message}\n\n请基于上下文回复用户的消息。")
                                final_prompt = "\n".join(context_parts)
                                print(f"[RemoteBot] 使用群聊上下文 prompt，历史记录数: {len(context_history)}")
                            else:
                                final_prompt = message

                            # Use thread pool to call bot (similar to _call_bot_chat)
                            import time as time_module
                            import os
                            import json
                            from concurrent.futures import ThreadPoolExecutor
                            import asyncio

                            loop = asyncio.get_event_loop()
                            collected_chunks = []

                            def send_chunk(text: str, is_thinking: bool = False):
                                collected_chunks.append(text)

                            def on_thinking(text: str):
                                pass  # Don't send thinking in remote calls

                            def do_chat():
                                # Get session workspace
                                session_work_dir = self._workspace_mgr.get_session_workspace(
                                    bot_id, chat_id, is_group=False
                                )

                                original_dir = os.getcwd()
                                os.chdir(session_work_dir)
                                os.environ['CLAWDBOZ_SESSION_WORK_DIR'] = session_work_dir

                                try:
                                    # Create or get ACP client
                                    future = asyncio.run_coroutine_threadsafe(
                                        self._acp_mgr.get_or_create_client(chat_id, bot_id, is_group=False),
                                        loop
                                    )
                                    acp_client = future.result(timeout=10)

                                    if acp_client is None:
                                        return "[无法创建 ACP 会话]"

                                    # Call bot with contextual prompt
                                    result = acp_client.chat(
                                        final_prompt,
                                        on_chunk=send_chunk,
                                        on_thinking=on_thinking,
                                        timeout=180,
                                        include_thinking_in_result=False
                                    )
                                    return result
                                finally:
                                    os.chdir(original_dir)

                            # Execute in thread pool
                            with ThreadPoolExecutor(max_workers=1) as executor:
                                future = executor.submit(do_chat)
                                response = await asyncio.wrap_future(future)

                            result = {
                                "success": True,
                                "result": response
                            }
                        else:
                            result = {
                                "success": False,
                                "error": f"Unknown method: {method}"
                            }

                        # Send response back
                        response_msg = {
                            "type": "bot_response",
                            "message_id": message_id,
                            "result": result
                        }
                        await websocket.send_json(response_msg)
                        print(f"[RemoteBot] Bot调用完成，已发送响应")

                    except Exception as e:
                        print(f"[RemoteBot] Bot调用失败: {e}")
                        import traceback
                        traceback.print_exc()

                        error_response = {
                            "type": "bot_response",
                            "message_id": message_id,
                            "result": {
                                "success": False,
                                "error": str(e)
                            }
                        }
                        await websocket.send_json(error_response)

                else:
                    print(f"[RemoteBot] 未知消息类型: {msg_type}")

        except Exception as e:
            print(f"[RemoteBot] WebSocket 处理错误: {e}")
            import traceback
            traceback.print_exc()

