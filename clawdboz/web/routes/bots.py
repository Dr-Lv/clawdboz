#!/usr/bin/env python3
"""
Bots API Routes - Bot 管理 API 路由

提供 Bot 列表、创建、更新、删除和详情获取等功能。
"""

import json
import os
import shutil
import time
from pathlib import Path
from typing import TYPE_CHECKING

from fastapi import Request, Query
from fastapi.responses import JSONResponse

if TYPE_CHECKING:
    from ..server_core import WebChatServer


def setup_bots_routes(server: "WebChatServer"):
    """
    设置 Bot 管理 API 路由

    Args:
        server: WebChatServer 实例
    """
    app = server.app
    auth_token = server.auth_token
    base_workplace = server.base_workplace
    bots = server.bots

    def _get_bot_work_dir(bid: str) -> str:
        """获取 bot 工作目录，优先使用新格式，兼容旧格式"""
        new_path = os.path.join(base_workplace, f"workplace_{bid}")
        old_path = os.path.join(base_workplace, bid)
        if os.path.exists(new_path):
            return new_path
        elif os.path.exists(old_path):
            return old_path
        return new_path  # 默认返回新格式

    @app.get("/api/bots")
    async def list_bots():
        """获取 Bot 列表 - 只包含本地bot"""
        bots_list = []
        bots_by_id = {}

        # 1. 首先添加已注册的本地 bots
        for bid, bot in bots.items():
            bots_by_id[bid] = {
                "id": bid,
                "name": bid,
                "work_dir": _get_bot_work_dir(bid),
                "avatar_color": "",
                "avatar_icon": "",
                "registered": True,
                "type": "local"
            }

        # 2. 扫描 workplace 目录发现未注册的 bots（只使用 workplace_{bot_id} 格式）
        if os.path.exists(base_workplace):
            for item in os.listdir(base_workplace):
                item_path = os.path.join(base_workplace, item)
                if not os.path.isdir(item_path) or item.startswith('.') or item.startswith('groupspace') or item == 'workplace_system':
                    continue
                # 只处理 workplace_{bot_id} 格式
                if not item.startswith('workplace_'):
                    continue
                bid = item[len('workplace_'):]
                # 排除远程bot（包含冒号的bot_id格式：instance_id:bot_id）
                if ':' in bid:
                    continue
                # 只要 workplace 目录存在就加入列表（不再要求必须有 .bot.md）
                if bid not in bots_by_id:
                    bots_by_id[bid] = {
                        "id": bid,
                        "name": bid,
                        "work_dir": item_path,
                        "avatar_color": "",
                        "avatar_icon": "",
                        "registered": False,
                        "type": "local"
                    }

        # 3. 读取所有本地 bot 的元数据
        for bid, bot_info in bots_by_id.items():
            bot_md_path = os.path.join(bot_info['work_dir'], '.bot.md')
            if os.path.exists(bot_md_path):
                try:
                    with open(bot_md_path, 'r', encoding='utf-8') as f:
                        for line in f:
                            if line.startswith('Name:'):
                                bot_info['name'] = line.replace('Name:', '').strip() or bid
                            elif line.startswith('Bio:'):
                                bot_info['bio'] = line.replace('Bio:', '').strip()
                            elif line.startswith('Avatar Color:'):
                                bot_info['avatar_color'] = line.replace('Avatar Color:', '').strip()
                            elif line.startswith('Avatar Icon:'):
                                bot_info['avatar_icon'] = line.replace('Avatar Icon:', '').strip()
                            elif line.startswith('Avatar Image:'):
                                bot_info['avatar_image'] = line.replace('Avatar Image:', '').strip()
                            elif line.startswith('Feishu App ID:'):
                                bot_info['feishu_app_id'] = line.replace('Feishu App ID:', '').strip()
                            elif line.startswith('Feishu App Secret:'):
                                bot_info['feishu_app_secret'] = line.replace('Feishu App Secret:', '').strip()
                            elif line.startswith('ACP Client ID:'):
                                bot_info['acp_client_id'] = line.replace('ACP Client ID:', '').strip()
                except Exception as e:
                    print(f"[List Bots] 读取 {bid} .bot.md 失败: {e}")

            # 读取 Skills
            skills_dir = os.path.join(bot_info['work_dir'], '.agents', 'skills')
            bot_info['skills'] = []
            if os.path.exists(skills_dir):
                try:
                    for item in os.listdir(skills_dir):
                        skill_path = os.path.join(skills_dir, item)
                        if os.path.isdir(skill_path):
                            bot_info['skills'].append(item)
                            print(f"[List Bots] Bot {bid} skill: {item}")
                except Exception as e:
                    print(f"[List Bots] 读取 {bid} skills 失败: {e}")

            bots_list.append(bot_info)

        # 4. 添加已添加的远程 bots（从 RemoteBotManager 获取）
        try:
            remote_mgr = getattr(server, '_remote_bot_mgr', None)
            if remote_mgr:
                remote_bots = remote_mgr.get_added_remote_bots()
                for rb in remote_bots:
                    bots_list.append({
                        "id": rb["full_bot_id"],
                        "name": rb.get("display_name", rb["bot_id"]),
                        "bio": rb.get("description", ""),
                        "avatar_color": rb.get("avatar_color", ""),
                        "avatar_icon": rb.get("avatar_icon", ""),
                        "avatar_image": rb.get("avatar_image", ""),
                        "registered": True,
                        "type": "remote",
                        "instance_id": rb["instance_id"],
                        "instance_name": rb.get("instance_name", rb["instance_id"])
                    })
        except Exception as e:
            print(f"[List Bots] 加载远程 bots 失败: {e}")

        return {"bots": bots_list}

    @app.post("/api/bots")
    async def create_bot(request: Request):
        """创建新 Bot"""
        try:
            data = await request.json()
            token = data.get('token')

            if token != auth_token:
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "error": "Invalid token"}
                )

            bot_id = data.get('bot_id', '').strip()
            name = data.get('name', '').strip()
            bio = data.get('bio', '').strip()
            feishu_app_id = data.get('feishu_app_id', '').strip()
            feishu_app_secret = data.get('feishu_app_secret', '').strip()
            acp_client_id = data.get('acp_client_id', '').strip()

            if not bot_id:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": "Bot ID 不能为空"}
                )

            # 检查是否已存在
            if bot_id in bots:
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": f"Bot '{bot_id}' 已存在"}
                )

            # 使用统一的 workplace_{bot_id} 格式（兼容旧的 {bot_id} 格式）
            bot_work_dir = os.path.join(base_workplace, f"workplace_{bot_id}")
            if os.path.exists(bot_work_dir):
                return JSONResponse(
                    status_code=400,
                    content={"success": False, "error": f"Bot 目录 '{bot_id}' 已存在"}
                )

            # 创建 Bot 工作目录
            os.makedirs(bot_work_dir, exist_ok=True)

            # 复制 config.json（如果不存在）
            root_config = os.path.join(os.path.dirname(base_workplace), 'config.json')
            bot_config = os.path.join(bot_work_dir, 'config.json')
            if os.path.exists(root_config) and not os.path.exists(bot_config):
                try:
                    # 读取并修改 config.json
                    with open(root_config, 'r', encoding='utf-8') as f:
                        config = json.load(f)
                    # 更新 project_root 为 bot 的工作目录
                    config['project_root'] = bot_work_dir
                    # 确保 feishu 配置有占位符值（Web Chat 模式下不需要真实值，但验证需要非空）
                    if 'feishu' not in config:
                        config['feishu'] = {}
                    if not config['feishu'].get('app_id'):
                        config['feishu']['app_id'] = 'webchat-mode-no-feishu'
                    if not config['feishu'].get('app_secret'):
                        config['feishu']['app_secret'] = 'webchat-mode-no-feishu'
                    # 写入 bot 目录
                    with open(bot_config, 'w', encoding='utf-8') as f:
                        json.dump(config, f, indent=2, ensure_ascii=False)
                    print(f"[Create Bot] 复制 config.json 到: {bot_config}")
                except Exception as e:
                    print(f"[Create Bot] 复制 config.json 失败: {e}")

            # 创建基础目录结构
            for subdir in ['logs', 'user_files', 'user_images']:
                os.makedirs(os.path.join(bot_work_dir, subdir), exist_ok=True)

            # 创建 .bot.md 文件
            bot_md_path = os.path.join(bot_work_dir, '.bot.md')
            with open(bot_md_path, 'w', encoding='utf-8') as f:
                f.write(f"# {name or bot_id}\n\n")
                f.write(f"ID: {bot_id}\n")
                f.write(f"Name: {name or bot_id}\n")
                if bio:
                    f.write(f"Bio: {bio}\n")
                f.write("Avatar Color: from-purple-400 to-purple-600\n")
                f.write("Avatar Icon: fa-robot\n")
                f.write(f"Created: {time.strftime('%Y-%m-%d %H:%M:%S')}\n")
                # 保存飞书配置
                if feishu_app_id:
                    f.write(f"Feishu App ID: {feishu_app_id}\n")
                if feishu_app_secret:
                    f.write(f"Feishu App Secret: {feishu_app_secret}\n")
                # 保存 ACP 客户端配置
                if acp_client_id:
                    f.write(f"ACP Client ID: {acp_client_id}\n")

            # 配置内置 Skills
            # 统一从包目录复制，确保所有入口使用相同的 skill 版本
            package_dir = Path(__file__).parent.parent.parent.resolve()
            builtin_skills_dir = package_dir / '.agents' / 'skills'

            # 获取用户选择的 skills，如果没有提供则默认全部
            selected_skills = data.get('skills', ['local-memory', 'scheduler', 'find-skills', 'moments', 'webchat-sender'])

            skills_dir = os.path.join(bot_work_dir, '.agents', 'skills')
            os.makedirs(skills_dir, exist_ok=True)

            for skill_name in selected_skills:
                src_skill = builtin_skills_dir / skill_name
                dst_skill = os.path.join(skills_dir, skill_name)
                if src_skill.exists() and not os.path.exists(dst_skill):
                    try:
                        shutil.copytree(src_skill, dst_skill)
                        print(f"[Create Bot] 复制 skill: {skill_name}")
                    except Exception as e:
                        print(f"[Create Bot] 复制 skill {skill_name} 失败: {e}")

            # 创建简单的 Bot 对象
            from clawdboz.core.simple_bot import Bot as SimpleBot
            bot = SimpleBot(
                bot_id=bot_id,
                work_dir=bot_work_dir,
                system_prompt=bio or f"你是{name or bot_id}，一个友好的AI助手。"
            )

            # 设置 MCP 模式为 webchat，以便定时任务知道使用 webchat-sender
            os.environ['CLAWDBOZ_MCP_MODE'] = 'webchat'
            # 设置 bot_id 以便心跳能正确找到任务文件
            bot._bot_id = bot_id
            if hasattr(bot, '_bot') and bot._bot:
                bot._bot._bot_id = bot_id
                # 重新启动心跳以确保使用正确的 bot_id
                if hasattr(bot._bot, '_stop_heart_beat'):
                    bot._bot._stop_heart_beat()
                if hasattr(bot._bot, '_start_heart_beat'):
                    bot._bot._start_heart_beat()
                    print(f"[Create Bot] 已启动心跳线程，Bot ID: {bot_id}")

            # 设置 bot 名称和 system_prompt（供后端mention解析和ACP客户端使用）
            bot.name = name or bot_id
            bot._system_prompt = bio or f"你是{name or bot_id}，一个友好的AI助手。"

            # 添加到 bots 字典
            bots[bot_id] = bot

            print(f"[Create Bot] 创建成功: {bot_id} @ {bot_work_dir}")

            return {
                "success": True,
                "message": "Bot 创建成功",
                "bot": {
                    "id": bot_id,
                    "name": name or bot_id,
                    "work_dir": bot_work_dir
                }
            }
        except Exception as e:
            print(f"[Create Bot] 错误: {e}")
            import traceback
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )

    @app.put("/api/bots/{bot_id}")
    async def update_bot(bot_id: str, request: Request):
        """更新 Bot 信息"""
        try:
            data = await request.json()
            token = data.get('token')

            if token != auth_token:
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "error": "Invalid token"}
                )

            # 检查 bot 是否存在（只使用 workplace_{bot_id} 格式）
            bot_work_dir = os.path.join(base_workplace, f"workplace_{bot_id}")
            if bot_id not in bots and not os.path.exists(bot_work_dir):
                return JSONResponse(
                    status_code=404,
                    content={"success": False, "error": f"Bot '{bot_id}' 不存在"}
                )

            name = data.get('name', '').strip()
            bio = data.get('bio', '').strip()
            avatar_color = data.get('avatar_color', '').strip()
            avatar_icon = data.get('avatar_icon', '').strip()
            avatar_image = data.get('avatar_image', '').strip()
            feishu_app_id = data.get('feishu_app_id', '').strip()
            feishu_app_secret = data.get('feishu_app_secret', '').strip()
            acp_client_id = data.get('acp_client_id', '').strip()
            skills = data.get('skills', [])

            # 更新 .bot.md 文件
            bot_md_path = os.path.join(bot_work_dir, '.bot.md')

            # 读取现有内容
            existing_content = {}
            if os.path.exists(bot_md_path):
                with open(bot_md_path, 'r', encoding='utf-8') as f:
                    for line in f:
                        if ':' in line and not line.startswith('#'):
                            key, val = line.split(':', 1)
                            existing_content[key.strip()] = val.strip()

            # 更新内容
            if name:
                existing_content['Name'] = name
            if bio:
                existing_content['Bio'] = bio
            if avatar_color:
                existing_content['Avatar Color'] = avatar_color
            if avatar_icon:
                existing_content['Avatar Icon'] = avatar_icon
            if avatar_image:
                existing_content['Avatar Image'] = avatar_image
            if feishu_app_id:
                existing_content['Feishu App ID'] = feishu_app_id
            if feishu_app_secret:
                existing_content['Feishu App Secret'] = feishu_app_secret
            if acp_client_id:
                existing_content['ACP Client ID'] = acp_client_id
            elif 'acp_client_id' in data and not acp_client_id:
                # 如果传了空值，删除 ACP Client ID
                existing_content.pop('ACP Client ID', None)

            # 处理 Skills
            if skills is not None:
                existing_content['Skills'] = ', '.join(skills)

                # 同步 skills 目录
                package_dir = Path(__file__).parent.parent.parent.resolve()
                builtin_skills_dir = package_dir / '.agents' / 'skills'
                skills_dir = os.path.join(bot_work_dir, '.agents', 'skills')
                os.makedirs(skills_dir, exist_ok=True)

                # 获取当前已有的 skills
                existing_skills = set()
                if os.path.exists(skills_dir):
                    for item in os.listdir(skills_dir):
                        if os.path.isdir(os.path.join(skills_dir, item)):
                            existing_skills.add(item)

                # 复制选中的 skills
                for skill_id in skills:
                    src_skill = builtin_skills_dir / skill_id
                    dst_skill = os.path.join(skills_dir, skill_id)
                    if src_skill.exists() and not os.path.exists(dst_skill):
                        try:
                            shutil.copytree(src_skill, dst_skill)
                            print(f"[Update Bot] 复制 skill: {skill_id}")
                        except Exception as e:
                            print(f"[Update Bot] 复制 skill {skill_id} 失败: {e}")

                # 删除未选中的 skills（但保留用户自定义的）
                for existing_skill in list(existing_skills):
                    if existing_skill not in skills and existing_skill in ['local-memory', 'scheduler', 'find-skills', 'moments', 'webchat-sender']:
                        skill_path = os.path.join(skills_dir, existing_skill)
                        try:
                            shutil.rmtree(skill_path)
                            print(f"[Update Bot] 删除 skill: {existing_skill}")
                        except Exception as e:
                            print(f"[Update Bot] 删除 skill {existing_skill} 失败: {e}")

            # 写回文件
            with open(bot_md_path, 'w', encoding='utf-8') as f:
                f.write(f"# {name or bot_id}\n\n")
                f.write(f"ID: {bot_id}\n")
                for key, val in existing_content.items():
                    if key not in ['ID']:  # ID 已经写过了
                        f.write(f"{key}: {val}\n")

            # 如果 bot 在内存中，更新其属性
            if bot_id in bots:
                bot = bots[bot_id]
                bot.name = name or bot_id
                if bio:
                    bot._system_prompt = bio
                    if hasattr(bot, 'system_prompt'):
                        bot.system_prompt = bio
                # 更新 ACP Client ID
                if acp_client_id:
                    bot._acp_client_id = acp_client_id
                    if hasattr(bot, '_bot') and bot._bot:
                        bot._bot._acp_client_id = acp_client_id
                elif 'acp_client_id' in data and not acp_client_id:
                    # 如果传了空值，清除 ACP Client ID
                    bot._acp_client_id = None
                    if hasattr(bot, '_bot') and bot._bot:
                        bot._bot._acp_client_id = None

            print(f"[Update Bot] 更新成功: {bot_id}")

            return {
                "success": True,
                "message": "Bot 更新成功",
                "bot": {
                    "id": bot_id,
                    "name": name or bot_id,
                    "avatar_color": avatar_color or existing_content.get('Avatar Color', ''),
                    "avatar_icon": avatar_icon or existing_content.get('Avatar Icon', ''),
                    "avatar_image": avatar_image or existing_content.get('Avatar Image', ''),
                    "feishu_app_id": feishu_app_id or existing_content.get('Feishu App ID', ''),
                    "feishu_app_secret": feishu_app_secret or existing_content.get('Feishu App Secret', ''),
                    "acp_client_id": acp_client_id or existing_content.get('ACP Client ID', '')
                }
            }
        except Exception as e:
            print(f"[Update Bot] 错误: {e}")
            import traceback
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )

    @app.get("/api/bots/{bot_id}")
    async def get_bot_detail(bot_id: str, token: str = Query(...)):
        """获取 Bot 详细信息（包括 skills 和 memory）"""
        import sys
        print(f"[Get Bot Detail] API called for bot_id={bot_id}, token={token}", flush=True)
        sys.stderr.write(f"[Get Bot Detail] API called for bot_id={bot_id}\n")
        sys.stderr.flush()
        try:
            if token != auth_token:
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "error": "Invalid token"}
                )

            # 只使用 workplace_{bot_id} 格式
            bot_work_dir = os.path.join(base_workplace, f"workplace_{bot_id}")
            if not os.path.exists(bot_work_dir):
                return JSONResponse(
                    status_code=404,
                    content={"success": False, "error": f"Bot '{bot_id}' 不存在"}
                )

            result = {
                "id": bot_id,
                "skills": [],
                "memory": ""
            }

            # 读取 Skills - 返回技能ID列表
            skills_dir = os.path.join(bot_work_dir, '.agents', 'skills')
            os.makedirs(skills_dir, exist_ok=True)

            # 检查是否有任何 skill 目录
            has_skills = False
            if os.path.exists(skills_dir):
                try:
                    for item in os.listdir(skills_dir):
                        skill_path = os.path.join(skills_dir, item)
                        if os.path.isdir(skill_path):
                            # 直接使用目录名作为技能ID
                            result["skills"].append(item)
                            print(f"[Get Bot Detail] 找到 skill: {item}")
                            has_skills = True
                except Exception as e:
                    print(f"[Get Bot Detail] 读取 skills 失败: {e}")

            # 如果目录为空，自动复制所有内置skills（向后兼容）
            if not has_skills:
                print(f"[Get Bot Detail] Skills 目录为空，自动复制所有内置 skills")
                package_dir = Path(__file__).parent.parent.parent.resolve()
                builtin_skills_dir = package_dir / '.agents' / 'skills'
                builtin_skills = ['local-memory', 'scheduler', 'find-skills', 'moments', 'webchat-sender']

                for skill_name in builtin_skills:
                    src_skill = builtin_skills_dir / skill_name
                    dst_skill = os.path.join(skills_dir, skill_name)
                    if src_skill.exists() and not os.path.exists(dst_skill):
                        try:
                            shutil.copytree(src_skill, dst_skill)
                            print(f"[Get Bot Detail] 自动复制 skill: {skill_name}")
                            result["skills"].append(skill_name)
                        except Exception as e:
                            print(f"[Get Bot Detail] 自动复制 skill {skill_name} 失败: {e}")

            # 读取 Memory (local-memory SQLite)
            memory_db = os.path.join(bot_work_dir, '.agents', 'skills', 'local-memory', 'memory', 'memories.db')
            if os.path.exists(memory_db):
                try:
                    import sqlite3
                    conn = sqlite3.connect(memory_db)
                    cursor = conn.cursor()
                    cursor.execute("SELECT content FROM memories ORDER BY created_at DESC LIMIT 5")
                    rows = cursor.fetchall()
                    if rows:
                        result["memory"] = "\n".join([row[0] for row in rows])
                    conn.close()
                except Exception as e:
                    print(f"[Get Bot Detail] 读取 SQLite memory 失败: {e}")

            # 如果没有找到，尝试从 bot 工作目录的 memory/ 文件夹读取
            if not result["memory"]:
                memory_db = os.path.join(bot_work_dir, 'memory', 'memories.db')
                if os.path.exists(memory_db):
                    try:
                        import sqlite3
                        conn = sqlite3.connect(memory_db)
                        cursor = conn.cursor()
                        cursor.execute("SELECT content FROM memories ORDER BY created_at DESC LIMIT 5")
                        rows = cursor.fetchall()
                        if rows:
                            result["memory"] = "\n".join([row[0] for row in rows])
                        conn.close()
                    except Exception as e:
                        print(f"[Get Bot Detail] 读取 bot memory 失败: {e}")

            # 如果没有找到，尝试从 workplace 级别的 local-memory 读取
            if not result["memory"]:
                memory_db = os.path.join(base_workplace, '.agents', 'skills', 'local-memory', 'memory', 'memories.db')
                if os.path.exists(memory_db):
                    try:
                        import sqlite3
                        conn = sqlite3.connect(memory_db)
                        cursor = conn.cursor()
                        cursor.execute("SELECT content FROM memories ORDER BY created_at DESC LIMIT 5")
                        rows = cursor.fetchall()
                        if rows:
                            result["memory"] = "\n".join([row[0] for row in rows])
                        conn.close()
                    except Exception as e:
                        print(f"[Get Bot Detail] 读取 workplace memory 失败: {e}")

            # 也尝试读取 .memory.md 文件
            if not result["memory"]:
                memory_md = os.path.join(bot_work_dir, '.memory.md')
                if os.path.exists(memory_md):
                    try:
                        with open(memory_md, 'r', encoding='utf-8') as f:
                            result["memory"] = f.read()[:500]  # 限制长度
                    except Exception as e:
                        print(f"[Get Bot Detail] 读取 .memory.md 失败: {e}")

            return result
        except Exception as e:
            print(f"[Get Bot Detail] 错误: {e}")
            import traceback
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )

    @app.delete("/api/bots/{bot_id}")
    async def delete_bot(bot_id: str, token: str = Query(...)):
        """删除 Bot"""
        try:
            if token != auth_token:
                return JSONResponse(
                    status_code=403,
                    content={"success": False, "error": "Invalid token"}
                )

            # 只使用 workplace_{bot_id} 格式
            bot_work_dir = os.path.join(base_workplace, f"workplace_{bot_id}")
            if not os.path.exists(bot_work_dir):
                return JSONResponse(
                    status_code=404,
                    content={"success": False, "error": f"Bot '{bot_id}' 不存在"}
                )

            # 从 bots 字典中移除
            if bot_id in bots:
                del bots[bot_id]

            # 删除 Bot 工作目录
            try:
                shutil.rmtree(bot_work_dir)
                print(f"[Delete Bot] 删除成功: {bot_id}")
                return {"success": True, "message": "Bot 已删除"}
            except Exception as e:
                print(f"[Delete Bot] 删除目录失败: {e}")
                return JSONResponse(
                    status_code=500,
                    content={"success": False, "error": f"删除目录失败: {str(e)}"}
                )
        except Exception as e:
            print(f"[Delete Bot] 错误: {e}")
            import traceback
            traceback.print_exc()
            return JSONResponse(
                status_code=500,
                content={"success": False, "error": str(e)}
            )
