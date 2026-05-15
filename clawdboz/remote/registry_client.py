"""
注册服务器客户端
"""
import aiohttp
import asyncio
import time
import uuid
from typing import List, Optional, Dict
from clawdboz.remote.instance import RemoteInstance, InstanceStatus


class RegistryClient:
    """注册服务器客户端"""

    def __init__(
        self,
        registry_url: str,
        instance_info: dict,
        auto_heartbeat: bool = True
    ):
        """
        初始化注册客户端

        Args:
            registry_url: 注册服务器 URL
            instance_info: 实例信息
            auto_heartbeat: 是否自动发送心跳
        """
        self.registry_url = registry_url.rstrip('/')
        self.instance_info = instance_info
        self.auto_heartbeat = auto_heartbeat

        self.session: Optional[aiohttp.ClientSession] = None
        self._heartbeat_task: Optional[asyncio.Task] = None
        self._running = False
        self._ssl = False

    async def __aenter__(self):
        """异步上下文管理器入口"""
        connector = aiohttp.TCPConnector(ssl=self._ssl)
        self.session = aiohttp.ClientSession(connector=connector)
        return self

    async def __aexit__(self, *args):
        """异步上下文管理器出口"""
        if self.session:
            await self.session.close()

    async def register(self) -> bool:
        """
        注册实例到注册服务器

        Returns:
            是否注册成功
        """
        url = f"{self.registry_url}/api/registry/register"

        try:
            async with self.session.post(url, json=self.instance_info, ssl=self._ssl) as resp:
                if resp.status != 200:
                    print(f"[Registry] 注册失败: {resp.status}")
                    return False

                data = await resp.json()
                return data.get("success", False)

        except Exception as e:
            print(f"[Registry] 注册异常: {e}")
            return False

    def send_heartbeat(self) -> dict:
        """
        发送心跳（同步版本，避免 aiohttp 上下文问题）

        Returns:
            心跳响应数据
        """
        url = f"{self.registry_url}/api/registry/heartbeat"

        payload = {
            "instance_id": self.instance_info["instance_id"],
            "token": self.instance_info["token"],
            "published_bots": self.instance_info.get("published_bots", []),
            "published_bots_info": self.instance_info.get("published_bots_info", [])
        }

        try:
            # 使用同步 requests 库
            import requests
            resp = requests.post(url, json=payload, timeout=10, verify=False)
            if resp.status_code != 200:
                detail = ""
                try:
                    detail = resp.json().get("detail", "")
                except Exception:
                    pass
                print(f"[Registry] 心跳失败: {resp.status_code}, detail={detail}")
                return {"success": False, "status_code": resp.status_code, "detail": detail}

            return resp.json()

        except Exception as e:
            print(f"[Registry] 心跳异常: {e}")
            return {"success": False, "status_code": 0, "detail": str(e)}

    async def discover(self) -> List[RemoteInstance]:
        """
        发现实例

        Returns:
            实例列表
        """
        url = f"{self.registry_url}/api/registry/discover"
        instance_id = self.instance_info["instance_id"]

        try:
            # 使用同步 requests 库避免 aiohttp 上下文问题
            import requests
            resp = requests.get(url, params={"instance_id": instance_id}, timeout=10, verify=False)
            if resp.status_code != 200:
                print(f"[Registry] 发现失败: {resp.status_code}")
                return []

            data = resp.json()
            instances = []

            for inst_data in data.get("instances", []):
                instances.append(RemoteInstance.from_dict(inst_data))

            return instances

        except Exception as e:
            print(f"[Registry] 发现异常: {e}")
            return []

    async def get_all_bots(self) -> List[dict]:
        """
        获取所有已发布的 Bot（以 Bot 为中心的数据结构）

        Returns:
            Bot 列表
        """
        url = f"{self.registry_url}/api/registry/bots"

        try:
            # Use synchronous requests in executor to avoid aiohttp hanging
            import requests
            print(f"[Registry] Fetching bots from {url} using requests")
            resp = requests.get(url, timeout=10, verify=False)
            print(f"[Registry] Got response: status_code={resp.status_code}")
            if resp.status_code != 200:
                print(f"[Registry] 获取 Bot 列表失败: {resp.status_code}")
                return []

            data = resp.json()
            bots = data.get("bots", [])
            print(f"[Registry] Retrieved {len(bots)} bots")
            return bots

        except Exception as e:
            print(f"[Registry] 获取 Bot 列表异常: {e}")
            return []

    async def send_friend_request(
        self,
        to_instance: str,
        message: str = "",
        request_id: str = None,
        to_bot_id: str = "",
        from_bot_id: str = ""
    ) -> dict:
        """
        发送好友请求（同步版本，避免 aiohttp 上下文问题）

        Args:
            to_instance: 目标实例 ID
            message: 附加消息
            request_id: 可选的请求 ID（由调用方提供，确保一致性）
            to_bot_id: 目标 bot ID（bot 级别好友）
            from_bot_id: 发起方 bot ID（bot 级别好友）

        Returns:
            响应数据
        """
        url = f"{self.registry_url}/api/registry/friend-request"

        if request_id is None:
            request_id = str(uuid.uuid4())

        payload = {
            "request_id": request_id,
            "from_instance": self.instance_info["instance_id"],
            "to_instance": to_instance,
            "from_bot_id": from_bot_id,
            "to_bot_id": to_bot_id,
            "from_token": self.instance_info["token"],
            "message": message
        }

        try:
            # 使用同步 requests 库避免 FastAPI asyncio 上下文问题
            import requests
            resp = requests.post(url, json=payload, timeout=10, verify=False)
            if resp.status_code != 200:
                print(f"[Registry] 好友请求失败: {resp.status_code}")
                return {"success": False}

            return resp.json()

        except Exception as e:
            print(f"[Registry] 好友请求异常: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False}

    async def accept_friend_request(
        self,
        request_id: str,
        accept: bool = True
    ) -> dict:
        """
        确认/拒绝好友请求

        Args:
            request_id: 请求 ID
            accept: 是否接受

        Returns:
            响应数据
        """
        url = f"{self.registry_url}/api/registry/friend-accept"

        payload = {
            "request_id": request_id,
            "token": self.instance_info["token"],
            "accept": accept
        }

        try:
            # 创建新的 session 避免超时上下文管理器问题
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
                async with session.post(url, json=payload, ssl=False) as resp:
                    if resp.status != 200:
                        print(f"[Registry] 好友确认失败: {resp.status}")
                        return {"success": False}

                    return await resp.json()

        except Exception as e:
            print(f"[Registry] 好友确认异常: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False}

    async def remove_friend(self, instance_id: str, bot_id: str = "") -> dict:
        """
        移除好友关系（支持 bot 级别）

        Args:
            instance_id: 要移除的实例 ID
            bot_id: 要移除的 bot ID（为空则移除整个实例关系）

        Returns:
            响应数据
        """
        url = f"{self.registry_url}/api/registry/friend-remove"

        payload = {
            "instance_id": instance_id,
            "bot_id": bot_id,
            "token": self.instance_info["token"]
        }

        try:
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
                async with session.post(url, json=payload, ssl=False) as resp:
                    if resp.status != 200:
                        print(f"[Registry] 移除好友失败: {resp.status}")
                        return {"success": False}
                    return await resp.json()
        except Exception as e:
            print(f"[Registry] 移除好友异常: {e}")
            import traceback
            traceback.print_exc()
            return {"success": False}

    async def get_friend_requests(self) -> List[dict]:
        """
        获取待处理的好友请求

        Returns:
            好友请求列表
        """
        url = f"{self.registry_url}/api/registry/friend-requests"
        instance_id = self.instance_info["instance_id"]

        try:
            if self.session is None:
                print(f"[Registry] Session is None, cannot get friend requests")
                return []

            # 创建新的 session 避免超时上下文管理器问题
            async with aiohttp.ClientSession(connector=aiohttp.TCPConnector(ssl=False)) as session:
                async with session.get(url, params={"instance_id": instance_id}, ssl=False) as resp:
                    if resp.status != 200:
                        print(f"[Registry] 获取好友请求失败: HTTP {resp.status}")
                        return []

                    data = await resp.json()
                    requests = data.get("requests", [])
                    print(f"[Registry] 获取到 {len(requests)} 个好友请求")
                    return requests

        except Exception as e:
            print(f"[Registry] 获取好友请求异常: {e}")
            import traceback
            traceback.print_exc()
            return []

    async def start_heartbeat(self, interval: int = 30):
        """
        启动心跳线程

        Args:
            interval: 心跳间隔（秒）
        """
        if self._heartbeat_task is not None:
            return  # 已经在运行

        self._running = True

        async def heartbeat_loop():
            while self._running:
                self.send_heartbeat()  # 同步调用
                await asyncio.sleep(interval)

        self._heartbeat_task = asyncio.create_task(heartbeat_loop())

    async def stop_heartbeat(self):
        """停止心跳线程"""
        self._running = False

        if self._heartbeat_task is not None:
            self._heartbeat_task.cancel()
            try:
                await self._heartbeat_task
            except asyncio.CancelledError:
                pass
            self._heartbeat_task = None
