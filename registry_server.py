"""
注册服务器 - 独立进程

提供 Bot 发现、实例管理等功能
以 Bot 为中心的数据结构，bot_id 为唯一标识符
"""
import asyncio
import uuid
import time
from typing import Dict, List, Optional
from datetime import datetime, timedelta
from fastapi import FastAPI, HTTPException, WebSocket, WebSocketDisconnect, Query
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel


# ============================================================================
# 数据模型
# ============================================================================

class InstanceRegisterRequest(BaseModel):
    """实例注册请求"""
    instance_id: str
    name: str
    host: str
    port: int
    token: str
    fs_api_enabled: bool = True


class HeartbeatRequest(BaseModel):
    """心跳请求"""
    instance_id: str
    token: str
    published_bots: List[str] = []
    published_bots_info: List[dict] = []  # 完整的bot信息


class FriendRequest(BaseModel):
    """好友请求"""
    request_id: str
    from_instance: str
    to_instance: str
    from_bot_id: str = ""   # NEW: 发起请求的 bot
    to_bot_id: str = ""     # NEW: 目标 bot
    from_token: str
    message: str = ""


class FriendAccept(BaseModel):
    """好友确认"""
    request_id: str
    token: str
    accept: bool


class FriendRemove(BaseModel):
    """好友移除"""
    instance_id: str
    bot_id: str = ""        # NEW: 指定移除的 bot（为空则移除整个实例关系）
    token: str


# ============================================================================
# 注册服务器
# ============================================================================

class RegistryServer:
    """注册服务器核心逻辑 - 以 Bot 为中心"""

    def __init__(self):
        # 存储 Bot 信息，key 为 "instance_id:bot_id"
        self.bots: Dict[str, dict] = {}

        # 存储实例信息（仅用于实例管理和好友功能）
        self.instances: Dict[str, dict] = {}

        # 存储好友请求
        self.friend_requests: Dict[str, dict] = {}

        # WebSocket 连接（用于推送通知）
        self.websockets: Dict[str, WebSocket] = {}

        # NEW: 实例 WebSocket 连接（用于中心转发模式）
        self.instance_connections: Dict[str, WebSocket] = {}

        # NEW: 离线实例的消息队列 {instance_id: [messages]}
        self.message_queue: Dict[str, list] = {}

    def _make_bot_key(self, instance_id: str, bot_id: str) -> str:
        """生成 bot 的唯一键"""
        return f"{instance_id}:{bot_id}"

    def register_instance(self, req: InstanceRegisterRequest) -> dict:
        """注册实例"""
        instance_id = req.instance_id

        # 检查是否已注册
        if instance_id in self.instances:
            # 更新现有实例
            self.instances[instance_id].update({
                "name": req.name,
                "host": req.host,
                "port": req.port,
                "token": req.token,
                "fs_api_enabled": req.fs_api_enabled,
                "last_seen": time.time()
            })
        else:
            # 新实例
            self.instances[instance_id] = {
                "instance_id": instance_id,
                "name": req.name,
                "host": req.host,
                "port": req.port,
                "token": req.token,
                "fs_api_enabled": req.fs_api_enabled,
                "status": "online",
                "is_friend": False,
                "last_seen": time.time(),
                "created_at": time.time()
            }

        return {"success": True, "instance_id": instance_id}

    def handle_heartbeat(self, req: HeartbeatRequest) -> dict:
        """处理心跳 - 更新 Bot 信息"""
        instance_id = req.instance_id

        if instance_id not in self.instances:
            raise HTTPException(status_code=404, detail="Instance not found")

        # 更新实例心跳时间
        self.instances[instance_id]["last_seen"] = time.time()
        self.instances[instance_id]["status"] = "online"

        # 删除该实例之前的所有 Bot（重新发布）
        bots_to_remove = [
            bot_key for bot_key in self.bots.keys()
            if bot_key.startswith(f"{instance_id}:")
        ]
        for bot_key in bots_to_remove:
            del self.bots[bot_key]

        # 添加新的 Bot 信息
        instance_info = self.instances[instance_id]
        for bot_info in req.published_bots_info:
            bot_key = self._make_bot_key(instance_id, bot_info["bot_id"])

            self.bots[bot_key] = {
                # Bot 基本信息
                "bot_id": bot_info["bot_id"],
                "full_bot_id": bot_key,  # instance_id:bot_id
                "display_name": bot_info.get("display_name", bot_info["bot_id"]),
                "description": bot_info.get("description", ""),
                "capabilities": bot_info.get("capabilities", []),
                "is_sandboxed": bot_info.get("is_sandboxed", False),
                "requires_fs_access": bot_info.get("requires_fs_access", False),

                # 所属实例信息
                "instance_id": instance_id,
                "instance_name": instance_info["name"],
                "instance_host": instance_info["host"],
                "instance_port": instance_info["port"],

                # 状态信息
                "status": "online",
                "last_seen": time.time(),
                "registered_at": time.time()
            }

        # 获取待处理的好友请求
        pending_requests = [
            req for req in self.friend_requests.values()
            if req["to_instance"] == instance_id and req["status"] == "pending"
        ]

        # 获取好友列表（双向：既包括别人请求我的，也包括我请求别人的）
        friend_instance_ids = set()
        friend_bots = {}  # NEW: instance_id -> {bot_id, ...}
        for friend_req in self.friend_requests.values():
            if friend_req.get("status") == "accepted":
                from_inst = friend_req.get("from_instance", "")
                to_inst = friend_req.get("to_instance", "")
                from_bot = friend_req.get("from_bot_id", "")
                to_bot = friend_req.get("to_bot_id", "")

                if from_inst == instance_id:
                    friend_instance_ids.add(to_inst)
                    if to_bot:
                        friend_bots.setdefault(to_inst, set()).add(to_bot)
                    elif from_bot:
                        friend_bots.setdefault(to_inst, set()).add(from_bot)
                    else:
                        friend_bots.setdefault(to_inst, set()).add("__all__")
                elif to_inst == instance_id:
                    friend_instance_ids.add(from_inst)
                    if from_bot:
                        friend_bots.setdefault(from_inst, set()).add(from_bot)
                    elif to_bot:
                        friend_bots.setdefault(from_inst, set()).add(to_bot)
                    else:
                        friend_bots.setdefault(from_inst, set()).add("__all__")

        friends = [
            inst for inst in self.instances.values()
            if inst["is_friend"] and inst["instance_id"] in friend_instance_ids
        ]

        # 清理过期实例（每次心跳时触发）
        self._cleanup_expired_instances()

        return {
            "success": True,
            "pending_requests": pending_requests,
            "friends": friends,
            "friend_bots": {k: list(v) for k, v in friend_bots.items()},
            "bots_updated": len(req.published_bots_info)
        }

    def _cleanup_expired_instances(self, max_idle_seconds: float = 300.0):
        """清理超过指定时间未发送心跳的实例及其 Bot

        Args:
            max_idle_seconds: 最大空闲时间（秒），默认 5 分钟
        """
        now = time.time()
        expired_instances = []

        for instance_id, inst_data in list(self.instances.items()):
            if now - inst_data.get("last_seen", 0) > max_idle_seconds:
                expired_instances.append(instance_id)

        if not expired_instances:
            return

        for instance_id in expired_instances:
            # 删除该实例的所有 Bot
            bots_to_remove = [
                bot_key for bot_key in list(self.bots.keys())
                if bot_key.startswith(f"{instance_id}:")
            ]
            for bot_key in bots_to_remove:
                del self.bots[bot_key]

            # 删除实例
            del self.instances[instance_id]

            # 清理 WebSocket 连接
            if instance_id in self.instance_connections:
                del self.instance_connections[instance_id]

            # 清理消息队列
            if instance_id in self.message_queue:
                del self.message_queue[instance_id]

            print(f"[Registry] 清理过期实例: {instance_id} (idle > {max_idle_seconds}s)")

    def discover_bots(self) -> dict:
        """发现所有 Bot - 以 Bot 为中心"""
        bots_list = []

        for bot_key, bot_data in self.bots.items():
            # 检查 Bot 是否在线（所属实例 60 秒内有心跳）
            instance_id = bot_data["instance_id"]
            instance = self.instances.get(instance_id)

            if instance:
                is_online = (time.time() - instance["last_seen"]) < 60
                bot_data["status"] = "online" if is_online else "offline"
            else:
                bot_data["status"] = "offline"

            bots_list.append(bot_data)

        return {
            "success": True,
            "bots": bots_list,
            "total": len(bots_list)
        }

    def get_bot_by_id(self, bot_id: str) -> Optional[dict]:
        """根据 Bot ID 查询 Bot 信息

        Args:
            bot_id: Bot ID（格式：instance_id:bot_id 或仅 bot_id）

        Returns:
            Bot 信息，如果未找到则返回 None
        """
        # 直接查找
        if bot_id in self.bots:
            return self.bots[bot_id]

        # 如果不包含实例ID前缀，尝试匹配所有bot
        if ":" not in bot_id:
            for bot_key, bot_data in self.bots.items():
                if bot_data["bot_id"] == bot_id:
                    return bot_data

        return None

    def discover_instances(self, instance_id: str) -> dict:
        """发现实例（保留用于兼容）"""
        instances = []

        # 收集该实例视角的 bot 级别好友
        friend_bots = {}  # instance_id -> {bot_id, ...}
        for friend_req in self.friend_requests.values():
            if friend_req.get("status") == "accepted":
                from_inst = friend_req.get("from_instance", "")
                to_inst = friend_req.get("to_instance", "")
                from_bot = friend_req.get("from_bot_id", "")
                to_bot = friend_req.get("to_bot_id", "")

                if from_inst == instance_id:
                    if to_bot:
                        friend_bots.setdefault(to_inst, set()).add(to_bot)
                    elif from_bot:
                        friend_bots.setdefault(to_inst, set()).add(from_bot)
                elif to_inst == instance_id:
                    if from_bot:
                        friend_bots.setdefault(from_inst, set()).add(from_bot)
                    elif to_bot:
                        friend_bots.setdefault(from_inst, set()).add(to_bot)

        for inst_id, inst_data in self.instances.items():
            # 检查实例是否在线（60 秒内有心跳）
            is_online = (time.time() - inst_data["last_seen"]) < 60

            # 统计该实例发布的 Bot 数量
            bot_count = sum(
                1 for bot_key in self.bots.keys()
                if bot_key.startswith(f"{inst_id}:")
            )

            instances.append({
                "instance_id": inst_id,
                "name": inst_data["name"],
                "status": "online" if is_online else "offline",
                "is_friend": inst_data["is_friend"],
                "friend_bots": list(friend_bots.get(inst_id, [])),
                "fs_api_enabled": inst_data.get("fs_api_enabled", True),
                "bot_count": bot_count
            })

        return {"success": True, "instances": instances}

    def send_friend_request(self, req: FriendRequest) -> dict:
        """发送好友请求"""
        # 检查目标实例是否存在
        if req.to_instance not in self.instances:
            raise HTTPException(status_code=404, detail="Target instance not found")

        # 创建好友请求
        self.friend_requests[req.request_id] = {
            "request_id": req.request_id,
            "from_instance": req.from_instance,
            "to_instance": req.to_instance,
            "from_bot_id": req.from_bot_id,
            "to_bot_id": req.to_bot_id,
            "from_token": req.from_token,
            "message": req.message,
            "status": "pending",
            "created_at": time.time()
        }

        # 通过 WebSocket 推送通知给目标实例
        if req.to_instance in self.instance_connections:
            try:
                notification = {
                    "type": "friend_request_notification",
                    "request_id": req.request_id,
                    "from_instance": req.from_instance,
                    "message": req.message,
                    "timestamp": time.time()
                }
                # 使用 asyncio.create_task 在后台发送
                import asyncio
                asyncio.create_task(
                    self.instance_connections[req.to_instance].send_json(notification)
                )
                print(f"[Registry] 已推送好友请求通知到 {req.to_instance}: {req.request_id}")
            except Exception as e:
                print(f"[Registry] 推送好友请求通知失败: {e}")

        return {"success": True, "request_id": req.request_id}

    def accept_friend_request(self, req: FriendAccept) -> dict:
        """确认好友请求"""
        request_id = req.request_id

        if request_id not in self.friend_requests:
            raise HTTPException(status_code=404, detail="Friend request not found")

        friend_req = self.friend_requests[request_id]

        if req.accept:
            # 更新请求状态
            friend_req["status"] = "accepted"
            friend_req["accepted_at"] = time.time()

            # 更新双方的 friend 状态
            from_inst = friend_req["from_instance"]
            to_inst = friend_req["to_instance"]

            if from_inst in self.instances:
                self.instances[from_inst]["is_friend"] = True
            if to_inst in self.instances:
                self.instances[to_inst]["is_friend"] = True

        else:
            # 拒绝好友请求
            friend_req["status"] = "rejected"

            # 如果没有其他 accepted 请求关联这两个实例，清除 is_friend
            from_inst = friend_req["from_instance"]
            to_inst = friend_req["to_instance"]
            has_other_accepted = any(
                r["status"] == "accepted" and
                ((r["from_instance"] == from_inst and r["to_instance"] == to_inst) or
                 (r["from_instance"] == to_inst and r["to_instance"] == from_inst))
                for r in self.friend_requests.values()
                if r["request_id"] != request_id
            )
            if not has_other_accepted:
                if from_inst in self.instances:
                    self.instances[from_inst]["is_friend"] = False
                if to_inst in self.instances:
                    self.instances[to_inst]["is_friend"] = False

        return {"success": True}

    def remove_friend(self, instance_id: str, remover_id: str, bot_id: str = "") -> dict:
        """移除好友关系（支持 bot 级别）"""
        if instance_id not in self.instances:
            raise HTTPException(status_code=404, detail="Instance not found")

        # 删除双方之间的 accepted 好友请求
        requests_to_remove = []
        for req_id, req in self.friend_requests.items():
            if req["status"] != "accepted":
                continue

            involves_pair = (
                (req["from_instance"] == remover_id and req["to_instance"] == instance_id) or
                (req["from_instance"] == instance_id and req["to_instance"] == remover_id)
            )
            if not involves_pair:
                continue

            if bot_id:
                # Bot 级别移除：只删除涉及该 bot 的请求
                req_bots = [req.get("from_bot_id", ""), req.get("to_bot_id", "")]
                if bot_id in req_bots:
                    requests_to_remove.append(req_id)
            else:
                # 实例级别移除（向后兼容）
                requests_to_remove.append(req_id)

        for req_id in requests_to_remove:
            del self.friend_requests[req_id]

        # 检查是否还有其他 accepted 请求关联这两个实例
        has_other_accepted = any(
            r["status"] == "accepted" and
            ((r["from_instance"] == remover_id and r["to_instance"] == instance_id) or
             (r["from_instance"] == instance_id and r["to_instance"] == remover_id))
            for r in self.friend_requests.values()
        )

        # 如果没有其他 accepted 请求，清除 is_friend
        if not has_other_accepted:
            if remover_id in self.instances:
                self.instances[remover_id]["is_friend"] = False
            if instance_id in self.instances:
                self.instances[instance_id]["is_friend"] = False

        return {"success": True, "removed_requests": len(requests_to_remove)}

    def get_bot_friends(self, instance_id: str, bot_id: str) -> List[dict]:
        """获取添加了这个 bot 为好友的实例列表

        Args:
            instance_id: bot 所属实例 ID
            bot_id: bot ID

        Returns:
            好友实例列表，每项包含 instance_id, instance_name, bot_id
        """
        friends = []
        seen = set()
        full_bot_id = f"{instance_id}:{bot_id}"

        for req in self.friend_requests.values():
            if req["status"] != "accepted":
                continue

            # 情况1: 该 bot 是目标（to）
            if req["to_instance"] == instance_id and req.get("to_bot_id") == bot_id:
                friend_inst_id = req["from_instance"]
                friend_bot_id = req.get("from_bot_id", "")
                key = (friend_inst_id, friend_bot_id)
                if key not in seen:
                    seen.add(key)
                    inst = self.instances.get(friend_inst_id, {})
                    friends.append({
                        "instance_id": friend_inst_id,
                        "instance_name": inst.get("name", friend_inst_id),
                        "bot_id": friend_bot_id,
                        "full_bot_id": f"{friend_inst_id}:{friend_bot_id}" if friend_bot_id else friend_inst_id,
                        "added_at": req.get("accepted_at", 0)
                    })

            # 情况2: 该 bot 是发起方（from）
            elif req["from_instance"] == instance_id and req.get("from_bot_id") == bot_id:
                friend_inst_id = req["to_instance"]
                friend_bot_id = req.get("to_bot_id", "")
                key = (friend_inst_id, friend_bot_id)
                if key not in seen:
                    seen.add(key)
                    inst = self.instances.get(friend_inst_id, {})
                    friends.append({
                        "instance_id": friend_inst_id,
                        "instance_name": inst.get("name", friend_inst_id),
                        "bot_id": friend_bot_id,
                        "full_bot_id": f"{friend_inst_id}:{friend_bot_id}" if friend_bot_id else friend_inst_id,
                        "added_at": req.get("accepted_at", 0)
                    })

        # 按添加时间排序
        friends.sort(key=lambda x: x["added_at"], reverse=True)
        return friends

    async def handle_instance_websocket(self, websocket: WebSocket, instance_id: str, token: str):
        """
        处理实例的 WebSocket 连接（中心转发模式）

        Args:
            websocket: WebSocket 连接对象
            instance_id: 实例 ID
            token: 认证令牌
        """
        # 验证实例是否存在
        if instance_id not in self.instances:
            await websocket.close(code=4008, reason=f"Instance {instance_id} not registered")
            return

        instance = self.instances[instance_id]

        # 验证 JWT token（使用共享密钥）
        try:
            import jwt
            # 解码 token（验证签名和实例 ID）
            payload = jwt.decode(
                token,
                "clawdboz-remote-secret-key-2024",  # TODO: 从配置获取
                algorithms=["HS256"]
            )

            # 验证实例 ID 是否匹配
            if payload.get("instance_id") != instance_id:
                await websocket.close(code=4008, reason="Token instance_id mismatch")
                return

            # Token 有效 - 更新实例的 token（如果有需要）
            # 注：不再做精确字符串匹配，因为 JWT 包含时间戳

        except jwt.ExpiredSignatureError:
            await websocket.close(code=4008, reason="Token expired")
            return
        except jwt.InvalidTokenError as e:
            await websocket.close(code=4008, reason=f"Invalid token: {str(e)}")
            return

        # 接受连接
        await websocket.accept()

        # 如果该实例已有连接，关闭旧连接（防止孤儿连接）
        if instance_id in self.instance_connections:
            old_ws = self.instance_connections[instance_id]
            try:
                await old_ws.close(code=4009, reason="Connection replaced")
                print(f"[Registry] 关闭实例 {instance_id} 的旧 WebSocket 连接")
            except Exception:
                pass

        # 存储连接
        self.instance_connections[instance_id] = websocket
        print(f"[Registry] 实例 {instance_id} 已连接到 WebSocket (连接数: {len(self.instance_connections)})")

        try:
            # 发送队列中的消息
            if instance_id in self.message_queue:
                queued_messages = self.message_queue[instance_id]
                if queued_messages:
                    print(f"[Registry] 发送 {len(queued_messages)} 条队列消息到 {instance_id}")
                    for msg in queued_messages:
                        await websocket.send_json(msg)
                    # 清空队列
                    self.message_queue[instance_id] = []

            # 监听来自实例的消息
            while True:
                data = await websocket.receive_json()

                # 处理转发消息
                if data.get("type") == "forward":
                    await self.forward_message_to_instance(
                        from_instance=data.get("from_instance"),
                        to_instance=data.get("to_instance"),
                        message=data
                    )

        except Exception as e:
            print(f"[Registry] WebSocket 异常: {e}")
        finally:
            # 清理连接：只删除当前 websocket，避免覆盖后新连接被误删
            if instance_id in self.instance_connections and self.instance_connections[instance_id] == websocket:
                del self.instance_connections[instance_id]
            print(f"[Registry] 实例 {instance_id} 断开 WebSocket 连接 (剩余连接: {len(self.instance_connections)})")

    async def forward_message_to_instance(self, from_instance: str, to_instance: str, message: dict):
        """
        转发消息到目标实例

        Args:
            from_instance: 发送方实例 ID
            to_instance: 接收方实例 ID
            message: 消息内容
        """
        # 检查目标实例是否在线（有 WebSocket 连接）
        if to_instance in self.instance_connections:
            # 目标在线 - 立即转发
            try:
                await self.instance_connections[to_instance].send_json(message)
                print(f"[Registry] 转发消息: {from_instance} -> {to_instance}")
            except Exception as e:
                print(f"[Registry] 转发失败: {e}")
                # 转发失败，加入队列
                self._enqueue_message(to_instance, message)
        else:
            # 目标离线 - 加入队列
            print(f"[Registry] 目标实例 {to_instance} 离线，消息加入队列")
            self._enqueue_message(to_instance, message)

    def _enqueue_message(self, instance_id: str, message: dict):
        """
        将消息加入队列

        Args:
            instance_id: 实例 ID
            message: 消息内容
        """
        if instance_id not in self.message_queue:
            self.message_queue[instance_id] = []

        # 加入队列
        self.message_queue[instance_id].append(message)

        # 限制队列大小（最多 100 条消息）
        if len(self.message_queue[instance_id]) > 100:
            # 删除最旧的消息
            self.message_queue[instance_id].pop(0)
            print(f"[Registry] 实例 {instance_id} 队列已满，删除最旧的消息")


# ============================================================================
# FastAPI 应用
# ============================================================================

app = FastAPI(title="Clawdboz Registry Server")
registry = RegistryServer()

# 添加 CORS 中间件
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"]
)


# ============================================================================
# API 路由
# ============================================================================

@app.post("/api/registry/register")
async def register_instance(req: InstanceRegisterRequest):
    """注册实例"""
    try:
        result = registry.register_instance(req)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/registry/heartbeat")
async def heartbeat(req: HeartbeatRequest):
    """心跳"""
    try:
        result = registry.handle_heartbeat(req)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/registry/bots")
async def discover_bots():
    """发现所有 Bot - 以 Bot 为中心的数据结构"""
    try:
        result = registry.discover_bots()
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/registry/bots/{bot_id}")
async def get_bot_by_id(bot_id: str):
    """根据 Bot ID 查询 Bot 信息

    Args:
        bot_id: Bot ID（格式：instance_id:bot_id 或仅 bot_id）

    Returns:
        Bot 信息
    """
    try:
        result = registry.get_bot_by_id(bot_id)
        if not result:
            raise HTTPException(status_code=404, detail=f"Bot '{bot_id}' not found")
        return {"success": True, "bot": result}
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/registry/discover")
async def discover_instances(instance_id: str):
    """发现实例（保留用于兼容）"""
    try:
        result = registry.discover_instances(instance_id)
        return result
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/registry/friend-request")
async def send_friend_request(req: FriendRequest):
    """发送好友请求"""
    try:
        result = registry.send_friend_request(req)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/registry/friend-requests")
async def get_friend_requests(instance_id: str):
    """获取待处理的好友请求"""
    try:
        pending = [
            req for req in registry.friend_requests.values()
            if req["to_instance"] == instance_id and req["status"] == "pending"
        ]
        return {"success": True, "requests": pending}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/registry/friend-accept")
async def accept_friend_request(req: FriendAccept):
    """确认/拒绝好友请求"""
    try:
        result = registry.accept_friend_request(req)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/registry/friend-remove")
async def remove_friend(req: FriendRemove):
    """移除好友关系"""
    try:
        # 验证 token
        import jwt
        payload = jwt.decode(
            req.token,
            "clawdboz-remote-secret-key-2024",
            algorithms=["HS256"]
        )
        remover_id = payload.get("instance_id")
        if not remover_id:
            raise HTTPException(status_code=401, detail="Invalid token")

        result = registry.remove_friend(req.instance_id, remover_id, req.bot_id)
        return result
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/registry/bot-friends")
async def get_bot_friends(instance_id: str = Query(...), bot_id: str = Query(...)):
    """获取添加了这个 bot 为好友的实例列表"""
    try:
        friends = registry.get_bot_friends(instance_id, bot_id)
        return {"success": True, "friends": friends}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/api/registry/instances")
async def list_instances():
    """列出所有实例"""
    try:
        instances = list(registry.instances.values())
        return {"success": True, "instances": instances}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.websocket("/ws/registry")
async def registry_websocket(websocket: WebSocket, instance_id: str = Query(...), token: str = Query(...)):
    """
    注册服务器 WebSocket 端点（中心转发模式）

    实例连接到此端点后，注册服务器会转发消息到其他实例。
    """
    await registry.handle_instance_websocket(websocket, instance_id, token)


@app.get("/api/registry/queue/{instance_id}")
async def get_queued_messages(instance_id: str):
    """
    获取实例的队列消息（备用轮询接口）

    Args:
        instance_id: 实例 ID

    Returns:
        该实例的队列消息
    """
    try:
        messages = registry.message_queue.get(instance_id, [])
        return {"success": True, "instance_id": instance_id, "messages": messages}
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.post("/api/registry/clear")
async def clear_registry():
    """清除所有已发布的 Bot 和过时实例数据（管理端点）"""
    try:
        cleared_bots = len(registry.bots)
        cleared_instances = len(registry.instances)
        registry.bots.clear()
        registry.instances.clear()
        registry.friend_requests.clear()
        registry.message_queue.clear()
        return {
            "success": True,
            "message": "Registry cleared successfully",
            "cleared_bots": cleared_bots,
            "cleared_instances": cleared_instances
        }
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e))


@app.get("/")
async def root():
    """根路径"""
    return {
        "service": "Clawdboz Registry Server",
        "version": "2.0.0",
        "data_structure": "bot-centric",
        "status": "running"
    }


# ============================================================================
# 主函数
# ============================================================================

if __name__ == "__main__":
    import uvicorn

    # 运行服务器
    uvicorn.run(
        app,
        host="0.0.0.0",
        port=6902,
        log_level="info"
    )
