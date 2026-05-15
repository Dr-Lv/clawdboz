#!/usr/bin/env python3
"""
Moments API Routes - 朋友圈 API 路由

提供朋友圈动态、点赞、评论等功能。
"""

import json
import os
import time
import uuid
from typing import TYPE_CHECKING

from fastapi import Request, Query
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from ..server_core import WebChatServer


def setup_moments_routes(server: "WebChatServer"):
    """
    设置朋友圈 API 路由

    Args:
        server: WebChatServer 实例
    """
    app = server.app
    auth_token = server.auth_token
    base_workplace = server.base_workplace
    bots = server.bots

    # Import data manager
    from ..data.moments import MomentsDataManager
    moments_mgr = MomentsDataManager(base_workplace)

    @app.get("/api/moments")
    async def get_moments(token: str = Query(...), limit: int = Query(20), offset: int = Query(0)):
        """获取朋友圈列表 - 实时更新头像信息"""
        if token != auth_token:
            return JSONResponse(
                status_code=403,
                content={"success": False, "error": "Invalid token"}
            )

        try:
            moments = moments_mgr.load_moments()
            # 按时间倒序，分页
            moments.sort(key=lambda x: x.get('created_at', 0), reverse=True)
            total = len(moments)
            paginated = moments[offset:offset + limit]

            # 实时更新每个 moment 的 sender 信息（昵称、头像同步）
            for moment in paginated:
                sender = moment.get('sender', {})
                sender_id = sender.get('id', 'user')
                sender_type = sender.get('type', 'user')

                # 获取最新的 sender 信息
                latest_sender = moments_mgr.get_sender_info(sender_id, sender_type, bots)

                # 更新昵称和头像信息
                sender['name'] = latest_sender.get('name', sender.get('name', '未知'))
                sender['avatar_color'] = latest_sender.get('avatar_color', 'from-blue-400 to-blue-600')
                sender['avatar_icon'] = latest_sender.get('avatar_icon', 'fa-user')

                # 更新点赞列表中的昵称
                for like in moment.get('likes', []):
                    if isinstance(like, dict):
                        like_sender_id = like.get('sender_id', 'user')
                        like_sender_type = like.get('sender_type', 'user')
                        latest_like_sender = moments_mgr.get_sender_info(like_sender_id, like_sender_type, bots)
                        like['sender_name'] = latest_like_sender.get('name', like.get('sender_name', '未知用户'))

                # 更新评论中的发送者昵称和头像
                for comment in moment.get('comments', []):
                    comment_sender = comment.get('sender', {})
                    comment_sender_id = comment_sender.get('id', 'user')
                    comment_sender_type = comment_sender.get('type', 'user')
                    latest_comment_sender = moments_mgr.get_sender_info(comment_sender_id, comment_sender_type, bots)
                    comment_sender['name'] = latest_comment_sender.get('name', comment_sender.get('name', '未知'))
                    comment_sender['avatar_color'] = latest_comment_sender.get('avatar_color', 'from-blue-400 to-blue-600')
                    comment_sender['avatar_icon'] = latest_comment_sender.get('avatar_icon', 'fa-user')

            return {
                "success": True,
                "moments": paginated,
                "total": total,
                "limit": limit,
                "offset": offset
            }
        except Exception as e:
            print(f"[Get Moments] 错误: {e}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )

    @app.post("/api/moments")
    async def create_moment(request: Request):
        """发布朋友圈"""
        try:
            data = await request.json()
            token = data.get('token')

            if token != auth_token:
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "error": "Invalid token"}
                )

            content = data.get('content', '').strip()
            images = data.get('images', [])
            sender_id = data.get('sender_id', 'user')
            sender_type = data.get('sender_type', 'user')  # 'user' or 'bot'

            if not content and not images:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "内容或图片至少填一个"}
                )

            # 获取发送者信息
            sender_info = moments_mgr.get_sender_info(sender_id, sender_type, bots)

            moment = {
                'id': str(uuid.uuid4()),
                'content': content,
                'images': images,
                'sender': sender_info,
                'likes': [],
                'comments': [],
                'created_at': time.time()
            }

            moments = moments_mgr.load_moments()
            moments.append(moment)
            moments_mgr.save_moments(moments)

            return {
                "success": True,
                "message": "发布成功",
                "moment": moment
            }
        except Exception as e:
            print(f"[Create Moment] 错误: {e}")
            import traceback
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )

    @app.post("/api/moments/{moment_id}/like")
    async def like_moment(moment_id: str, request: Request):
        """点赞/取消点赞"""
        try:
            data = await request.json()
            token = data.get('token')

            if token != auth_token:
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "error": "Invalid token"}
                )

            sender_id = data.get('sender_id', 'user')
            sender_type = data.get('sender_type', 'user')

            moments = moments_mgr.load_moments()
            moment = None
            for m in moments:
                if m['id'] == moment_id:
                    moment = m
                    break

            if not moment:
                return JSONResponse(
                    status_code=404,
                    content={"success": False, "error": "动态不存在"}
                )

            likes = moment.get('likes', [])

            # 获取发送者信息
            sender_info = moments_mgr.get_sender_info(sender_id, sender_type, bots)

            # 查找是否已点赞（通过 sender_id）
            existing_index = None
            for i, like in enumerate(likes):
                if isinstance(like, dict) and like.get('sender_id') == sender_id:
                    existing_index = i
                    break
                elif isinstance(like, str) and like == sender_id:
                    # 兼容旧数据格式
                    existing_index = i
                    break

            # 切换点赞状态
            if existing_index is not None:
                likes.pop(existing_index)
                liked = False
            else:
                likes.append({
                    'sender_id': sender_id,
                    'sender_name': sender_info['name'],
                    'sender_type': sender_type
                })
                liked = True

            moment['likes'] = likes
            moments_mgr.save_moments(moments)

            return {
                "success": True,
                "liked": liked,
                "likes_count": len(likes)
            }
        except Exception as e:
            print(f"[Like Moment] 错误: {e}")
            import traceback
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )

    @app.post("/api/moments/{moment_id}/comment")
    async def comment_moment(moment_id: str, request: Request):
        """评论朋友圈"""
        try:
            data = await request.json()
            token = data.get('token')

            if token != auth_token:
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "error": "Invalid token"}
                )

            content = data.get('content', '').strip()
            if not content:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "评论内容不能为空"}
                )

            sender_id = data.get('sender_id', 'user')
            sender_type = data.get('sender_type', 'user')

            moments = moments_mgr.load_moments()
            moment = None
            for m in moments:
                if m['id'] == moment_id:
                    moment = m
                    break

            if not moment:
                return JSONResponse(
                    status_code=404,
                    content={"success": False, "error": "动态不存在"}
                )

            sender_info = moments_mgr.get_sender_info(sender_id, sender_type, bots)

            comment = {
                'id': str(uuid.uuid4()),
                'content': content,
                'sender': sender_info,
                'created_at': time.time()
            }

            moment['comments'].append(comment)
            moments_mgr.save_moments(moments)

            return {
                "success": True,
                "message": "评论成功",
                "comment": comment
            }
        except Exception as e:
            print(f"[Comment Moment] 错误: {e}")
            import traceback
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )

    @app.get("/api/user/profile")
    async def get_user_profile(token: str = Query(...)):
        """获取用户资料"""
        if token != auth_token:
            return JSONResponse(
                status_code=403,
                content={"success": False, "error": "Invalid token"}
            )

        try:
            user_file = os.path.join(base_workplace, '.user.md')
            result = {
                "name": "用户",
                "bio": "",
                "avatar_color": "from-indigo-500 to-purple-600",
                "avatar_icon": "fa-user"
            }

            if os.path.exists(user_file):
                with open(user_file, 'r', encoding='utf-8') as f:
                    for line in f:
                        if line.startswith('Name:'):
                            result['name'] = line.replace('Name:', '').strip()
                        elif line.startswith('Bio:'):
                            result['bio'] = line.replace('Bio:', '').strip()
                        elif line.startswith('Avatar Color:'):
                            result['avatar_color'] = line.replace('Avatar Color:', '').strip()
                        elif line.startswith('Avatar Icon:'):
                            result['avatar_icon'] = line.replace('Avatar Icon:', '').strip()
                        elif line.startswith('Avatar Image:'):
                            result['avatar_image'] = line.replace('Avatar Image:', '').strip()

            return result
        except Exception as e:
            print(f"[Get User Profile] 错误: {e}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )

    @app.post("/api/user/profile/update")
    async def save_user_profile(request: Request):
        """保存用户资料"""
        try:
            data = await request.json()
            token = data.get('token')

            if token != auth_token:
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "error": "Invalid token"}
                )

            name = data.get('name', '').strip()
            bio = data.get('bio', '').strip()
            avatar_color = data.get('avatar_color', '').strip()
            avatar_icon = data.get('avatar_icon', '').strip()
            avatar_image = data.get('avatar_image', '').strip()

            user_file = os.path.join(base_workplace, '.user.md')

            with open(user_file, 'w', encoding='utf-8') as f:
                f.write(f"# 用户资料\n\n")
                f.write(f"Name: {name}\n")
                f.write(f"Bio: {bio}\n")
                f.write(f"Avatar Color: {avatar_color or 'from-indigo-500 to-purple-600'}\n")
                f.write(f"Avatar Icon: {avatar_icon or 'fa-user'}\n")
                if avatar_image:
                    f.write(f"Avatar Image: {avatar_image}\n")

            return {"success": True}
        except Exception as e:
            print(f"[Save User Profile] 错误: {e}")
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )
