"""
Docker 沙箱 HTTP 服务器
运行在容器内，接收主机的 execute 请求并执行 Bot 调用
"""
import sys
# 必须在所有其他导入之前添加路径
sys.path.insert(0, '/host-site-packages')
# Removed: sys.path.insert(0, '/app') - causes import shadowing

import asyncio
import json
import os
import traceback
from aiohttp import web

# 存储注册的 bot 配置
_registered_bots = {}


def _convert_host_path_to_container(workspace_dir: str) -> str:
    """将宿主机的 workspace 路径转换为容器内路径"""
    # 常见映射模式：/tmp/clawdboz/WORKPLACE/... -> /workplace/...
    if workspace_dir.startswith('/tmp/clawdboz/WORKPLACE'):
        return '/workplace' + workspace_dir[len('/tmp/clawdboz/WORKPLACE'):]
    # 兜底：如果路径中包含 WORKPLACE，提取其后部分拼到 /workplace
    if 'WORKPLACE' in workspace_dir:
        idx = workspace_dir.find('WORKPLACE')
        relative = workspace_dir[idx + len('WORKPLACE'):]
        return '/workplace' + relative
    return workspace_dir


async def register_handler(request):
    """处理 /register 请求（注册 Bot 配置到沙箱）"""
    try:
        data = await request.json()
        bot_id = data.get("bot_id", "")
        config = data.get("config", {})
        acp_config = data.get("acp_config", {})

        _registered_bots[bot_id] = {
            "config": config,
            "acp_config": acp_config
        }
        print(f"[SandboxServer] Bot '{bot_id}' registered")
        return web.json_response({"success": True})
    except Exception as e:
        print(f"[SandboxServer] Register error: {e}")
        return web.json_response({"success": False, "error": str(e)})


async def execute_handler(request):
    """处理 /execute 请求"""
    try:
        data = await request.json()
        bot_id = data.get("bot_id", "")
        method = data.get("method", "chat")
        params = data.get("params", {})

        print(f"[SandboxServer] Execute request: bot_id={bot_id}, method={method}")

        workspace_dir = params.get("workspace_dir", "/workplace")
        # 修复：将宿主机的绝对路径转换为容器内路径
        workspace_dir = _convert_host_path_to_container(workspace_dir)
        print(f"[SandboxServer] Container workspace_dir: {workspace_dir}")

        message = params.get("message", "")
        chat_id = params.get("chat_id", "sandbox")

        # 设置工作目录
        os.makedirs(workspace_dir, exist_ok=True)
        original_dir = os.getcwd()
        os.chdir(workspace_dir)
        os.environ['CLAWDBOZ_SESSION_WORK_DIR'] = workspace_dir

        try:
            # _execute_bot 包含同步阻塞的 ACPClient.chat()，需要在线程池中执行
            # 避免阻塞 aiohttp 事件循环
            loop = asyncio.get_event_loop()
            result = await loop.run_in_executor(None, _execute_bot, bot_id, method, message, chat_id)
            return web.json_response(result)
        finally:
            os.chdir(original_dir)

    except Exception as e:
        print(f"[SandboxServer] Execution error: {e}")
        traceback.print_exc()
        return web.json_response({
            "success": False,
            "error": f"Sandbox execution error: {str(e)}"
        })


def _execute_bot(bot_id: str, method: str, message: str, chat_id: str) -> dict:
    """在沙箱内执行 Bot 调用"""
    try:
        from clawdboz.communication.acp_client import ACPClient

        # 获取注册的 bot 配置
        bot_info = _registered_bots.get(bot_id, {})
        acp_config = bot_info.get("acp_config", {})
        config = bot_info.get("config", {})

        # 修复：从 bot 配置中读取 system_prompt
        system_prompt = config.get("system_prompt", "") or config.get("bio", "")

        # 如果 bot 未注册（沙箱重启后），尝试从 workplace 的 .bot.md 动态加载
        if not system_prompt:
            bot_md_path = f"/workplace/workplace_{bot_id}/.bot.md"
            if os.path.exists(bot_md_path):
                try:
                    with open(bot_md_path, "r", encoding="utf-8") as f:
                        content = f.read()
                    name = ""
                    bio = ""
                    for line in content.split("\n"):
                        if line.startswith("Name:"):
                            name = line[5:].strip()
                        elif line.startswith("Bio:"):
                            bio = line[4:].strip()
                    if name:
                        if bio and len(bio) >= 20 and "skill" not in bio.lower():
                            system_prompt = f"你是{name}。{bio}。请始终以{name}的身份回答用户的问题。"
                        else:
                            system_prompt = f"你是{name}。请始终以{name}的身份回答用户的问题。"
                        print(f"[SandboxServer] 从 .bot.md 动态加载 {bot_id} system_prompt")
                except Exception as e:
                    print(f"[SandboxServer] 读取 .bot.md 失败: {e}")

        print(f"[SandboxServer] Bot '{bot_id}' system_prompt: {system_prompt[:50] if system_prompt else '(empty)'}...")

        # 如果有 ACP 配置，注入到环境变量或全局 CONFIG
        if acp_config:
            # 尝试更新 clawdboz 的 CONFIG
            try:
                from clawdboz.config import CONFIG
                CONFIG['acp'] = acp_config
            except Exception:
                pass

        # 创建 ACP 客户端
        acp_client = ACPClient(
            bot_ref=None,
            session_work_dir=os.environ.get('CLAWDBOZ_SESSION_WORK_DIR'),
            bot_work_dir=None,
            system_prompt=system_prompt if system_prompt else None
        )

        if method == "chat":
            response = acp_client.chat(message, timeout=120)
            return {
                "success": True,
                "result": response if response else "[无回复]"
            }
        else:
            return {
                "success": False,
                "error": f"Unsupported method: {method}"
            }

    except ImportError as e:
        return {
            "success": False,
            "error": f"Required module not available in sandbox: {e}"
        }
    except Exception as e:
        traceback_str = traceback.format_exc()
        print(f"[SandboxServer] Bot execution error: {e}\n{traceback_str}")
        return {
            "success": False,
            "error": f"Execution error: {str(e)}"
        }


async def health_handler(request):
    """健康检查"""
    return web.json_response({"status": "ok"})


def main():
    import argparse
    parser = argparse.ArgumentParser()
    parser.add_argument("--port", type=int, default=18443)
    parser.add_argument("--host", default="0.0.0.0")
    args = parser.parse_args()

    app = web.Application()
    app.router.add_post("/register", register_handler)
    app.router.add_post("/execute", execute_handler)
    app.router.add_get("/health", health_handler)

    print(f"[SandboxServer] Starting on {args.host}:{args.port}")
    web.run_app(app, host=args.host, port=args.port, print=None)


if __name__ == "__main__":
    main()
