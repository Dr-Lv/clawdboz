"""
远程 Bot 管理器
集成远程 Bot 发布、发现和调用功能
"""
import asyncio
import json
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

        # RSA 加密管理器
        from clawdboz.remote.crypto import InstanceCrypto
        self.crypto = InstanceCrypto(base_workplace)

        # 本地 Bot 订阅者存储 {bot_id: {subscriber_instance_id: {instance_name, added_at}}}
        self.bot_subscribers: Dict[str, Dict[str, dict]] = {}
        self._load_bot_subscribers()

    def _load_bot_subscribers(self):
        """从本地文件加载 bot 订阅者"""
        try:
            subs_file = Path(self.base_workplace) / ".remote" / "bot_subscribers.json"
            if subs_file.exists():
                import json
                with open(subs_file, 'r', encoding='utf-8') as f:
                    data = json.load(f)
                self.bot_subscribers = data
                print(f"[RemoteBot] 加载了 {len(data)} 个 bot 的订阅者")
        except Exception as e:
            print(f"[RemoteBot] 加载 bot_subscribers 失败: {e}")
            self.bot_subscribers = {}

    def _save_bot_subscribers(self):
        """保存 bot 订阅者到本地文件"""
        try:
            subs_file = Path(self.base_workplace) / ".remote" / "bot_subscribers.json"
            subs_file.parent.mkdir(parents=True, exist_ok=True)
            import json
            with open(subs_file, 'w', encoding='utf-8') as f:
                json.dump(self.bot_subscribers, f, indent=2, ensure_ascii=False)
        except Exception as e:
            print(f"[RemoteBot] 保存 bot_subscribers 失败: {e}")

    def add_bot_subscriber(self, subscriber_instance_id: str, subscriber_name: str, bot_id: str):
        """添加一个 bot 订阅者"""
        if bot_id not in self.bot_subscribers:
            self.bot_subscribers[bot_id] = {}
        self.bot_subscribers[bot_id][subscriber_instance_id] = {
            "instance_name": subscriber_name or subscriber_instance_id,
            "added_at": asyncio.get_event_loop().time() if hasattr(asyncio, 'get_event_loop') else 0
        }
        self._save_bot_subscribers()
        print(f"[RemoteBot] Bot {bot_id} 新增订阅者: {subscriber_instance_id}")

    def remove_bot_subscriber(self, subscriber_instance_id: str, bot_id: str):
        """移除一个 bot 订阅者。如果 bot_id 为空，则移除该实例的所有订阅"""
        removed = False
        if bot_id:
            if bot_id in self.bot_subscribers and subscriber_instance_id in self.bot_subscribers[bot_id]:
                del self.bot_subscribers[bot_id][subscriber_instance_id]
                if not self.bot_subscribers[bot_id]:
                    del self.bot_subscribers[bot_id]
                removed = True
                print(f"[RemoteBot] Bot {bot_id} 移除订阅者: {subscriber_instance_id}")
        else:
            # bot_id 为空，移除该实例的所有订阅
            bots_to_remove = []
            for b_id, subscribers in self.bot_subscribers.items():
                if subscriber_instance_id in subscribers:
                    del subscribers[subscriber_instance_id]
                    if not subscribers:
                        bots_to_remove.append(b_id)
                    removed = True
                    print(f"[RemoteBot] Bot {b_id} 移除订阅者: {subscriber_instance_id}")
            for b_id in bots_to_remove:
                del self.bot_subscribers[b_id]
        if removed:
            self._save_bot_subscribers()

    def _add_to_added_bots(self, instance_id: str, bot_id: str):
        """将远程 bot 添加到本地 added_bots.json（用于双向添加）"""
        try:
            remote_bots_file = Path(self.base_workplace) / ".remote" / "added_bots.json"
            remote_bots_file.parent.mkdir(parents=True, exist_ok=True)

            added_bots = {}
            if remote_bots_file.exists():
                with open(remote_bots_file, 'r', encoding='utf-8') as f:
                    added_bots = json.load(f)

            full_bot_id = f"{instance_id}:{bot_id}"
            if full_bot_id not in added_bots:
                added_bots[full_bot_id] = {
                    "instance_id": instance_id,
                    "bot_id": bot_id,
                    "added_at": 0
                }
                with open(remote_bots_file, 'w', encoding='utf-8') as f:
                    json.dump(added_bots, f, indent=2, ensure_ascii=False)
                print(f"[RemoteBot] 双向添加: {full_bot_id} 已写入 added_bots.json")
        except Exception as e:
            print(f"[RemoteBot] 双向添加失败: {e}")

    def get_bot_subscribers(self, bot_id: str) -> List[dict]:
        """获取订阅了某个 bot 的实例列表"""
        subscribers = self.bot_subscribers.get(bot_id, {})
        return [
            {
                "instance_id": sid,
                "instance_name": info.get("instance_name", sid),
                "added_at": info.get("added_at", 0)
            }
            for sid, info in subscribers.items()
        ]

    async def _notify_target_instance(self, target_instance_id: str, payload: dict):
        """向目标实例发送订阅/解除通知"""
        # 从注册服务器获取目标实例信息
        if not self.registry_client:
            return False
        try:
            instances = await self.registry_client.discover()
            target = None
            for inst in instances:
                if inst.instance_id == target_instance_id:
                    target = inst
                    break
            if not target:
                print(f"[RemoteBot] 未找到目标实例: {target_instance_id}")
                return False

            url = f"{target.http_url}/api/remote/subscribe-notification"
            token = self.token_manager.generate_instance_token(self.instance_id)
            import aiohttp
            use_ssl = url.startswith("https://")
            async with aiohttp.ClientSession() as session:
                async with session.post(url, json=payload, headers={"X-Instance-Token": token}, ssl=use_ssl, timeout=aiohttp.ClientTimeout(total=10)) as resp:
                    return resp.status == 200
        except Exception as e:
            print(f"[RemoteBot] 通知目标实例失败: {e}")
            return False

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

            # 初始化好友管理器（去中心化 + RSA）
            async def on_friend_accepted(from_instance, bot_id):
                """好友请求被接受后，通过 WS 发送自己的公钥给对方
                同时在本地 bot_subscribers 中记录对方订阅了这个 bot
                并更新 added_bots.json（记录自己添加了对方的 bot）
                """
                try:
                    # 记录对方实例订阅了这个 bot（接受方视角）
                    if bot_id:
                        self.add_bot_subscriber(
                            from_instance,
                            self.discovered_instances.get(from_instance, {}).name if hasattr(self.discovered_instances.get(from_instance, {}), 'name') else from_instance,
                            bot_id
                        )
                        print(f"[RemoteBot] 已记录订阅者: {from_instance} 订阅了 {bot_id}")
                except Exception as e:
                    print(f"[RemoteBot] 记录 bot 订阅者失败（非阻塞）: {e}")

                # FIX: 主动接受好友请求时，也要在本地 added_bots.json 中记录对方的 bot
                try:
                    if bot_id:
                        self._add_to_added_bots(from_instance, bot_id)
                        print(f"[RemoteBot] 已记录添加的远程 bot: {from_instance}:{bot_id}")
                except Exception as e:
                    print(f"[RemoteBot] 记录 added_bots 失败（非阻塞）: {e}")

                # 3. 通过 WS 通知对方（去中心化）
                ws_sent = False
                try:
                    if self._registry_ws_client and self._registry_ws_client.is_connected:
                        await self._registry_ws_client.send_to_instance(
                            from_instance,
                            {
                                "type": "friend_accept",
                                "from_instance": self.instance_id,
                                "bot_id": bot_id,
                                "public_key": self.crypto.get_public_key_pem()
                            }
                        )
                        print(f"[RemoteBot] 已通过 WS 发送接受通知给 {from_instance}")
                        ws_sent = True
                except Exception as e:
                    print(f"[RemoteBot] 发送好友接受通知失败（非阻塞）: {e}")

                # 4. HTTP fallback：无论 WS 是否成功，都通过 HTTP 直接通知对方
                #    因为 WS 发送可能成功但注册中心未实际转发，双通道确保可靠性
                try:
                    await self._notify_target_instance(
                        from_instance,
                        {
                            "action": "add",
                            "subscriber_instance_id": self.instance_id,
                            "subscriber_instance_name": getattr(self.registry_client.instance_info, 'name', self.instance_id),
                            "bot_id": bot_id
                        }
                    )
                    print(f"[RemoteBot] 已通过 HTTP fallback 通知 {from_instance} 添加好友关系")
                except Exception as e:
                    print(f"[RemoteBot] HTTP fallback 通知失败（非阻塞）: {e}")

            async def on_friend_removed(instance_id, bot_id):
                """收到对方解除好友通知后的清理"""
                try:
                    # 清理 bot_subscribers.json
                    self.remove_bot_subscriber(instance_id, bot_id or "")
                    # 清理 added_bots.json
                    self._remove_added_bot(instance_id, bot_id or "")
                    print(f"[RemoteBot] 已自动清理 {instance_id} 的订阅/添加记录")
                except Exception as e:
                    print(f"[RemoteBot] 自动清理失败（非阻塞）: {e}")

            self.friend_manager = FriendManager(
                self.registry_client,
                crypto=self.crypto,
                base_workplace=self.base_workplace,
                on_friend_accepted=on_friend_accepted,
                on_friend_removed=on_friend_removed
            )

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
                    # 注册中心不再返回好友关系（去中心化设计）
                    # 好友关系由各实例本地管理，通过 WS 直接通信
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

            elif payload_type == "friend_request_notification":
                # 收到好友请求通知（注册中心转发）
                print(f"[RemoteBot] 收到好友请求通知 from {from_instance}")
                if self.friend_manager:
                    self.friend_manager.receive_friend_request(payload)

            elif payload_type == "friend_accept":
                # 收到好友接受通知
                print(f"[RemoteBot] 收到好友接受通知 from {from_instance}")
                if self.friend_manager:
                    self.friend_manager.receive_friend_accept(payload)
                # 同步更新 added_bots.json（记录自己添加了对方的 bot）
                try:
                    bot_id = payload.get("bot_id", "")
                    if bot_id:
                        self._add_to_added_bots(from_instance, bot_id)
                        print(f"[RemoteBot] 收到接受通知后已更新 added_bots: {from_instance}:{bot_id}")
                except Exception as e:
                    print(f"[RemoteBot] 更新 added_bots 失败（非阻塞）: {e}")

            elif payload_type == "friend_remove":
                # 收到好友解除通知
                print(f"[RemoteBot] 收到好友解除通知 from {from_instance}")
                if self.friend_manager:
                    self.friend_manager.receive_friend_remove(payload)

    async def _handle_center_bot_call(self, from_instance: str, bot_id: str, method: str, params: dict, message_id: str):
        """处理中心转发模式的 bot 调用"""
        try:
            # 检查好友关系（Bot 级别）
            if self.friend_manager and not self.friend_manager.is_friend(from_instance, bot_id):
                print(f"[RemoteBot] 拒绝调用: {from_instance} 不是 {bot_id} 的好友")
                if self._registry_ws_client and self._registry_ws_client.is_connected:
                    response_payload = {
                        "type": "bot_response",
                        "message_id": message_id,
                        "result": {
                            "success": False,
                            "error": "NOT_FRIEND",
                            "error_message": "对方已解除好友关系，无法发送消息"
                        }
                    }
                    await self._registry_ws_client.send_to_instance(from_instance, response_payload)
                return

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

            # 调用沙箱容器执行（传入 ACP 配置以确保挂载正确）
            from clawdboz.config import CONFIG
            result = await self._sandbox_mgr.execute_bot(
                bot_id=bot_id,
                method=method,
                params=execute_params,
                timeout=180,
                acp_config=CONFIG.get("acp", {})
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
            full_bot_id = f"{instance_id}:{remote_bot_id}"

            # 获取远程实例
            instance = self.discovered_instances.get(instance_id)
            if not instance:
                print(f"[RemoteBot] 远程实例不存在: {instance_id}")
                return None

            # 检查本地是否还添加了这个 bot（调用方视角）
            if not self._check_added_bot(instance_id, remote_bot_id):
                print(f"[RemoteBot] 本地未添加该 bot: {full_bot_id}")
                return {
                    "success": False,
                    "error": "NOT_ADDED",
                    "error_message": "您尚未添加该 Bot，请先添加好友"
                }

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

            # 检查是否被对方解除好友（NOT_SUBSCRIBED 来自直接 WS，NOT_FRIEND 来自中心转发）
            if result and isinstance(result, dict):
                remote_error = result.get("error", "")
                if remote_error in ("NOT_SUBSCRIBED", "NOT_FRIEND"):
                    print(f"[RemoteBot] 被对方解除好友: {full_bot_id} (error={remote_error})")
                    # 从本地 added_bots.json 中删除
                    self._remove_added_bot(instance_id, remote_bot_id)
                    # 同时清理本地好友关系（如果还有的话）
                    if self.friend_manager:
                        self.friend_manager.remove_friend(instance_id, remote_bot_id)
                    # 返回带明确提示的错误
                    return {
                        "success": False,
                        "error": "NOT_FRIEND",
                        "error_message": "对方已解除好友关系，无法发送消息"
                    }

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

        # 读取已添加的远程bot
        added_bot_keys = set()
        try:
            remote_bots_file = Path(self.base_workplace) / ".remote" / "added_bots.json"
            if remote_bots_file.exists():
                import json
                with open(remote_bots_file, 'r', encoding='utf-8') as f:
                    added_bots_data = json.load(f)
                added_bot_keys = set(added_bots_data.keys())
        except Exception as e:
            print(f"[RemoteBot] 读取已添加bot失败: {e}")

        # 实时从注册中心获取远程 Bot
        registry_bots_found = False
        if self.registry_client:
            try:
                remote_bots = await self.registry_client.get_all_bots()
                if remote_bots:
                    registry_bots_found = True
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
                        "is_published": True,
                        "is_added": full_bot_id in added_bot_keys,
                        "is_friend": self.friend_manager.is_friend(instance_id, bot_id) if self.friend_manager else False
                    }
            except Exception as e:
                print(f"[RemoteBot] 实时获取远程 Bot 失败: {e}")

        # 如果 Registry /api/registry/bots 返回空，回退到 discovered_instances 数据
        if not registry_bots_found and self.discovered_instances:
            print(f"[RemoteBot] Registry /api/registry/bots 为空，使用 discovered_instances 回退 ({len(self.discovered_instances)} 个实例)")
            for instance_id, instance in self.discovered_instances.items():
                if instance_id == self.instance_id:
                    continue
                published_bots_info = getattr(instance, 'published_bots_info', None) or []
                for bot_info in published_bots_info:
                    bot_id = bot_info.get('bot_id')
                    if not bot_id:
                        continue
                    full_bot_id = f"{instance_id}:{bot_id}"
                    if full_bot_id in all_bots:
                        continue
                    avatar_image = bot_info.get("avatar_image") or bot_info.get("avatar_url", "")
                    avatar_color = bot_info.get("avatar_color", "")
                    avatar_icon = bot_info.get("avatar_icon", "")
                    if not avatar_image and avatar_color == "from-purple-400 to-purple-600" and avatar_icon == "fa-robot":
                        avatar_color = ""
                        avatar_icon = ""
                    all_bots[full_bot_id] = {
                        "id": full_bot_id,
                        "bot_id": bot_id,
                        "name": bot_info.get('display_name', bot_id),
                        "type": "remote",
                        "instance_id": instance_id,
                        "instance_name": getattr(instance, 'name', instance_id),
                        "instance_host": getattr(instance, 'host', ''),
                        "instance_port": getattr(instance, 'port', 0),
                        "description": bot_info.get('description', ''),
                        "capabilities": bot_info.get('capabilities', []),
                        "is_sandboxed": bot_info.get('is_sandboxed', False),
                        "requires_fs_access": bot_info.get('requires_fs_access', False),
                        "avatar_color": avatar_color,
                        "avatar_icon": avatar_icon,
                        "avatar_image": avatar_image,
                        "status": getattr(instance, 'status', 'unknown'),
                        "last_seen": getattr(instance, 'last_seen', 0),
                        "registered_at": bot_info.get('registered_at', 0),
                        "is_published": True,
                        "is_added": full_bot_id in added_bot_keys,
                        "is_friend": self.friend_manager.is_friend(instance_id, bot_id) if self.friend_manager else False
                    }

        return all_bots

    async def get_friends(self) -> List[dict]:
        """获取好友列表（Bot 级别，从本地内存读取）"""
        print(f"[RemoteBot] get_friends called, friend_manager={self.friend_manager is not None}")
        if not self.friend_manager:
            return []

        # 去中心化设计：好友关系只从本地 FriendManager 读取
        friends = self.friend_manager.get_friends()

        # 补充实例信息和 bot 名称
        friend_list = []
        for f in friends:
            instance_id = f["instance_id"]
            bot_id = f["bot_id"]

            # 从 discovered_instances 获取实例信息
            instance = self.discovered_instances.get(instance_id)
            instance_name = instance.name if instance else instance_id
            online = instance.is_online() if instance else False

            # 查找 bot 名称
            bot_name = bot_id
            if instance and bot_id and bot_id != "__all__":
                for bot in instance.published_bots_info:
                    if bot.get("bot_id") == bot_id:
                        bot_name = bot.get("display_name") or bot_id
                        break
            elif bot_id == "__all__":
                bot_name = "__all__（实例级别）"

            friend_list.append({
                "instance_id": instance_id,
                "bot_id": bot_id,
                "bot_name": bot_name,
                "instance_name": instance_name,
                "online": online
            })

        print(f"[RemoteBot] get_friends returning {len(friend_list)} friend entries")
        return friend_list

    async def get_bot_friends(self, instance_id: str, bot_id: str) -> List[dict]:
        """获取添加了这个 bot 为好友的实例列表（从本地读取）

        Args:
            instance_id: bot 所属实例 ID
            bot_id: bot ID

        Returns:
            好友实例列表
        """
        # 只查询本实例的 bot 订阅者
        if instance_id != self.instance_id:
            print(f"[RemoteBot] 只能查询本实例的 bot 好友列表")
            return []

        friends = self.get_bot_subscribers(bot_id)
        print(f"[RemoteBot] get_bot_friends({instance_id}:{bot_id}) returned {len(friends)} friends from local")
        return friends

    async def remove_friend(self, instance_id: str, bot_id: str = "") -> bool:
        """移除好友（支持 Bot 级别）
        先删除本地密钥和关系，然后通过 WS 通知对方
        """
        if not self.friend_manager:
            return False

        # 1. 删除本地密钥和好友关系
        self.friend_manager.remove_friend(instance_id, bot_id)
        print(f"[RemoteBot] 已移除本地好友: {instance_id}:{bot_id or 'all'}")

        # 2. 清理 bot_subscribers.json（对方订阅了我）
        self.remove_bot_subscriber(instance_id, bot_id or "")

        # 3. 清理 added_bots.json（我添加了对方的 bot）
        self._remove_added_bot(instance_id, bot_id or "")

        # 4. 通过 WS 通知对方（去中心化）
        if self._registry_ws_client and self._registry_ws_client.is_connected:
            try:
                await self._registry_ws_client.send_to_instance(
                    instance_id,
                    {
                        "type": "friend_remove",
                        "from_instance": self.instance_id,
                        "bot_id": bot_id
                    }
                )
                print(f"[RemoteBot] 已通过 WS 通知 {instance_id} 解除好友")
            except Exception as e:
                print(f"[RemoteBot] WS 通知解除好友失败（非阻塞）: {e}")

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
                "requires_fs_access": bot.requires_fs_access,
                "avatar_color": bot.avatar_color,
                "avatar_icon": bot.avatar_icon,
                "avatar_image": bot.avatar_image
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

            # 向目标实例发送订阅通知（去中心化）
            try:
                notified = await self._notify_target_instance(
                    instance_id,
                    {
                        "action": "add",
                        "subscriber_instance_id": self.instance_id,
                        "subscriber_instance_name": self.instance_info.get("name", self.instance_id),
                        "bot_id": bot_id
                    }
                )
                if notified:
                    print(f"[RemoteBot] 已通知目标实例: {full_bot_id}")
                else:
                    print(f"[RemoteBot] 通知目标实例失败（非阻塞）: {full_bot_id}")
            except Exception as e:
                print(f"[RemoteBot] 通知目标实例异常（非阻塞）: {e}")

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

    def _check_added_bot(self, instance_id: str, bot_id: str) -> bool:
        """检查本地 added_bots.json 中是否包含指定的远程Bot"""
        try:
            remote_bots_file = Path(self.base_workplace) / ".remote" / "added_bots.json"
            if not remote_bots_file.exists():
                return False

            import json
            with open(remote_bots_file, 'r', encoding='utf-8') as f:
                added_bots = json.load(f)

            full_bot_id = f"{instance_id}:{bot_id}"
            return full_bot_id in added_bots

        except Exception as e:
            print(f"[RemoteBot] 检查 added_bots 失败: {e}")
            return False

    def _remove_added_bot(self, instance_id: str, bot_id: str):
        """从本地 added_bots.json 中删除已添加的远程Bot。如果 bot_id 为空，则删除该实例的所有 bot"""
        try:
            remote_bots_file = Path(self.base_workplace) / ".remote" / "added_bots.json"
            if not remote_bots_file.exists():
                return

            with open(remote_bots_file, 'r', encoding='utf-8') as f:
                added_bots = json.load(f)

            removed_any = False
            if bot_id:
                full_bot_id = f"{instance_id}:{bot_id}"
                if full_bot_id in added_bots:
                    del added_bots[full_bot_id]
                    removed_any = True
                    print(f"[RemoteBot] 已删除 added_bots.json 中的: {full_bot_id}")
            else:
                # bot_id 为空，删除该实例下的所有 bot
                keys_to_remove = [k for k in added_bots.keys() if k.startswith(f"{instance_id}:")]
                for k in keys_to_remove:
                    del added_bots[k]
                    removed_any = True
                if keys_to_remove:
                    print(f"[RemoteBot] 已删除 added_bots.json 中的: {keys_to_remove}")

            if removed_any:
                with open(remote_bots_file, 'w', encoding='utf-8') as f:
                    json.dump(added_bots, f, indent=2, ensure_ascii=False)

            # 同时从 discovered_instances 的 is_friend 标记中清除
            instance = self.discovered_instances.get(instance_id)
            if instance:
                instance.is_friend = False
                print(f"[RemoteBot] 已清除实例 {instance_id} 的好友标记")

        except Exception as e:
            print(f"[RemoteBot] 删除 added_bots 失败: {e}")
            import traceback
            traceback.print_exc()

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
                    from_instance = data.get("from_instance", "")

                    print(f"[RemoteBot] 调用本地Bot: bot_id={bot_id}, method={method}, from={from_instance}")

                    # 检查好友关系（Bot 级别）
                    if self.friend_manager and not self.friend_manager.is_friend(from_instance, bot_id or ""):
                        print(f"[RemoteBot] 拒绝调用: {from_instance} 不是 {bot_id} 的好友")
                        error_response = {
                            "type": "bot_response",
                            "message_id": message_id,
                            "result": {
                                "success": False,
                                "error": "NOT_FRIEND",
                                "error_message": "对方已解除好友关系，无法发送消息"
                            }
                        }
                        await websocket.send_json(error_response)
                        continue

                    # 检查调用方是否还在订阅者列表中（兼容旧逻辑）
                    if from_instance and bot_id:
                        subscribers = self.bot_subscribers.get(bot_id, {})
                        if from_instance not in subscribers:
                            print(f"[RemoteBot] 拒绝调用: {from_instance} 不在 {bot_id} 的订阅者列表中")
                            error_response = {
                                "type": "bot_response",
                                "message_id": message_id,
                                "result": {
                                    "success": False,
                                    "error": "NOT_SUBSCRIBED",
                                    "error_message": "对方已解除好友关系，无法发送消息"
                                }
                            }
                            await websocket.send_json(error_response)
                            continue

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

