"""
远程 Bot API 路由
提供远程 Bot 的发布、发现和好友管理 API
"""
from typing import List, Optional, TYPE_CHECKING
from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import FileResponse
from pydantic import BaseModel
import os


if TYPE_CHECKING:
    from ..server import WebChatServer


if TYPE_CHECKING:
    from ..server import WebChatServer


# ============================================================================
# 数据模型
# ============================================================================

class PublishBotRequest(BaseModel):
    """发布 Bot 请求"""
    bot_id: str
    display_name: str
    description: str = ""
    capabilities: List[str] = []
    is_sandboxed: bool = True
    requires_fs_access: bool = False


class UnpublishBotRequest(BaseModel):
    """取消发布 Bot 请求"""
    bot_id: str


class FriendRequest(BaseModel):
    """好友请求"""
    to_instance: str
    to_bot_id: str = ""      # NEW: 目标 bot ID（bot 级别好友）
    from_bot_id: str = ""    # NEW: 发起方 bot ID
    message: str = ""


class FriendAcceptRequest(BaseModel):
    """好友确认请求"""
    accept: bool = True


# ============================================================================
# 路由设置函数
# ============================================================================

def setup_remote_routes(server: "WebChatServer"):
    """
    设置远程 Bot API 路由

    Args:
        server: WebChatServer 实例
    """
    app = server.app
    base_workplace = server.base_workplace
    bots = server.bots
    auth_token = server.auth_token

    # 创建路由器
    router = APIRouter(prefix="/api/remote", tags=["remote"])

    # 获取远程管理器
    def get_remote_manager():
        """获取远程 Bot 管理器"""
        if not server._remote_bot_mgr:
            raise HTTPException(status_code=503, detail="Remote bot functionality not available")
        return server._remote_bot_mgr

    @router.get("/bots")
    async def get_remote_bots():
        """
        获取所有 Bot（本地 + 远程），实时从注册中心获取远程 Bot

        Returns:
            Bot 列表
        """
        remote_mgr = get_remote_manager()
        all_bots = await remote_mgr.get_all_bots_realtime(bots)
        return {"success": True, "bots": list(all_bots.values())}

    @router.post("/publish")
    async def publish_bot(request: PublishBotRequest):
        """
        发布本地 Bot 到远程

        Args:
            request: 发布请求

        Returns:
            发布结果
        """
        remote_mgr = get_remote_manager()

        # 检查 Bot 是否存在
        if request.bot_id not in bots:
            raise HTTPException(status_code=404, detail=f"Bot '{request.bot_id}' not found")

        try:
            published_bot = remote_mgr.bot_publisher.publish_bot(
                bot_id=request.bot_id,
                display_name=request.display_name,
                description=request.description,
                is_sandboxed=request.is_sandboxed,
                requires_fs_access=request.requires_fs_access
            )
            return {"success": True, "bot": published_bot.to_dict()}

        except ValueError as e:
            raise HTTPException(status_code=400, detail=str(e))
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to publish bot: {str(e)}")

    @router.delete("/unpublish/{bot_id}")
    async def unpublish_bot(bot_id: str):
        """
        取消发布 Bot

        Args:
            bot_id: Bot ID

        Returns:
            取消发布结果
        """
        remote_mgr = get_remote_manager()
        success = remote_mgr.bot_publisher.unpublish_bot(bot_id)

        if success:
            return {"success": True}
        else:
            raise HTTPException(status_code=404, detail=f"Bot '{bot_id}' not published")

    @router.get("/published")
    async def get_published_bots():
        """
        获取已发布的 Bot 列表

        Returns:
            已发布的 Bot 列表
        """
        remote_mgr = get_remote_manager()
        published_bots = remote_mgr.get_published_bots()

        return {
            "success": True,
            "published_bots": published_bots
        }

    @router.post("/bots/{bot_id}/toggle")
    async def toggle_bot(bot_id: str, enabled: bool):
        """
        切换 Bot 的启用状态

        Args:
            bot_id: Bot ID
            enabled: 是否启用

        Returns:
            操作结果
        """
        remote_mgr = get_remote_manager()
        success = remote_mgr.bot_publisher.toggle_bot(bot_id, enabled)

        if success:
            return {"success": True}
        else:
            raise HTTPException(status_code=404, detail=f"Bot '{bot_id}' not found")

    @router.get("/friends")
    async def get_friends():
        """
        获取好友实例列表

        Returns:
            好友列表
        """
        print("[RemoteRoutes] /friends called")
        remote_mgr = get_remote_manager()
        print(f"[RemoteRoutes] remote_mgr={remote_mgr}, friend_mgr={remote_mgr.friend_manager is not None}, registry={remote_mgr.registry_client is not None}")
        friends = await remote_mgr.get_friends()
        print(f"[RemoteRoutes] get_friends returned: {friends}")

        return {"success": True, "friends": friends}

    @router.post("/add-bot")
    async def add_remote_bot(request: dict):
        """
        添加远程Bot到本地实例

        Args:
            request: 包含 instance_id, bot_id, full_bot_id

        Returns:
            添加结果
        """
        try:
            instance_id = request.get("instance_id")
            bot_id = request.get("bot_id")
            full_bot_id = request.get("full_bot_id")

            if not instance_id or not bot_id:
                raise HTTPException(status_code=400, detail="Missing required fields: instance_id, bot_id")

            remote_mgr = get_remote_manager()

            # 检查好友关系：必须先成为好友才能添加远程Bot（Bot 级别）
            if not remote_mgr.friend_manager.is_friend(instance_id, bot_id):
                raise HTTPException(
                    status_code=403,
                    detail="Not friends with this bot. Please send a friend request first."
                )

            # 添加远程bot到本地实例
            # 这里只是将bot添加到可用列表中，实际使用时通过远程调用
            success = await remote_mgr.add_remote_bot(instance_id, bot_id)

            if success:
                return {
                    "success": True,
                    "message": f"已添加远程Bot: {full_bot_id}",
                    "bot_id": full_bot_id
                }
            else:
                raise HTTPException(status_code=500, detail="Failed to add remote bot")

        except HTTPException:
            raise
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Error adding remote bot: {str(e)}")

    @router.post("/friend-request")
    async def send_friend_request(request: FriendRequest):
        """
        发送好友请求

        Args:
            request: 好友请求

        Returns:
            发送结果
        """
        remote_mgr = get_remote_manager()

        try:
            friend_req = await remote_mgr.friend_manager.send_friend_request(
                to_instance=request.to_instance,
                message=request.message,
                to_bot_id=request.to_bot_id,
                from_bot_id=request.from_bot_id
            )
            return {"success": True, "request_id": friend_req.request_id}

        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to send friend request: {str(e)}")

    @router.post("/friend-accept/{request_id}")
    async def accept_friend_request(request_id: str, body: FriendAcceptRequest):
        """
        接受或拒绝好友请求

        Args:
            request_id: 请求 ID
            accept: 是否接受

        Returns:
            操作结果
        """
        remote_mgr = get_remote_manager()

        try:
            print(f"[RemoteRoutes] 接受好友请求: request_id={request_id}, accept={body.accept}")

            if body.accept:
                success = await remote_mgr.friend_manager.accept_friend_request(request_id)
                print(f"[RemoteRoutes] 接受好友请求结果: success={success}")

                if success:
                    # 触发一次实例发现，确保新好友的实例信息被加载到 discovered_instances
                    try:
                        await remote_mgr._discover_bots()
                        print(f"[RemoteRoutes] 已触发实例发现，刷新好友实例信息")
                    except Exception as e:
                        print(f"[RemoteRoutes] 实例发现失败（非关键）: {e}")
                    return {"success": True}
                else:
                    return {"success": False, "error": "Failed to accept friend request"}
            else:
                await remote_mgr.friend_manager.accept_friend_request(request_id, accept=False)
                return {"success": True}

        except ValueError as e:
            print(f"[RemoteRoutes] ValueError: {e}")
            raise HTTPException(status_code=404, detail=str(e))
        except Exception as e:
            print(f"[RemoteRoutes] Exception: {e}")
            import traceback
            traceback.print_exc()
            raise HTTPException(status_code=500, detail=f"Failed to process friend request: {str(e)}")

    @router.get("/friend-requests")
    async def get_friend_requests():
        """
        获取待处理的好友请求

        Returns:
            好友请求列表
        """
        remote_mgr = get_remote_manager()
        requests = await remote_mgr.friend_manager.get_pending_requests()

        return {
            "success": True,
            "requests": [req.to_dict() for req in requests]
        }

    @router.delete("/friends/{instance_id}/{bot_id}")
    async def remove_friend(instance_id: str, bot_id: str):
        """
        移除好友（Bot 级别）

        Args:
            instance_id: 好友实例 ID
            bot_id: 好友 Bot ID（"__all__" 表示移除整个实例关系）

        Returns:
            操作结果
        """
        remote_mgr = get_remote_manager()

        try:
            # 将 "__all__" 转换为空字符串（实例级别移除）
            actual_bot_id = "" if bot_id == "__all__" else bot_id
            success = await remote_mgr.remove_friend(instance_id, actual_bot_id)
            if success:
                return {"success": True, "message": f"Friend {instance_id}:{bot_id} removed"}
            else:
                raise HTTPException(status_code=500, detail="Failed to remove friend")
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Failed to remove friend: {str(e)}")

    @router.get("/instances")
    async def get_online_instances():
        """
        获取在线实例列表

        Returns:
            在线实例列表
        """
        remote_mgr = get_remote_manager()
        instances = remote_mgr.discovered_instances

        return {
            "success": True,
            "instances": [inst.to_dict() for inst in instances.values()]
        }

    @router.post("/discover")
    async def discover_instances():
        """
        立即触发实例发现

        Returns:
            发现结果
        """
        remote_mgr = get_remote_manager()
        try:
            await remote_mgr._discover_bots()
            instances = remote_mgr.discovered_instances

            return {
                "success": True,
                "message": f"Discovered {len(instances)} instances",
                "instances": [inst.to_dict() for inst in instances.values()]
            }
        except Exception as e:
            raise HTTPException(status_code=500, detail=f"Discovery failed: {str(e)}")

    # TODO: Federation功能未实现，暂时禁用
    # @router.post("/federation/groups")
    # async def create_federated_group(request: dict):
    #     """创建联合群组"""
    #     raise HTTPException(status_code=501, detail="Federation feature not implemented")

    # @router.get("/federation/groups")
    # async def get_federated_groups():
    #     """获取联合群组列表"""
    #     raise HTTPException(status_code=501, detail="Federation feature not implemented")

    # TODO: Metrics功能未实现，暂时禁用
    # @router.get("/metrics")
    # async def get_metrics():
    #     """获取远程调用指标"""
    #     raise HTTPException(status_code=501, detail="Metrics feature not implemented")

    @router.get("/ui")
    async def remote_bots_ui():
        """提供远程 Bot 管理 UI"""
        current_dir = os.path.dirname(os.path.abspath(__file__))
        static_dir = os.path.join(current_dir, "..", "static")
        html_path = os.path.join(static_dir, "remote-bots.html")

        if os.path.exists(html_path):
            return FileResponse(html_path)
        else:
            raise HTTPException(status_code=404, detail="Remote bots UI not found")

    # 注册路由到应用
    app.include_router(router)
