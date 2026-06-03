#!/usr/bin/env python3
"""
clawdboz - 命令行工具

Web-first 模式：
    clawdboz init              # 初始化 Web Chat 项目
    clawdboz run               # 启动 Web Chat 服务器
    clawdboz bot list          # 列出所有 Bot
    clawdboz chat list         # 列出所有会话
    clawdboz chat send         # 发送消息

遗留飞书模式（可选）：
    clawdboz init --feishu     # 初始化飞书 Bot 项目
    clawdboz run --feishu      # 启动飞书 Bot
"""

import argparse
import json
import os
import shutil
import signal
import subprocess
import sys
import time
import uuid
import requests
import urllib.parse
import urllib.request
import asyncio
from websockets.asyncio.client import connect
from datetime import datetime
from pathlib import Path
from typing import Optional, List, Dict, Any


# =============================================================================
# 版本和配置工具
# =============================================================================

def get_version() -> str:
    """获取版本号 - 从 VERSION 文件读取"""
    try:
        version_file = os.path.join(os.path.dirname(__file__), 'VERSION')
        with open(version_file, 'r') as f:
            return f.read().strip()
    except Exception:
        return "5.0.0"


def get_templates_dir() -> Path:
    """获取模板文件目录"""
    try:
        from importlib import resources
        with resources.files('clawdboz') as pkg_path:
            templates_dir = pkg_path / 'templates'
            if templates_dir.exists():
                return templates_dir
    except Exception:
        pass

    templates_dir = Path(__file__).parent / 'templates'
    if templates_dir.exists():
        return templates_dir

    return Path(__file__).parent.parent


# =============================================================================
# Web CLI Client
# =============================================================================

class WebCLIClient:
    """Web Chat CLI 客户端"""

    def __init__(self, base_url: str = None, token: str = None):
        self.config_path = os.path.expanduser("~/.clawdboz/cli_config.json")
        self.project_config_path = self._find_project_config()

        # 加载配置（优先级：传入参数 > 项目 config.json > 本地 cli 配置）
        project_cfg = self._load_project_config()
        if project_cfg:
            webchat = project_cfg.get("webchat", {})
            self.token = webchat.get("token", "")
            port = webchat.get("port", 8080)
            use_https = webchat.get("https", False)
            protocol = "https" if use_https else "http"
            self.base_url = f"{protocol}://localhost:{port}"
        else:
            self.base_url = ""
            self.token = ""

        # 回退到本地 cli 配置
        if not self.base_url or not self.token:
            self.config = self._load_config()
            self.base_url = self.config.get("base_url", "")
            self.token = self.config.get("token", "")

        # 传入参数覆盖
        if base_url:
            self.base_url = base_url
        if token:
            self.token = token

        self.session = requests.Session()
        self.session.verify = False
        import urllib3
        urllib3.disable_warnings(urllib3.exceptions.InsecureRequestWarning)

    def _find_project_config(self) -> str:
        """查找项目根目录下的 config.json"""
        cwd = os.getcwd()
        path = os.path.join(cwd, "config.json")
        if os.path.exists(path):
            return path
        script_dir = os.path.dirname(os.path.abspath(__file__))
        for _ in range(5):
            path = os.path.join(script_dir, "config.json")
            if os.path.exists(path):
                return path
            script_dir = os.path.dirname(script_dir)
        return ""

    def _load_config(self) -> dict:
        if os.path.exists(self.config_path):
            try:
                with open(self.config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def _load_project_config(self) -> dict:
        if self.project_config_path and os.path.exists(self.project_config_path):
            try:
                with open(self.project_config_path, "r", encoding="utf-8") as f:
                    return json.load(f)
            except Exception:
                pass
        return {}

    def save_config(self):
        """保存 CLI 配置到项目 config.json"""
        if self.project_config_path and os.path.exists(os.path.dirname(self.project_config_path)):
            try:
                cfg = {}
                if os.path.exists(self.project_config_path):
                    with open(self.project_config_path, "r", encoding="utf-8") as f:
                        cfg = json.load(f)

                port = 8080
                use_https = False
                if self.base_url:
                    use_https = self.base_url.startswith("https")
                    try:
                        port = int(self.base_url.split(":")[-1])
                    except ValueError:
                        port = 443 if use_https else 80

                webchat_cfg = cfg.get("webchat", {})
                webchat_cfg["token"] = self.token
                cfg["webchat"] = webchat_cfg

                with open(self.project_config_path, "w", encoding="utf-8") as f:
                    json.dump(cfg, f, indent=2, ensure_ascii=False)
                print(f"配置已保存到项目: {self.project_config_path}")
                return
            except Exception as e:
                print(f"保存到项目配置失败: {e}")

        os.makedirs(os.path.dirname(self.config_path), exist_ok=True)
        cfg = {"base_url": self.base_url, "token": self.token}
        with open(self.config_path, "w", encoding="utf-8") as f:
            json.dump(cfg, f, indent=2)
        print(f"配置已保存到本地: {self.config_path}")

    def _url(self, path: str) -> str:
        return f"{self.base_url.rstrip('/')}{path}"

    def _get(self, path: str, params: dict = None) -> dict:
        p = params or {}
        p["token"] = self.token
        headers = {"Cache-Control": "no-cache", "Pragma": "no-cache"}
        resp = self.session.get(self._url(path), params=p, headers=headers, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _post(self, path: str, data: dict = None, params: dict = None) -> dict:
        d = data or {}
        d["token"] = self.token
        resp = self.session.post(self._url(path), json=d, params=params, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _put(self, path: str, data: dict = None) -> dict:
        d = data or {}
        d["token"] = self.token
        resp = self.session.put(self._url(path), json=d, timeout=30)
        resp.raise_for_status()
        return resp.json()

    def _delete(self, path: str) -> dict:
        resp = self.session.delete(
            self._url(path), params={"token": self.token}, timeout=30
        )
        resp.raise_for_status()
        return resp.json()

    # ========== 用户资料 ==========
    def get_profile(self) -> dict:
        return self._get("/api/user/profile")

    def update_profile(self, name: str, bio: str = "") -> dict:
        return self._post("/api/user/profile/update", {"name": name, "bio": bio})

    # ========== Bot 管理 ==========
    def list_bots(self) -> List[dict]:
        return self._get("/api/bots").get("bots", [])

    def get_bot(self, bot_id: str) -> dict:
        return self._get(f"/api/bots/{bot_id}")

    def create_bot(self, bot_id: str, name: str = "", bio: str = "") -> dict:
        return self._post("/api/bots", {"bot_id": bot_id, "name": name, "bio": bio})

    def update_bot(self, bot_id: str, name: str = "", bio: str = "",
                   avatar_color: str = "", avatar_icon: str = "") -> dict:
        data = {"name": name, "bio": bio}
        if avatar_color:
            data["avatar_color"] = avatar_color
        if avatar_icon:
            data["avatar_icon"] = avatar_icon
        return self._put(f"/api/bots/{bot_id}", data)

    def delete_bot(self, bot_id: str) -> dict:
        return self._delete(f"/api/bots/{bot_id}")

    # ========== 会话管理 ==========
    def list_sessions(self) -> List[dict]:
        return self._get("/api/sessions").get("sessions", [])

    def get_session(self, chat_id: str) -> dict:
        return self._get(f"/api/sessions/{chat_id}")

    def delete_session(self, chat_id: str) -> dict:
        return self._delete(f"/api/sessions/{chat_id}")

    def create_session(self, chat_id: str, bot_ids: List[str], name: str = "") -> dict:
        return self._post("/api/sessions", {"id": chat_id, "bot_ids": bot_ids, "name": name}, params={"token": self.token})

    # ========== 朋友圈 ==========
    def list_moments(self, limit: int = 20, offset: int = 0) -> dict:
        return self._get("/api/moments", {"limit": limit, "offset": offset})

    def post_moment(self, content: str, images: List[str] = None,
                    sender_id: str = "user", sender_type: str = "user") -> dict:
        data = {
            "content": content,
            "images": images or [],
            "sender_id": sender_id,
            "sender_type": sender_type
        }
        return self._post("/api/moments", data)

    def like_moment(self, moment_id: str, sender_id: str = "user", sender_type: str = "user") -> dict:
        return self._post(f"/api/moments/{moment_id}/like", {"sender_id": sender_id, "sender_type": sender_type})

    def comment_moment(self, moment_id: str, content: str,
                       sender_id: str = "user", sender_type: str = "user") -> dict:
        return self._post(f"/api/moments/{moment_id}/comment", {
            "content": content, "sender_id": sender_id, "sender_type": sender_type
        })

    # ========== 远程 Bot 管理 ==========
    def discover_remote_bots(self) -> dict:
        """发现远程 Bot"""
        return self._get("/api/remote/bots", params={"token": self.token})

    def publish_bot(self, bot_id: str, display_name: str = "", description: str = "",
                   capabilities: list = None, is_sandboxed: bool = True,
                   requires_fs_access: bool = False) -> dict:
        """发布本地 Bot 到远程"""
        data = {
            "bot_id": bot_id,
            "display_name": display_name or bot_id,
            "description": description,
            "capabilities": capabilities or [],
            "is_sandboxed": is_sandboxed,
            "requires_fs_access": requires_fs_access
        }
        return self._post("/api/remote/publish", data, params={"token": self.token})

    def unpublish_bot(self, bot_id: str) -> dict:
        """取消发布 Bot"""
        url = f"{self.base_url}/api/remote/unpublish/{bot_id}?token={urllib.parse.quote(self.token)}"
        resp = self.session.delete(url, verify=False, timeout=10)
        return resp.json()

    def get_published_bots(self) -> dict:
        """获取已发布的 Bot 列表"""
        return self._get("/api/remote/published", params={"token": self.token})

    def add_remote_bot(self, instance_id: str, bot_id: str) -> dict:
        """添加远程 Bot"""
        data = {"instance_id": instance_id, "bot_id": bot_id}
        return self._post("/api/remote/add-bot", data, params={"token": self.token})

    def get_added_remote_bots(self) -> dict:
        """获取已添加的远程 Bot"""
        # 这个端点不存在，使用 discover_remote_bots 过滤已添加的
        return self._get("/api/remote/bots", params={"token": self.token})

    # ========== 好友管理 ==========
    def send_friend_request(self, to_instance: str, message: str = "", to_bot_id: str = "") -> dict:
        """发送好友请求"""
        data = {"to_instance": to_instance, "message": message, "to_bot_id": to_bot_id}
        return self._post("/api/remote/friend-request", data, params={"token": self.token})

    def accept_friend_request(self, request_id: str, accept: bool = True) -> dict:
        """确认/拒绝好友请求"""
        return self._post(f"/api/remote/friend-accept/{request_id}",
                         {"accept": accept}, params={"token": self.token})

    def get_friend_requests(self) -> dict:
        """获取待处理的好友请求"""
        return self._get("/api/remote/friend-requests", params={"token": self.token})

    def get_friends(self) -> dict:
        """获取好友列表"""
        return self._get("/api/remote/friends", params={"token": self.token})

    def remove_friend(self, instance_id: str, bot_id: str = "") -> dict:
        """移除好友（Bot 级别）"""
        actual_bot_id = bot_id or "__all__"
        return self._delete(f"/api/remote/friends/{instance_id}/{actual_bot_id}")

    def get_bot_friends(self, bot_id: str) -> dict:
        """获取订阅了指定 bot 的实例列表（谁添加了我的 bot）"""
        return self._get("/api/remote/bot-friends", params={"token": self.token, "bot_id": bot_id})

    # ========== 聊天 ==========
    async def _chat_with_bots_async(self, bot_ids: List[str], message: str, chat_id: str,
                                    thinking_mode: bool = True, stream: bool = True,
                                    fetch_from_history: bool = False, is_hidden: bool = False):
        """Async WebSocket chat using websockets library"""
        ws_url = self.base_url.replace("https://", "wss://").replace("http://", "ws://")
        ws_url = f"{ws_url.rstrip('/')}/ws/chat?token={urllib.parse.quote(self.token)}"

        mode = "group" if len(bot_ids) > 1 else "single"

        # Message data to send
        msg_data = {
            "mode": mode,
            "bots": bot_ids,
            "message": message,
            "chat_id": chat_id,
            "thinking_mode": thinking_mode
        }
        if is_hidden:
            msg_data["is_hidden"] = True

        # Mode A: Smart wait for reply (for cli send)
        if fetch_from_history:
            finished = False
            success = False
            final_reply = ""
            chunks = []
            error_msg = ""
            has_generating = False
            start_time = time.time()
            DETECT_TIMEOUT = 120
            MAX_TIMEOUT = 125  # 比服务端超时稍长，避免 race condition

            try:
                async with connect(ws_url) as ws:
                    # Send message
                    await ws.send(json.dumps(msg_data))

                    # Wait for response
                    while time.time() - start_time < MAX_TIMEOUT:
                        try:
                            response = await asyncio.wait_for(ws.recv(), timeout=1.0)
                            data = json.loads(response)
                            msg_type = data.get("type")

                            if msg_type == "done":
                                finished = True
                                success = True
                                final_reply = data.get("final", "")
                                break
                            elif msg_type == "error":
                                finished = True
                                error_msg = data.get("error", "")
                                break
                            elif msg_type == "chunk":
                                has_generating = True
                                chunk_content = data.get("content", "")
                                if chunk_content:
                                    chunks.append(chunk_content)
                            elif msg_type == "start":
                                has_generating = True

                            # Early exit if we detected generation
                            if has_generating and (time.time() - start_time) > DETECT_TIMEOUT:
                                break

                        except asyncio.TimeoutError:
                            elapsed = time.time() - start_time
                            if not has_generating and elapsed > DETECT_TIMEOUT:
                                break
                            continue

            except Exception as e:
                print(f"[WebSocket 错误] {e}")

            # 优先使用 done 中的 final 字段
            if final_reply:
                print(final_reply)
                return final_reply
            # 其次使用累积的 chunks
            if chunks:
                reply_text = "".join(chunks)
                print(reply_text)
                return reply_text
            # 如果收到 error 消息
            if error_msg:
                print(f"[错误] {error_msg}")
                return f"[错误] {error_msg}"
            # 完全超时且无内容
            if has_generating:
                print("[超时] Bot 响应时间过长，请稍后通过会话历史查看完整回复")
            else:
                print("[超时] Bot 未响应，请检查 Bot 状态或网络连接")
            return ""

        # Mode B: Stream/non-stream collection (for interactive)
        replies = []
        results = {}
        finished = set()
        thinking_map = {}
        final_result = {}

        try:
            async with connect(ws_url) as ws:
                # Send message
                await ws.send(json.dumps(msg_data))

                # Receive messages
                while True:
                    response = await ws.recv()
                    data = json.loads(response)

                    msg_type = data.get("type")
                    bid = data.get("bot_id", "unknown")
                    is_thinking = data.get("is_thinking", False)

                    if msg_type == "start":
                        if mode == "group" and stream:
                            print(f"\n[{bid}] 开始回复...")

                    elif msg_type == "thinking":
                        thinking_map[bid] = thinking_map.get(bid, "") + data.get("content", "")

                    elif msg_type == "chunk":
                        chunk = data.get("content", "")
                        if is_thinking:
                            thinking_map[bid] = thinking_map.get(bid, "") + chunk
                        else:
                            if mode == "single":
                                if stream:
                                    sys.stdout.write(chunk)
                                    sys.stdout.flush()
                                replies.append(chunk)
                            else:
                                if stream:
                                    sys.stdout.write(f"[{bid}] {chunk}")
                                    sys.stdout.flush()
                                results[bid] = results.get(bid, "") + chunk

                    elif msg_type == "done":
                        if mode == "single":
                            if stream:
                                print()
                            final_result[bid] = data.get("final", "")
                        else:
                            if stream:
                                print(f"\n[{bid}] 回复完成")
                            final_result[bid] = data.get("final", "")
                        finished.add(bid)
                        break

                    elif msg_type == "error":
                        if stream:
                            print(f"\n[{bid}] 错误: {data.get('error', '未知错误')}")
                        finished.add(bid)
                        break

        except Exception as e:
            print(f"[WebSocket 错误] {e}")

        # Return results
        if not stream:
            if mode == "single":
                bid = bot_ids[0]
                final_reply = final_result.get(bid, "")
                if not final_reply:
                    final_reply = "".join(replies)
                if final_reply:
                    print(final_reply)
                if thinking_mode:
                    for b, txt in thinking_map.items():
                        if txt.strip():
                            print(f"\n[思考过程] {txt.strip()}")
                return final_reply
            else:
                for bid in bot_ids:
                    txt = final_result.get(bid, "")
                    if not txt:
                        txt = results.get(bid, "")
                    if txt:
                        print(f"\n[{bid}] {txt}")
                if thinking_mode:
                    for b, txt in thinking_map.items():
                        if txt.strip():
                            print(f"\n[{b} 思考] {txt.strip()}")
                return final_result

        return "".join(replies) if mode == "single" else results

    def chat_with_bots(self, bot_ids: List[str], message: str, chat_id: str,
                       thinking_mode: bool = True, stream: bool = True,
                       fetch_from_history: bool = False, is_hidden: bool = False):
        """通过 WebSocket 发送消息并接收回复"""
        return asyncio.run(self._chat_with_bots_async(
            bot_ids, message, chat_id, thinking_mode, stream, fetch_from_history, is_hidden
        ))


# =============================================================================
# 工具函数
# =============================================================================

def print_table(headers: List[str], rows: List[List[str]]):
    """简单表格打印"""
    if not rows:
        print("(暂无数据)")
        return
    col_widths = [len(h) for h in headers]
    for row in rows:
        for i, cell in enumerate(row):
            col_widths[i] = max(col_widths[i], len(str(cell)))
    line = " | ".join(h.ljust(col_widths[i]) for i, h in enumerate(headers))
    print(line)
    print("-" * len(line))
    for row in rows:
        print(" | ".join(str(cell).ljust(col_widths[i]) for i, cell in enumerate(row)))


def format_time(ts: float) -> str:
    if not ts:
        return "-"
    return datetime.fromtimestamp(ts).strftime("%m-%d %H:%M")


def check_kimi_installation():
    """检测 Kimi CLI 安装和登录状态"""
    kimi_bin = None

    try:
        result = subprocess.run(['which', 'kimi'], capture_output=True, text=True, timeout=5)
        if result.returncode == 0 and result.stdout.strip():
            kimi_bin = result.stdout.strip()
    except Exception:
        pass

    if not kimi_bin:
        common_paths = [
            os.path.expanduser('~/.local/bin/kimi'),
            '/usr/local/bin/kimi',
            '/usr/bin/kimi',
        ]
        for path in common_paths:
            if os.path.isfile(path) and os.access(path, os.X_OK):
                kimi_bin = path
                break

    if not kimi_bin:
        return False, False, None

    logged_in = False
    credentials_paths = [
        os.path.expanduser('~/.agents/credentials/kimi-code.json'),
        os.path.expanduser('~/.agents/credentials/kimi.json'),
    ]
    for cred_path in credentials_paths:
        if os.path.exists(cred_path):
            try:
                with open(cred_path, 'r', encoding='utf-8') as f:
                    creds = json.load(f)
                if creds.get('access_token'):
                    logged_in = True
                    break
            except Exception:
                pass

    return True, logged_in, kimi_bin


# =============================================================================
# ACP 工具自动发现
# =============================================================================

ACP_TOOL_CONFIGS = [
    {
        "id": "kimi",
        "name": "Kimi Code",
        "type": "kimi",
        "executable_names": ["kimi"],
        "common_paths": ["~/.local/bin/kimi", "/usr/local/bin/kimi", "/usr/bin/kimi"],
        "args": ["acp"],
    },
    {
        "id": "claude",
        "name": "Claude Code",
        "type": "claudecode",
        "executable_names": ["claude", "claude-code"],
        "common_paths": ["/usr/local/bin/claude", "/usr/bin/claude", "/usr/local/bin/claude-code"],
        "args": ["-m", "clawdboz.communication.claude_acp_stdio"],
        "use_sys_executable": True,
    },
    {
        "id": "opencode",
        "name": "Opencode",
        "type": "opencode",
        "executable_names": ["opencode"],
        "common_paths": ["~/.opencode/bin/opencode", "/usr/local/bin/opencode", "/usr/bin/opencode"],
        "args": ["acp"],
    },
    {
        "id": "openclaw",
        "name": "OpenClaw",
        "type": "openclaw",
        "executable_names": ["openclaw"],
        "common_paths": ["/usr/local/bin/openclaw", "/usr/bin/openclaw"],
        "args": ["acp"],
    },
    {
        "id": "hermes",
        "name": "Hermes Agent",
        "type": "hermes",
        "executable_names": ["hermes"],
        "common_paths": ["/usr/local/bin/hermes", "/usr/bin/hermes"],
        "args": ["acp"],
    },
]


def _find_executable(executable_names: List[str], common_paths: List[str]) -> Optional[str]:
    """查找可执行文件，先检查 PATH，再检查常见路径"""
    for name in executable_names:
        path = shutil.which(name)
        if path:
            return path
    for path in common_paths:
        expanded = os.path.expanduser(path)
        if os.path.isfile(expanded) and os.access(expanded, os.X_OK):
            return expanded
    return None


def detect_acp_tools() -> List[Dict[str, Any]]:
    """检测系统中安装的所有 ACP 工具"""
    found = []
    for tool in ACP_TOOL_CONFIGS:
        executable = _find_executable(tool["executable_names"], tool["common_paths"])
        if executable:
            found.append({
                "id": tool["id"],
                "name": tool["name"],
                "type": tool["type"],
                "executable": executable,
                "args": tool.get("args", ["acp"]),
                "use_sys_executable": tool.get("use_sys_executable", False),
            })
    return found


def test_acp_availability(tool_info: Dict[str, Any], timeout: int = 10) -> bool:
    """测试 ACP 工具是否能响应 initialize 请求"""
    import select as select_module

    provider = tool_info["type"]
    executable = tool_info["executable"]

    if tool_info.get("use_sys_executable"):
        cmd = [sys.executable] + tool_info.get("args", [])
    else:
        cmd = [executable] + tool_info.get("args", ["acp"])

    env = os.environ.copy()
    env["TERM"] = "dumb"
    env["NO_COLOR"] = "1"

    try:
        proc = subprocess.Popen(
            cmd,
            stdin=subprocess.PIPE,
            stdout=subprocess.PIPE,
            stderr=subprocess.PIPE,
            text=True,
            env=env,
            preexec_fn=os.setsid if hasattr(os, "setsid") else None,
        )
    except Exception:
        return False

    try:
        init_req = {
            "jsonrpc": "2.0",
            "id": str(uuid.uuid4()),
            "method": "initialize",
            "params": {"protocolVersion": 1, "capabilities": {}},
        }
        proc.stdin.write(json.dumps(init_req) + "\n")
        proc.stdin.flush()

        start = time.time()
        while time.time() - start < timeout:
            readable, _, _ = select_module.select([proc.stdout], [], [], 0.5)
            if readable:
                line = proc.stdout.readline()
                if line:
                    try:
                        resp = json.loads(line.strip())
                        if "result" in resp or "error" in resp:
                            return True
                    except json.JSONDecodeError:
                        pass
            if proc.poll() is not None:
                break

        return False
    finally:
        try:
            if hasattr(os, "killpg"):
                os.killpg(os.getpgid(proc.pid), signal.SIGTERM)
            else:
                proc.terminate()
        except Exception:
            pass
        try:
            proc.kill()
        except Exception:
            pass


def fetch_clawdboz_knowledge() -> Optional[str]:
    """从 clawdboz.chat 获取使用说明文本"""
    try:
        req = urllib.request.Request(
            "https://clawdboz.chat",
            headers={"User-Agent": "Mozilla/5.0 (Clawdboz-Init)"},
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            html = resp.read().decode("utf-8", errors="ignore")
    except Exception:
        return None

    import re
    # 移除 script/style/nav/footer 标签
    html = re.sub(r"<script[^>]*>.*?</script>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<style[^>]*>.*?</style>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<nav[^>]*>.*?</nav>", "", html, flags=re.DOTALL | re.IGNORECASE)
    html = re.sub(r"<footer[^>]*>.*?</footer>", "", html, flags=re.DOTALL | re.IGNORECASE)

    # 提取 body
    body_match = re.search(r"<body[^>]*>(.*?)</body>", html, flags=re.DOTALL | re.IGNORECASE)
    if body_match:
        html = body_match.group(1)

    # 去掉所有标签
    text = re.sub(r"<[^>]+>", " ", html)
    text = re.sub(r"\s+", " ", text).strip()

    # 解码 HTML 实体
    import html
    text = html.unescape(text)

    if len(text) > 4000:
        text = text[:4000] + "...（内容已截断）"
    return text


# =============================================================================
# INIT 命令 - Web-first 模式
# =============================================================================

def init_project_web(work_dir: Optional[str] = None):
    """初始化 Web Chat 项目"""
    target_dir = work_dir or os.getcwd()

    print(f"[INIT] 初始化 Web Chat 项目: {target_dir}")

    # 检测 Kimi CLI 状态
    kimi_installed, kimi_logged_in, kimi_bin = check_kimi_installation()

    if not kimi_installed:
        print(f"[WARN] 未检测到 Kimi CLI，请先安装:")
        print(f"       curl -L code.agents.com/install.sh | bash")
    elif not kimi_logged_in:
        print(f"[WARN] Kimi CLI 已安装但未登录，请先登录:")
        print(f"       {kimi_bin} auth login")
    else:
        print(f"[OK] Kimi CLI 已安装并已登录: {kimi_bin}")

    # 自动发现所有 ACP 工具
    print("[INIT] 扫描 ACP 工具...")
    detected_tools = detect_acp_tools()
    available_clients = []

    for tool in detected_tools:
        print(f"[INIT] 检测到 {tool['name']}: {tool['executable']}")
        print(f"[INIT] 测试 {tool['name']} 可用性...")
        if test_acp_availability(tool, timeout=10):
            print(f"[OK] {tool['name']} 可用")
            client_id = f"{tool['id']}_client_{uuid.uuid4().hex[:6]}"
            available_clients.append({
                "id": client_id,
                "name": tool["name"],
                "type": tool["type"],
                "executable": tool["executable"],
                "enabled": True,
            })
        else:
            print(f"[WARN] {tool['name']} 未响应 ACP 协议，跳过")

    if available_clients:
        print(f"[OK] 共 {len(available_clients)} 个 ACP 客户端可用")
    else:
        print("[WARN] 未检测到可用的 ACP 客户端，Bot 将无法回复消息")

    # 创建目录
    dirs = [
        'WORKPLACE',
        'WORKPLACE/user_images',
        'WORKPLACE/user_files',
        'WORKPLACE/groupspace',
        '.agents',
        '.agents/skills',
        'logs',
    ]

    for d in dirs:
        path = os.path.join(target_dir, d)
        os.makedirs(path, exist_ok=True)
        print(f"[INIT] 创建目录: {d}/")

    # 创建 config.json（Web-first 配置）
    config_path = os.path.join(target_dir, 'config.json')
    if not os.path.exists(config_path):
        web_port = 8443
        config = {
            "project_root": target_dir,
            "webchat": {
                "port": web_port,
                "https": False,
                "cert": "ssl/server.crt",
                "key": "ssl/server.key",
                "token": f"clawdboz-{uuid.uuid4().hex[:16]}"
            },
            "remote": {
                "enabled": True,
                "registry_url": "https://api.clawdboz.chat",
                "instance_name": "",
                "host": "0.0.0.0",
                "port": web_port,
                "heartbeat_interval": 30,
                "connection_timeout": 10,
                "call_timeout": 30,
                "max_retries": 3,
                "sandbox": {
                    "enabled": False,
                    "docker": False,
                    "max_memory_mb": 512,
                    "timeout_seconds": 120
                },
                "fs_api_enabled": True,
                "fs_max_file_size": 10485760,
                "token_secret": "",
                "connection_mode": "center"
            },
            "python": {
                "venv": os.environ.get('VIRTUAL_ENV', '.venv'),
                "bin": sys.executable
            },
            "logs": {
                "main_log": "logs/main.log",
                "debug_log": "logs/bot_debug.log",
                "web_log": "logs/web.log"
            },
            "paths": {
                "workplace": "WORKPLACE",
                "user_images": "WORKPLACE/user_images",
                "user_files": "WORKPLACE/user_files",
                "mcp_config": ".agents/mcp.json",
                "skills_dir": ".agents/skills"
            }
        }

        if available_clients:
            config["acp"] = {"clients": available_clients}
            print(f"[INIT] 自动配置 {len(available_clients)} 个 ACP 客户端到 config.json")

        with open(config_path, 'w', encoding='utf-8') as f:
            json.dump(config, f, indent=2, ensure_ascii=False)

        print(f"[INIT] 创建配置文件: config.json")
        print(f"[INFO] Token: {config['webchat']['token']}")
        print(f"[WARN] 请编辑 config.json 配置端口和 HTTPS")
    else:
        print(f"[INFO] 配置文件已存在: config.json")

    # 创建 .agents/mcp.json
    mcp_path = os.path.join(target_dir, '.agents', 'mcp.json')
    if not os.path.exists(mcp_path):
        with open(mcp_path, 'w', encoding='utf-8') as f:
            json.dump({}, f, indent=2)
        print(f"[INIT] 创建 MCP 配置: .agents/mcp.json")

    # 复制内置技能
    BUILTIN_SKILLS_WHITELIST = [
        'find-skills',
        'local-memory',
        'scheduler',
        'feishu-api-sender',
        'webchat-sender',
    ]

    pkg_kimi_dir = os.path.join(os.path.dirname(__file__), '.agents')
    if os.path.exists(pkg_kimi_dir):
        pkg_skills_dir = os.path.join(pkg_kimi_dir, 'skills')
        if os.path.exists(pkg_skills_dir):
            target_skills_dir = os.path.join(target_dir, '.agents', 'skills')
            os.makedirs(target_skills_dir, exist_ok=True)

            for skill_name in os.listdir(pkg_skills_dir):
                pkg_skill_path = os.path.join(pkg_skills_dir, skill_name)
                if skill_name not in BUILTIN_SKILLS_WHITELIST:
                    continue
                if os.path.isdir(pkg_skill_path):
                    target_skill_path = os.path.join(target_skills_dir, skill_name)
                    if not os.path.exists(target_skill_path):
                        shutil.copytree(pkg_skill_path, target_skill_path)
                        print(f"[INIT] 复制 Skill: .agents/skills/{skill_name}/")
                    else:
                        print(f"[INFO] Skill 已存在: .agents/skills/{skill_name}/")

    # 创建助手 Bot（使用第一个可用的 ACP 客户端）
    if available_clients:
        first_client = available_clients[0]
        assistant_bot_id = "assistant"
        assistant_dir = os.path.join(target_dir, 'WORKPLACE', f'workplace_{assistant_bot_id}')
        os.makedirs(assistant_dir, exist_ok=True)

        assistant_md = os.path.join(assistant_dir, '.bot.md')
        if not os.path.exists(assistant_md):
            bio_text = (
                "你是 Clawdboz Web Chat 界面的官方使用助手。你的核心任务是解答用户关于 Web Chat 界面操作的问题。"
                "每次回答用户问题时，请先参考实时获取到的最新使用说明，然后基于这些知识给出清晰、准确的解答。"
                "请重点围绕以下 Web Chat 功能来回答：创建会话、单聊/群聊切换、@提及 Bot、文件上传与图片发送、"
                "远程 Bot 发现与添加、会话管理、思考模式切换、Terminal 终端和 Finder 文件管理等。"
            )

            bot_md_content = f"""# {assistant_bot_id}

ID: {assistant_bot_id}
Name: Clawdboz 助手
Bio: {bio_text}
Avatar Color: from-purple-400 to-purple-600
Avatar Icon: fa-question-circle
ACP Client ID: {first_client['id']}
Created: {time.strftime('%Y-%m-%d %H:%M:%S')}
"""
            with open(assistant_md, 'w', encoding='utf-8') as f:
                f.write(bot_md_content)
            print(f"[INIT] 创建助手 Bot: {assistant_bot_id} (使用 {first_client['name']})")
        else:
            print(f"[INFO] 助手 Bot 已存在: {assistant_bot_id}")

        # 创建初始欢迎会话（session ID 与前端格式一致）
        session_id = f"session_{uuid.uuid4().hex[:16]}"
        session_dir = os.path.join(assistant_dir, f"w_{session_id}")
        os.makedirs(session_dir, exist_ok=True)

        session_json = {
            "meta": {
                "id": session_id,
                "chat_type": "single",
                "bot_ids": [assistant_bot_id],
                "name": "欢迎使用 Clawdboz",
                "created_at": time.time(),
                "updated_at": time.time(),
                "is_group": False,
                "thinking_mode": False,
                "source": "web"
            },
            "messages": [
                {
                    "sender": assistant_bot_id,
                    "content": "你好！我是 Clawdboz 助手，很高兴为你服务。如果你在使用 Web Chat 界面过程中遇到任何问题，随时可以问我！",
                    "time": time.time()
                }
            ],
            "stats": {
                "message_count": 1,
                "last_active": time.time()
            }
        }

        session_path = os.path.join(session_dir, 'session.json')
        if not os.path.exists(session_path):
            with open(session_path, 'w', encoding='utf-8') as f:
                json.dump(session_json, f, indent=2, ensure_ascii=False)
            print(f"[INIT] 创建初始会话: {session_id}")

    print(f"\n[INIT] Web Chat 项目初始化完成！")
    print(f"\n下一步:")
    print(f"  1. 编辑 config.json 配置端口和 HTTPS")
    print(f"  2. 运行: clawdboz run")
    if available_clients:
        web_port = json.load(open(config_path))['webchat']['port']
        print(f"  3. 访问: http://localhost:{web_port}")
        print(f"\n已配置的 ACP 客户端:")
        for client in available_clients:
            print(f"    - {client['name']} ({client['type']})")
    else:
        print(f"  3. 访问: http://localhost:{json.load(open(config_path))['webchat']['port']}")
        print(f"\n[WARN] 未配置 ACP 客户端，请至少安装一种 Agent 工具")


def init_project_feishu(work_dir: Optional[str] = None):
    """初始化飞书 Bot 项目（遗留模式）"""
    print("[INIT] 初始化飞书 Bot 项目（遗留模式）")
    # 这里保留原有的飞书初始化逻辑
    # ... (原有代码)


# =============================================================================
# RUN 命令 - Web-first 模式
# =============================================================================

def run_web_server(port: Optional[int] = None, token: Optional[str] = None, config: Optional[str] = None):
    """启动 Web Chat 服务器"""
    from clawdboz.core.bot_manager import BotManager
    from clawdboz.web import start_web_chat

    # 加载配置
    if config:
        config_path = config
    else:
        config_path = os.path.join(os.getcwd(), 'config.json')

    if not os.path.exists(config_path):
        print(f"[ERROR] 配置文件不存在: {config_path}")
        print("请先运行: clawdboz init")
        sys.exit(1)

    try:
        with open(config_path, "r", encoding="utf-8") as f:
            cfg = json.load(f)
    except Exception as e:
        print(f"[ERROR] 无法读取配置文件: {e}")
        sys.exit(1)

    # 读取 webchat 配置
    webchat_cfg = cfg.get("webchat", {})
    server_port = port or webchat_cfg.get("port", 8443)
    use_https = webchat_cfg.get("https", False)
    ssl_cert_path = webchat_cfg.get("cert", "ssl/server.crt")
    ssl_key_path = webchat_cfg.get("key", "ssl/server.key")
    auth_token = token or webchat_cfg.get("token", "")

    if not auth_token:
        print("[ERROR] config.json 中缺少 webchat.token 配置")
        sys.exit(1)

    print("=" * 60)
    print("启动 Web Chat 服务器")
    print("=" * 60)
    print(f"端口: {server_port}")
    print(f"HTTPS: {'是' if use_https else '否'}")
    print(f"Token: {auth_token[:10]}...")

    # 初始化 BotManager
    workplace = os.path.join(os.path.dirname(config_path), "WORKPLACE")
    manager = BotManager(base_workplace=workplace)

    # 加载已存在的 Bot
    import glob
    for wp_dir in glob.glob(os.path.join(workplace, "workplace_*")):
        bot_id = os.path.basename(wp_dir).replace("workplace_", "")
        if not bot_id.isalnum():
            continue
        if bot_id in manager.bots:
            continue
        try:
            bot_md_path = os.path.join(wp_dir, ".bot.md")
            system_prompt = f"你是{bot_id}，一个友好的AI助手。"
            if os.path.exists(bot_md_path):
                with open(bot_md_path, 'r') as f:
                    content = f.read()
                    for line in content.split('\n'):
                        if line.startswith('Bio:'):
                            bio = line.replace('Bio:', '').strip()
                            if bio and bio != bot_id:
                                system_prompt = bio
                            break
            manager.register(bot_id, "webchat-bot", "webchat-secret", system_prompt=system_prompt)
            if bot_id in manager.bots:
                bot = manager.bots[bot_id]
                if os.path.exists(bot_md_path):
                    with open(bot_md_path, 'r') as f:
                        for line in f:
                            if line.startswith('Name:'):
                                name_from_file = line.replace('Name:', '').strip()
                                if name_from_file:
                                    bot.name = name_from_file
                                break
            print(f"[INFO] 加载 Bot: {bot_id}")
        except Exception as e:
            print(f"[WARN] 加载 Bot {bot_id} 失败: {e}")

    # 启动服务器
    start_web_chat(
        bots=manager.bots,
        port=server_port,
        auth_token=auth_token,
        base_workplace=workplace,
        blocking=True
    )


def run_feishu_bot(app_id: Optional[str], app_secret: Optional[str], config: Optional[str] = None):
    """启动飞书 Bot（遗留模式）"""
    print("[RUN] 启动飞书 Bot（遗留模式）")
    from clawdboz.simple_bot import Bot

    try:
        bot = Bot(
            app_id=app_id,
            app_secret=app_secret,
            config_path=config
        )
        bot.run()
    except ValueError as e:
        print(f"[ERROR] {e}")
        sys.exit(1)
    except KeyboardInterrupt:
        print("\n[RUN] 已停止")
    except Exception as e:
        print(f"[ERROR] 运行失败: {e}")
        sys.exit(1)


# =============================================================================
# Web 守护进程管理
# =============================================================================

def _get_daemon_paths(config_path: Optional[str] = None):
    """获取守护进程 PID 和日志文件路径"""
    if config_path and os.path.exists(config_path):
        root = os.path.dirname(os.path.abspath(config_path))
    elif os.path.exists(os.path.join(os.getcwd(), "config.json")):
        root = os.getcwd()
    else:
        root = os.path.expanduser("~/.clawdboz")

    daemon_dir = os.path.join(root, ".clawdboz")
    os.makedirs(daemon_dir, exist_ok=True)

    pid_file = os.path.join(daemon_dir, "web_daemon.pid")
    log_file = os.path.join(daemon_dir, "web_daemon.log")
    return pid_file, log_file


def _pid_alive(pid: int) -> bool:
    """检查进程是否存活"""
    try:
        os.kill(pid, 0)
        return True
    except (OSError, ProcessLookupError):
        return False


def daemon_start(port: Optional[int] = None,
                 token: Optional[str] = None,
                 config: Optional[str] = None):
    """以守护进程模式启动 Web Chat 服务器"""
    pid_file, log_file = _get_daemon_paths(config)

    # 检查是否已在运行
    if os.path.exists(pid_file):
        with open(pid_file, "r", encoding="utf-8") as f:
            try:
                old_pid = int(f.read().strip())
            except ValueError:
                old_pid = None
        if old_pid and _pid_alive(old_pid):
            print(f"[INFO] Web 守护进程已在运行 (PID: {old_pid})")
            print(f"[INFO] 日志: {log_file}")
            return
        else:
            os.remove(pid_file)

    # 构建启动命令（子进程以普通前台模式运行，但通过 start_new_session 脱离终端）
    cmd = [sys.executable, "-m", "clawdboz.cli", "web"]
    if port:
        cmd += ["--port", str(port)]
    if token:
        cmd += ["--token", token]
    if config:
        cmd += ["--config", config]

    # 启动后台进程，脱离终端会话
    with open(log_file, "a", encoding="utf-8") as log_f:
        # 先写入启动标记
        log_f.write(f"\n[{datetime.now().strftime('%Y-%m-%d %H:%M:%S')}] 启动守护进程\n")
        log_f.flush()
        proc = subprocess.Popen(
            cmd,
            stdout=log_f,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            start_new_session=True,
            cwd=os.getcwd(),
        )

    with open(pid_file, "w", encoding="utf-8") as f:
        f.write(str(proc.pid))

    # 启动后短暂等待，确认进程存活（避免端口冲突等立即退出的情况）
    time.sleep(1.5)
    if not _pid_alive(proc.pid):
        os.remove(pid_file)
        print(f"[ERROR] Web 守护进程启动失败，请检查日志: {log_file}")
        return

    # 解析实际使用的端口和 Token，用于展示访问 URL
    display_port = port
    display_token = token or ""
    cfg_path = config or os.path.join(os.getcwd(), "config.json")
    if os.path.exists(cfg_path):
        try:
            with open(cfg_path, "r", encoding="utf-8") as f:
                cfg = json.load(f)
            webchat = cfg.get("webchat", {})
            if display_port is None:
                display_port = webchat.get("port", 8443)
            if not display_token:
                display_token = webchat.get("token", "")
        except Exception:
            pass
    if display_port is None:
        display_port = 8443

    url = f"http://localhost:{display_port}/static/index.html"
    if display_token:
        url += f"?token={display_token}"

    print(f"[OK] Web 守护进程已启动 (PID: {proc.pid})")
    print(f"[INFO] 访问地址: {url}")
    print(f"[INFO] 日志: {log_file}")
    print(f"[INFO] 停止命令: clawdboz web stop")


def daemon_stop(config: Optional[str] = None):
    """停止 Web Chat 守护进程"""
    pid_file, _ = _get_daemon_paths(config)

    if not os.path.exists(pid_file):
        print("[INFO] Web 守护进程未运行")
        return

    with open(pid_file, "r", encoding="utf-8") as f:
        try:
            pid = int(f.read().strip())
        except ValueError:
            print("[WARN] PID 文件损坏，已清理")
            os.remove(pid_file)
            return

    if not _pid_alive(pid):
        print("[INFO] Web 守护进程未运行")
        os.remove(pid_file)
        return

    # 先尝试 SIGTERM
    try:
        os.kill(pid, signal.SIGTERM)
    except OSError as e:
        print(f"[WARN] 发送终止信号失败: {e}")
        os.remove(pid_file)
        return

    # 等待退出（最多 15 秒）
    for _ in range(30):
        if not _pid_alive(pid):
            break
        time.sleep(0.5)
    else:
        try:
            os.kill(pid, signal.SIGKILL)
            time.sleep(0.3)
        except OSError:
            pass

    if os.path.exists(pid_file):
        os.remove(pid_file)

    if _pid_alive(pid):
        print(f"[WARN] 守护进程未能完全停止 (PID: {pid})，请手动检查")
    else:
        print(f"[OK] Web 守护进程已停止 (PID: {pid})")


def daemon_status(config: Optional[str] = None):
    """查看 Web 守护进程状态"""
    pid_file, log_file = _get_daemon_paths(config)

    if not os.path.exists(pid_file):
        print("[INFO] Web 守护进程未运行")
        return

    with open(pid_file, "r", encoding="utf-8") as f:
        try:
            pid = int(f.read().strip())
        except ValueError:
            print("[WARN] PID 文件损坏")
            return

    if _pid_alive(pid):
        print(f"[OK] Web 守护进程运行中 (PID: {pid})")
        print(f"[INFO] 日志: {log_file}")
    else:
        print(f"[WARN] PID 文件存在但进程已不存在 (PID: {pid})")
        print("      建议运行: clawdboz web stop 清理状态")


def daemon_restart(port: Optional[int] = None,
                   token: Optional[str] = None,
                   config: Optional[str] = None):
    """重启 Web Chat 守护进程"""
    print("[INFO] 重启 Web 守护进程...")
    daemon_stop(config)
    time.sleep(0.5)
    daemon_start(port, token, config)


# =============================================================================
# Status 命令
# =============================================================================

def show_status():
    """显示状态信息"""
    print(f"Clawdboz v{get_version()}")
    print()

    # 检查配置文件
    if os.path.exists('config.json'):
        print("[OK] 找到配置文件: config.json")
        try:
            with open('config.json', 'r') as f:
                config = json.load(f)

            # Web Chat 配置
            webchat = config.get('webchat', {})
            if webchat.get('token'):
                print(f"[OK] Web Chat Token: {webchat['token'][:10]}...")
                print(f"[OK] Web Chat 端口: {webchat.get('port', 8080)}")
            else:
                print("[WARN] Web Chat 未配置")

            # 飞书配置
            feishu = config.get('feishu', {})
            if feishu.get('app_id'):
                print(f"[OK] 飞书 App ID: {feishu['app_id'][:8]}...")
        except Exception as e:
            print(f"[ERROR] 配置文件格式错误: {e}")
    else:
        print("[WARN] 未找到配置文件: config.json")
        print("      运行 'clawdboz init' 初始化项目")

    # 检查目录
    dirs = ['WORKPLACE', 'logs', '.agents']
    for d in dirs:
        if os.path.exists(d):
            print(f"[OK] 目录存在: {d}/")
        else:
            print(f"[WARN] 目录缺失: {d}/")

    print()
    print("可用命令:")
    print("  clawdboz run     启动 Web Chat 服务器")
    print("  clawdboz bot     管理 Bot")
    print("  clawdboz chat    管理会话和聊天")


# =============================================================================
# 主命令行入口
# =============================================================================

def main():
    parser = argparse.ArgumentParser(
        prog='clawdboz',
        description='Clawdboz - Web-first Chat Bot Platform',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
示例:
  # Web-first 模式（默认）
  clawdboz init                          # 初始化 Web Chat 项目
  clawdboz run                           # 启动 Web Chat 服务器
  clawdboz bot list                      # 列出所有 Bot
  clawdboz chat list                     # 列出所有会话
  clawdboz chat send session_xxx "你好"  # 发送消息

  # 飞书模式（遗留）
  clawdboz init --feishu                 # 初始化飞书 Bot 项目
  clawdboz run --feishu                  # 启动飞书 Bot
        """
    )

    parser.add_argument(
        '--version',
        action='version',
        version=f'%(prog)s {get_version()}'
    )

    # 全局参数
    parser.add_argument("--url", help="Web API 基础 URL（仅 Web CLI 命令）")
    parser.add_argument("--token", help="访问 Token（仅 Web CLI 命令）")

    subparsers = parser.add_subparsers(dest='command', help='可用命令')

    # ========== init 命令 ==========
    init_parser = subparsers.add_parser('init', help='初始化项目')
    init_parser.add_argument('--dir', help='指定项目目录（默认当前目录）')
    init_parser.add_argument('--feishu', action='store_true', help='使用飞书 Bot 模式（遗留）')

    # ========== run 命令 ==========
    run_parser = subparsers.add_parser('run', help='启动服务')
    run_parser.add_argument('--port', type=int, help='Web 服务器端口（覆盖配置）')
    run_parser.add_argument('--token', help='认证 Token（覆盖配置）')
    run_parser.add_argument('--config', '-c', help='配置文件路径')
    run_parser.add_argument('--feishu', action='store_true', help='启动飞书 Bot（遗留）')
    run_parser.add_argument('--app-id', help='飞书 App ID（仅飞书模式）')
    run_parser.add_argument('--app-secret', help='飞书 App Secret（仅飞书模式）')

    # ========== web 命令 ==========
    web_parser = subparsers.add_parser('web', help='启动 Web Chat 服务器')
    web_parser.add_argument('--port', type=int, help='Web 服务器端口（覆盖配置）')
    web_parser.add_argument('--token', help='认证 Token（覆盖配置）')
    web_parser.add_argument('--config', '-c', help='配置文件路径')

    # web 子命令：start / stop / restart / status
    web_sub = web_parser.add_subparsers(dest='web_cmd', help='守护进程操作')
    web_sub.required = False

    web_start = web_sub.add_parser('start', help='以守护进程模式启动 Web Chat 服务器')
    web_start.add_argument('--port', type=int, help='Web 服务器端口（覆盖配置）')
    web_start.add_argument('--token', help='认证 Token（覆盖配置）')
    web_start.add_argument('--config', '-c', help='配置文件路径')

    web_stop = web_sub.add_parser('stop', help='停止 Web Chat 守护进程')
    web_stop.add_argument('--config', '-c', help='配置文件路径')

    web_restart = web_sub.add_parser('restart', help='重启 Web Chat 守护进程')
    web_restart.add_argument('--port', type=int, help='Web 服务器端口（覆盖配置）')
    web_restart.add_argument('--token', help='认证 Token（覆盖配置）')
    web_restart.add_argument('--config', '-c', help='配置文件路径')

    web_status = web_sub.add_parser('status', help='查看 Web Chat 守护进程状态')
    web_status.add_argument('--config', '-c', help='配置文件路径')

    # ========== status 命令 ==========
    subparsers.add_parser('status', help='查看项目状态')

    # ========== bot 命令 ==========
    bot_parser = subparsers.add_parser('bot', help='Bot 管理')
    bot_sub = bot_parser.add_subparsers(dest='bot_cmd', help='Bot 子命令')

    bot_sub.add_parser('list', help='列出所有 Bot')

    bot_create = bot_sub.add_parser('create', help='创建 Bot')
    bot_create.add_argument('bot_id', help='Bot ID')
    bot_create.add_argument('--name', default='', help='Bot 名称')
    bot_create.add_argument('--bio', default='', help='Bot 介绍')

    bot_info = bot_sub.add_parser('info', help='查看 Bot 详情')
    bot_info.add_argument('bot_id', help='Bot ID')

    bot_edit = bot_sub.add_parser('edit', help='编辑 Bot')
    bot_edit.add_argument('bot_id', help='Bot ID')
    bot_edit.add_argument('--name', default='', help='Bot 名称')
    bot_edit.add_argument('--bio', default='', help='Bot 介绍')

    bot_del = bot_sub.add_parser('delete', help='删除 Bot')
    bot_del.add_argument('bot_id', help='Bot ID')

    # ========== remote 命令（嵌套结构）==========
    remote_parser = subparsers.add_parser('remote', help='远程 Bot 管理')
    remote_sub = remote_parser.add_subparsers(dest='remote_cmd', help='远程子命令')

    # remote bots 子命令
    remote_bots = remote_sub.add_parser('bots', help='远程 Bot 操作')
    bots_sub = remote_bots.add_subparsers(dest='remote_bots_cmd', help='Bot 子命令')

    bots_sub.add_parser('list', help='发现远程 Bot')

    bots_publish = bots_sub.add_parser('publish', help='发布本地 Bot')
    bots_publish.add_argument('bot_id', help='Bot ID')
    bots_publish.add_argument('--display-name', help='显示名称')
    bots_publish.add_argument('--description', help='描述')
    bots_publish.add_argument('--capabilities', nargs='+', help='能力列表')
    bots_publish.add_argument('--no-sandbox', action='store_true', help='不使用沙箱')
    bots_publish.add_argument('--require-fs', action='store_true', help='需要文件访问')

    bots_unpublish = bots_sub.add_parser('unpublish', help='取消发布 Bot')
    bots_unpublish.add_argument('bot_id', help='Bot ID')

    bots_sub.add_parser('published', help='查看已发布的 Bot')

    bots_add = bots_sub.add_parser('add', help='添加远程 Bot')
    bots_add.add_argument('remote_bot_id', help='远程 Bot ID（格式: instance_id:bot_id）')

    bots_sub.add_parser('added', help='查看已添加的远程 Bot')
    bots_sub.add_parser('online', help='查看在线 Bot 列表（本地已发布 + 远程非好友）')

    bots_search = bots_sub.add_parser('search', help='搜索在线 Bot（本地已发布 + 远程非好友）')
    bots_search.add_argument('keyword', help='搜索关键词（匹配名称、ID、实例名）')

    # remote friends 子命令
    remote_friends = remote_sub.add_parser('friends', help='好友管理')
    friends_sub = remote_friends.add_subparsers(dest='remote_friends_cmd', help='好友子命令')

    friends_sub.add_parser('list', help='好友列表')

    friends_add = friends_sub.add_parser('add', help='发送好友请求')
    friends_add.add_argument('instance_id', help='目标实例 ID')
    friends_add.add_argument('--bot-id', help='目标 Bot ID（bot 级别好友，推荐指定）')
    friends_add.add_argument('--message', help='附加消息')

    friends_accept = friends_sub.add_parser('accept', help='接受好友请求')
    friends_accept.add_argument('request_id', help='请求 ID')
    friends_accept.add_argument('--reject', action='store_true', help='拒绝请求（兼容旧用法，推荐用 reject 子命令）')

    friends_reject = friends_sub.add_parser('reject', help='拒绝好友请求')
    friends_reject.add_argument('request_id', help='请求 ID')

    friends_sub.add_parser('requests', help='待处理的好友请求')

    friends_remove = friends_sub.add_parser('remove', help='移除好友（Bot 级别）')
    friends_remove.add_argument('target', help='目标（格式: instance_id 或 instance_id:bot_id）')
    friends_remove.add_argument('--bot-id', help='目标 Bot ID（不指定则移除整个实例关系，优先级低于 target 中的 :bot_id）')

    # remote bot-friends 子命令
    bot_friends_parser = remote_sub.add_parser('bot-friends', help='查看已发布 Bot 的好友列表（谁添加了我的 Bot）')
    bot_friends_parser.add_argument('bot_id', nargs='?', help='Bot ID（不传则列出所有已发布 Bot 的好友情况）')

    # ========== chat 命令 ==========
    chat_parser = subparsers.add_parser('chat', help='会话管理与聊天')
    chat_sub = chat_parser.add_subparsers(dest='chat_cmd', help='聊天子命令')

    chat_sub.add_parser('list', help='列出所有会话')

    chat_show = chat_sub.add_parser('show', help='查看会话属性')
    chat_show.add_argument('chat_id', help='会话 ID')

    chat_history = chat_sub.add_parser('history', help='查看会话历史消息')
    chat_history.add_argument('chat_id', help='会话 ID')

    chat_create = chat_sub.add_parser('create', help='创建会话')
    chat_create.add_argument('--bots', action='append', required=True, help='包含的 Bot ID')
    chat_create.add_argument('--name', default='', help='会话名称')

    chat_delete = chat_sub.add_parser('delete', help='删除会话')
    chat_delete.add_argument('chat_id', help='会话 ID')

    chat_send = chat_sub.add_parser('send', help='发送消息到会话')
    chat_send.add_argument('chat_id', help='会话 ID')
    chat_send.add_argument('message', nargs='?', default=None, help='消息内容')
    chat_send.add_argument('--bot', dest='bots', action='append', help='指定回复的 Bot')
    chat_send.add_argument('--thinking', action='store_true', help='启用思考模式')
    chat_send.add_argument('--hide', action='store_true', help='隐藏消息')

    chat_interactive = chat_sub.add_parser('interactive', help='交互式聊天')
    chat_interactive.add_argument('chat_id', help='会话 ID')
    chat_interactive.add_argument('--bot', dest='bots', action='append', help='指定回复的 Bot')
    chat_interactive.add_argument('--thinking', action='store_true', help='启用思考模式')

    chat_with = chat_sub.add_parser('with', help='直接与指定 Bot 聊天')
    chat_with.add_argument('bot_id', help='Bot ID')
    chat_with.add_argument('--message', '-m', help='发送单条消息')
    chat_with.add_argument('--non-interactive', '-n', action='store_true', help='非交互模式（从 stdin 读取消息，不进入交互循环）')
    chat_with.add_argument('--thinking', action='store_true', help='启用思考模式')

    # ========== contacts 命令 ==========
    contacts_parser = subparsers.add_parser('contacts', help='通讯录')
    contacts_sub = contacts_parser.add_subparsers(dest='contacts_cmd', help='通讯录子命令')
    contacts_sub.add_parser('list', help='列出所有联系人')

    # ========== moments 命令 ==========
    moments_parser = subparsers.add_parser('moments', help='朋友圈')
    moments_sub = moments_parser.add_subparsers(dest='moments_cmd', help='朋友圈子命令')

    moments_list = moments_sub.add_parser('list', help='查看朋友圈')
    moments_list.add_argument('--limit', type=int, default=20, help='每页数量')
    moments_list.add_argument('--offset', type=int, default=0, help='偏移量')

    moments_post = moments_sub.add_parser('post', help='发布朋友圈')
    moments_post.add_argument('content', help='内容')

    moments_like = moments_sub.add_parser('like', help='点赞/取消点赞')
    moments_like.add_argument('moment_id', help='动态 ID')

    moments_comment = moments_sub.add_parser('comment', help='评论')
    moments_comment.add_argument('moment_id', help='动态 ID')
    moments_comment.add_argument('content', help='评论内容')

    # ========== profile 命令 ==========
    profile_parser = subparsers.add_parser('profile', help='用户资料')
    profile_sub = profile_parser.add_subparsers(dest='profile_cmd', help='资料子命令')

    profile_sub.add_parser('show', help='查看资料')
    profile_update = profile_sub.add_parser('update', help='更新资料')
    profile_update.add_argument('--name', required=True, help='昵称')
    profile_update.add_argument('--bio', default='', help='简介')

    args = parser.parse_args()

    # ========== 命令处理 ==========

    if args.command == 'init':
        if args.feishu:
            init_project_feishu(args.dir)
        else:
            init_project_web(args.dir)

    elif args.command == 'run':
        if args.feishu:
            run_feishu_bot(args.app_id, args.app_secret, args.config)
        else:
            run_web_server(args.port, args.token, args.config)

    elif args.command == 'web':
        if getattr(args, 'web_cmd', None) == 'start':
            daemon_start(args.port, args.token, args.config)
        elif getattr(args, 'web_cmd', None) == 'stop':
            daemon_stop(args.config)
        elif getattr(args, 'web_cmd', None) == 'restart':
            daemon_restart(args.port, args.token, args.config)
        elif getattr(args, 'web_cmd', None) == 'status':
            daemon_status(args.config)
        else:
            # 无子命令时保持向后兼容：前台启动
            run_web_server(args.port, args.token, args.config)

    elif args.command == 'status':
        show_status()

    elif args.command in ['bot', 'chat', 'contacts', 'moments', 'profile', 'remote']:
        # Web CLI 命令 - 需要 Web 服务器运行
        client = WebCLIClient(
            base_url=getattr(args, "url", None),
            token=getattr(args, "token", None)
        )

        if not client.base_url or not client.token:
            print("错误: 未配置 Web 服务器连接")
            print("请先运行: clawdboz run")
            print("或使用: clawdboz config --url <URL> --token <TOKEN>")
            sys.exit(1)

        try:
            # Bot 命令
            if args.command == 'bot':
                if args.bot_cmd == 'list':
                    bots = client.list_bots()
                    rows = [[b["id"], b.get("name", ""), "✓" if b.get("registered") else "", b.get("bio", "")[:40]] for b in bots]
                    print_table(["ID", "名称", "注册", "简介"], rows)
                    print(f"\n共 {len(bots)} 个 Bot")

                elif args.bot_cmd == 'create':
                    res = client.create_bot(args.bot_id, args.name, args.bio)
                    print("创建成功" if res.get("success") else f"创建失败: {res.get('error')}")

                elif args.bot_cmd == 'info':
                    res = client.get_bot(args.bot_id)
                    print(f"ID:     {res.get('id')}")
                    print(f"Skills: {', '.join(res.get('skills', [])) or '(无)'}")
                    print(f"Memory: {res.get('memory') or '(无)'}")

                elif args.bot_cmd == 'edit':
                    res = client.update_bot(args.bot_id, args.name, args.bio)
                    print("更新成功" if res.get("success") else f"更新失败: {res.get('error')}")

                elif args.bot_cmd == 'delete':
                    res = client.delete_bot(args.bot_id)
                    print("删除成功" if res.get("success") else f"删除失败: {res.get('error')}")

            # Chat 命令
            elif args.command == 'chat':
                if args.chat_cmd == 'list':
                    sessions = client.list_sessions()
                    rows = []
                    for s in sessions:
                        bots = ",".join(s.get("bot_ids", []))
                        chat_type = "群聊" if len(s.get("bot_ids", [])) > 1 else "单聊"
                        rows.append([s["id"], s.get("name", ""), chat_type, bots, format_time(s.get("updated_at"))])
                    print_table(["ID", "名称", "类型", "Bots", "更新时间"], rows)
                    print(f"\n共 {len(sessions)} 个会话")

                elif args.chat_cmd == 'show':
                    res = client.get_session(args.chat_id)
                    bot_ids = res.get("bot_ids", [])
                    print(f"会话 ID: {res.get('id')}")
                    print(f"名称:    {res.get('name') or '(未命名)'}")
                    print(f"类型:    {'群聊' if res.get('is_group') else '单聊'}")
                    print(f"Bots:    {', '.join(bot_ids) if bot_ids else '(无)'}")
                    print(f"消息数:  {len(res.get('messages', []))}")

                elif args.chat_cmd == 'history':
                    res = client.get_session(args.chat_id)
                    output = {
                        "id": res.get("id"),
                        "name": res.get("name"),
                        "bot_ids": res.get("bot_ids", []),
                        "is_group": res.get("is_group", False),
                        "messages": res.get("messages", [])
                    }
                    print(json.dumps(output, ensure_ascii=False, indent=2))

                elif args.chat_cmd == 'create':
                    chat_id = f"session_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"
                    res = client.create_session(chat_id, args.bots, args.name)
                    if res.get("success"):
                        print(f"创建成功: {chat_id}")
                    else:
                        print(f"创建失败: {res.get('error')}")

                elif args.chat_cmd == 'delete':
                    res = client.delete_session(args.chat_id)
                    print("删除成功" if res.get("success") else f"删除失败: {res.get('error')}")

                elif args.chat_cmd == 'send':
                    message = args.message
                    if message is None:
                        try:
                            message = sys.stdin.read().strip()
                        except EOFError:
                            message = ""
                    if not message:
                        print("错误: 消息内容为空")
                        sys.exit(1)

                    session = client.get_session(args.chat_id)
                    bot_ids = args.bots or session.get("bot_ids", [])
                    if not bot_ids:
                        print("错误: 无法确定回复的 Bot，请使用 --bot 指定")
                        sys.exit(1)

                    thinking_mode = args.thinking
                    is_hidden = getattr(args, 'hide', False)
                    client.chat_with_bots(bot_ids, message, args.chat_id, thinking_mode, fetch_from_history=True, is_hidden=is_hidden)

                elif args.chat_cmd == 'interactive':
                    session = client.get_session(args.chat_id)
                    bot_ids = args.bots or session.get("bot_ids", [])
                    if not bot_ids:
                        print("错误: 无法确定回复的 Bot，请使用 --bot 指定")
                        sys.exit(1)

                    chat_type = "群聊" if len(bot_ids) > 1 else "单聊"
                    print(f"进入交互式 {chat_type}，Bots: {', '.join(bot_ids)}")
                    print("输入 'quit' 或 'exit' 退出")
                    thinking_mode = args.thinking

                    while True:
                        try:
                            msg = input("\n👤 You: ").strip()
                        except EOFError:
                            break
                        if msg.lower() in ("quit", "exit", "q"):
                            print("👋 再见!")
                            break
                        if not msg:
                            continue
                        client.chat_with_bots(bot_ids, msg, args.chat_id, thinking_mode, stream=False)

                elif args.chat_cmd == 'with':
                    # 直接与指定 Bot 聊天
                    bot_id = args.bot_id

                    # 生成会话 ID
                    chat_id = f"session_{int(time.time() * 1000)}_{uuid.uuid4().hex[:8]}"

                    # 创建会话
                    res = client.create_session(chat_id, [bot_id], f"与 {bot_id} 的聊天")
                    if not res.get("success"):
                        print(f"创建会话失败: {res.get('error')}")
                        sys.exit(1)

                    print(f"✓ 已创建会话: {chat_id}", file=sys.stderr)

                    # 非交互模式
                    if args.non_interactive:
                        message = args.message
                        if message is None:
                            # 从 stdin 读取消息
                            try:
                                message = sys.stdin.read().strip()
                            except EOFError:
                                message = ""

                        if not message:
                            print("错误: 消息内容为空", file=sys.stderr)
                            sys.exit(1)

                        client.chat_with_bots([bot_id], message, chat_id, args.thinking, fetch_from_history=True)

                    # 指定了单条消息
                    elif args.message:
                        client.chat_with_bots([bot_id], args.message, chat_id, args.thinking, fetch_from_history=True)

                    # 交互模式（默认）
                    else:
                        print(f"开始与 {bot_id} 聊天", file=sys.stderr)
                        print("输入 'quit' 或 'exit' 退出", file=sys.stderr)

                        while True:
                            try:
                                msg = input("\n👤 You: ").strip()
                            except EOFError:
                                break
                            if msg.lower() in ("quit", "exit", "q"):
                                print("👋 再见!", file=sys.stderr)
                                break
                            if not msg:
                                continue
                            client.chat_with_bots([bot_id], msg, chat_id, args.thinking, stream=False)

            # Contacts 命令
            elif args.command == 'contacts':
                if args.contacts_cmd == 'list':
                    # 获取本地 bots
                    bots = client.list_bots()
                    # 获取好友列表
                    friends_res = client.get_friends()
                    friends = friends_res.get("friends", []) if friends_res.get("success") else []
                    friend_ids = {f.get("instance_id", "") for f in friends}

                    # 获取远程 bots（用于获取好友 bot 的详细信息）
                    remote_res = client.discover_remote_bots()
                    remote_bots = []
                    if remote_res.get("success"):
                        all_bots = remote_res.get("bots", [])
                        remote_bots = [b for b in all_bots if b.get("type") == "remote"]

                    rows = []
                    # 本地 bots
                    for b in bots:
                        rows.append([b["id"], b.get("name", ""), "本地", b.get("bio", "")[:40]])

                    # 远程好友 bots
                    for rb in remote_bots:
                        inst_id = rb.get("instance_id", "")
                        if inst_id in friend_ids:
                            bot_id = rb.get("id", "")
                            name = rb.get("name", "")
                            instance = rb.get("instance_name", inst_id)
                            rows.append([bot_id, name, f"好友 · {instance}", rb.get("description", "")[:40]])

                    print_table(["ID", "名称", "类型", "简介"], rows)
                    local_count = len(bots)
                    friend_count = len([r for r in rows if r[2].startswith("好友")])
                    print(f"\n共 {len(rows)} 个联系人（本地 {local_count}，好友 {friend_count}）")

            # Remote 命令
            elif args.command == 'remote':
                if args.remote_cmd == 'bots':
                    # remote bots 子命令
                    if args.remote_bots_cmd == 'list':
                        res = client.discover_remote_bots()
                        if res.get("success"):
                            all_bots = res.get("bots", [])
                            # 过滤出只有远程类型的bot
                            remote_bots = [b for b in all_bots if b.get("type") == "remote"]

                            if not remote_bots:
                                print("未发现远程 Bot")
                            else:
                                rows = [[
                                    b.get("instance_id", ""),
                                    b.get("id", "").split(":")[-1] if ":" in b.get("id", "") else b.get("id", ""),
                                    b.get("name", ""),
                                    b.get("status", "unknown"),
                                    "是" if b.get("is_friend") else "否"
                                ] for b in remote_bots]
                                print_table(["实例", "Bot ID", "名称", "状态", "好友"], rows)
                                print(f"\n共 {len(remote_bots)} 个远程 Bot")
                        else:
                            print(f"发现失败: {res.get('error')}")

                    elif args.remote_bots_cmd == 'publish':
                        res = client.publish_bot(
                            args.bot_id,
                            display_name=args.display_name or args.bot_id,
                            description=getattr(args, 'description', ''),
                            capabilities=getattr(args, 'capabilities', []) or [],
                            is_sandboxed=not getattr(args, 'no_sandbox', False),
                            requires_fs_access=getattr(args, 'require_fs', False)
                        )
                        if res.get("success"):
                            print(f"✓ 已发布 Bot: {args.bot_id}")
                        else:
                            print(f"✗ 发布失败: {res.get('error')}")

                    elif args.remote_bots_cmd == 'unpublish':
                        res = client.unpublish_bot(args.bot_id)
                        if res.get("success"):
                            print(f"✓ 已取消发布: {args.bot_id}")
                        else:
                            print(f"✗ 取消发布失败: {res.get('error')}")

                    elif args.remote_bots_cmd == 'published':
                        res = client.get_published_bots()
                        if res.get("success"):
                            bots = res.get("published_bots", [])
                            if not bots:
                                print("未发布任何 Bot")
                            else:
                                rows = [[
                                    b["bot_id"],
                                    b.get("display_name", ""),
                                    b.get("description", "")[:50],
                                    "启用" if b.get("enabled") else "禁用"
                                ] for b in bots]
                                print_table(["Bot ID", "名称", "描述", "状态"], rows)
                                print(f"\n共 {len(bots)} 个已发布 Bot")
                        else:
                            print(f"获取失败: {res.get('error')}")

                    elif args.remote_bots_cmd == 'add':
                        remote_bot_id = args.remote_bot_id
                        if ':' not in remote_bot_id:
                            print("错误: 远程 Bot ID 格式应为 instance_id:bot_id")
                            sys.exit(1)

                        instance_id, bot_id = remote_bot_id.split(':', 1)
                        res = client.add_remote_bot(instance_id, bot_id)
                        if res.get("success"):
                            print(f"✓ 已添加远程 Bot: {remote_bot_id}")
                        else:
                            print(f"✗ 添加失败: {res.get('error')}")

                    elif args.remote_bots_cmd == 'added':
                        # 获取所有远程bot，然后过滤已添加的
                        res = client.discover_remote_bots()
                        if res.get("success"):
                            all_bots = res.get("bots", [])
                            # 过滤出远程类型且已添加的bot
                            added_bots = [b for b in all_bots
                                        if b.get("type") == "remote" and b.get("is_added", False)]

                            if not added_bots:
                                print("未添加任何远程 Bot")
                            else:
                                rows = [[
                                    b.get("id", ""),
                                    b.get("name", ""),
                                    b.get("description", "")[:50]
                                ] for b in added_bots]
                                print_table(["远程 Bot", "名称", "描述"], rows)
                                print(f"\n共 {len(added_bots)} 个已添加远程 Bot")
                        else:
                            print(f"获取失败: {res.get('error')}")

                    elif args.remote_bots_cmd == 'online':
                        # 获取已发布的本地bot
                        pub_res = client.get_published_bots()
                        published_bots = []
                        if pub_res.get("success"):
                            published_bots = pub_res.get("published_bots", [])

                        # 获取所有远程bot（包括好友和非好友）
                        res = client.discover_remote_bots()
                        remote_bots = []
                        if res.get("success"):
                            all_bots = res.get("bots", [])
                            remote_bots = [b for b in all_bots if b.get("type") == "remote"]

                        rows = []
                        # 本地已发布bots
                        for pb in published_bots:
                            rows.append([
                                pb.get("bot_id", ""),
                                pb.get("display_name", ""),
                                "本地已发布",
                                "启用" if pb.get("enabled") else "禁用",
                                "-"
                            ])

                        # 远程bots（包括好友和非好友）
                        for rb in remote_bots:
                            inst_id = rb.get("instance_id", "")
                            bot_id = rb.get("id", "")
                            name = rb.get("name", "")
                            instance = rb.get("instance_name", inst_id)
                            is_friend = "✓ 好友" if rb.get("is_friend") else "-"
                            rows.append([
                                bot_id,
                                name,
                                f"远程 · {instance}",
                                rb.get("status", "unknown"),
                                is_friend
                            ])

                        if not rows:
                            print("暂无可发现的在线 Bot")
                            print("提示: 发布本地bot或添加远程实例为好友")
                        else:
                            print_table(["Bot ID", "名称", "来源", "状态", "好友"], rows)
                            pub_count = len(published_bots)
                            remote_count = len(remote_bots)
                            friend_count = sum(1 for r in rows if r[4] == "✓ 好友")
                            print(f"\n共 {len(rows)} 个在线 Bot（本地已发布 {pub_count}，远程 {remote_count}，好友 {friend_count}）")

                    elif args.remote_bots_cmd == 'search':
                        keyword = args.keyword.lower()

                        # 获取已发布的本地bot
                        pub_res = client.get_published_bots()
                        published_bots = []
                        if pub_res.get("success"):
                            published_bots = pub_res.get("published_bots", [])

                        # 获取所有远程bot（包括好友和非好友）
                        res = client.discover_remote_bots()
                        remote_bots = []
                        if res.get("success"):
                            all_bots = res.get("bots", [])
                            remote_bots = [b for b in all_bots if b.get("type") == "remote"]

                        rows = []
                        # 本地已发布 bots
                        for pb in published_bots:
                            display = pb.get("display_name", "")
                            bot_id = pb.get("bot_id", "")
                            desc = pb.get("description", "")
                            if keyword in bot_id.lower() or keyword in display.lower() or keyword in desc.lower():
                                rows.append([
                                    bot_id,
                                    display,
                                    "本地已发布",
                                    "启用" if pb.get("enabled") else "禁用",
                                    "-"
                                ])

                        # 远程 bots（包括好友和非好友）
                        for rb in remote_bots:
                            inst_id = rb.get("instance_id", "")
                            bot_id = rb.get("id", "")
                            name = rb.get("name", "")
                            instance = rb.get("instance_name", inst_id)
                            desc = rb.get("description", "")
                            if (keyword in bot_id.lower() or keyword in name.lower()
                                    or keyword in inst_id.lower() or keyword in instance.lower()
                                    or keyword in desc.lower()):
                                is_friend = "✓ 好友" if rb.get("is_friend") else "-"
                                rows.append([
                                    bot_id,
                                    name,
                                    f"远程 · {instance}",
                                    rb.get("status", "unknown"),
                                    is_friend
                                ])

                        if not rows:
                            print(f'未找到匹配 "{args.keyword}" 的在线 Bot')
                        else:
                            print_table(["Bot ID", "名称", "来源", "状态", "好友"], rows)
                            print(f"\n共找到 {len(rows)} 个匹配结果")

                elif args.remote_cmd == 'friends':
                    # remote friends 子命令
                    if args.remote_friends_cmd == 'list':
                        res = client.get_friends()
                        if res.get("success"):
                            friends = res.get("friends", [])
                            if not friends:
                                print("好友列表为空")
                            else:
                                rows = [[
                                    f.get("instance_id", ""),
                                    f.get("instance_name", ""),
                                    f.get("bot_id", ""),
                                    f.get("bot_name", ""),
                                    "在线" if f.get("online") else "离线"
                                ] for f in friends]
                                print_table(["实例 ID", "实例名称", "Bot ID", "Bot 名称", "状态"], rows)
                                print(f"\n共 {len(friends)} 个好友")
                        else:
                            print(f"获取失败: {res.get('error')}")

                    elif args.remote_friends_cmd == 'add':
                        message = getattr(args, 'message', '') or ''
                        to_bot_id = getattr(args, 'bot_id', '') or ''
                        res = client.send_friend_request(args.instance_id, message, to_bot_id)
                        if res.get("success"):
                            req_id = res.get("request_id", "")
                            print(f"✓ 好友请求已发送")
                            print(f"  请求 ID: {req_id}")
                            print(f"  目标实例: {args.instance_id}")
                            if to_bot_id:
                                print(f"  目标 Bot: {to_bot_id}")
                                print(f"\n提示: 请对方使用 'clawdboz remote friends requests' 查看待处理请求")
                            else:
                                print(f"\n⚠️  警告: 未指定 Bot ID，对方实例的所有 Bot 将成为好友")
                                print(f"   建议: clawdboz remote friends add {args.instance_id} --bot-id <bot_id>")
                                print(f"\n提示: 请对方使用 'clawdboz remote friends requests' 查看待处理请求")
                            print(f"       使用 'clawdboz remote friends accept {req_id}' 接受请求")
                        else:
                            print(f"✗ 发送失败: {res.get('error')}")

                    elif args.remote_friends_cmd == 'accept':
                        request_id = args.request_id
                        accept = not getattr(args, 'reject', False)

                        res = client.accept_friend_request(request_id, accept)
                        if res.get("success"):
                            action = "接受" if accept else "拒绝"
                            print(f"✓ 已{action}好友请求: {request_id}")
                        else:
                            print(f"✗ 操作失败: {res.get('error')}")

                    elif args.remote_friends_cmd == 'reject':
                        request_id = args.request_id
                        res = client.accept_friend_request(request_id, accept=False)
                        if res.get("success"):
                            print(f"✓ 已拒绝好友请求: {request_id}")
                        else:
                            print(f"✗ 拒绝失败: {res.get('error')}")

                    elif args.remote_friends_cmd == 'requests':
                        res = client.get_friend_requests()
                        if res.get("success"):
                            friend_requests = res.get("requests", [])
                            if not friend_requests:
                                print("无待处理的好友请求")
                            else:
                                rows = [[
                                    r.get("request_id", ""),
                                    r.get("from_instance", ""),
                                    r.get("to_bot_id", "") or "__all__",
                                    r.get("message", "")[:30],
                                    r.get("created_at", "")
                                ] for r in friend_requests]
                                print_table(["请求 ID", "来自实例", "目标 Bot", "消息", "时间"], rows)
                                print(f"\n共 {len(friend_requests)} 个待处理请求")
                                print(f"\n接受请求: clawdboz remote friends accept <request_id>")
                                print(f"拒绝请求: clawdboz remote friends accept <request_id> --reject")
                        else:
                            print(f"获取失败: {res.get('error')}")

                    elif args.remote_friends_cmd == 'remove':
                        target = args.target
                        explicit_bot_id = getattr(args, 'bot_id', '') or ''

                        # 解析 instance_id:bot_id 格式
                        if ':' in target:
                            instance_id, parsed_bot_id = target.split(':', 1)
                            bot_id = explicit_bot_id or parsed_bot_id
                        else:
                            instance_id = target
                            bot_id = explicit_bot_id

                        res = client.remove_friend(instance_id, bot_id)
                        if res.get("success"):
                            display = f"{instance_id}:{bot_id}" if bot_id else instance_id
                            print(f"✓ 已移除好友: {display}")
                            if not bot_id:
                                print(f"  提示: 移除了整个实例的好友关系（包括所有 Bot）")
                        else:
                            print(f"✗ 移除失败: {res.get('error')}")

                elif args.remote_cmd == 'bot-friends':
                    bot_id = getattr(args, 'bot_id', '') or ''
                    if bot_id:
                        # 查询指定 bot
                        res = client.get_bot_friends(bot_id)
                        if res.get("success"):
                            friends = res.get("friends", [])
                            if not friends:
                                print(f'Bot "{bot_id}" 还没有被任何实例添加为好友')
                            else:
                                rows = [[
                                    f.get("instance_id", ""),
                                    f.get("instance_name", ""),
                                    f.get("added_at", "")
                                ] for f in friends]
                                print_table(["实例 ID", "实例名称", "添加时间"], rows)
                                print(f"\n共 {len(friends)} 个实例添加了 Bot '{bot_id}'")
                        else:
                            print(f"查询失败: {res.get('error')}")
                    else:
                        # 查询所有已发布 bot
                        res = client.get_published_bots()
                        if res.get("success"):
                            bots = res.get("published_bots", [])
                            if not bots:
                                print("没有已发布的本地 Bot")
                            else:
                                print("已发布 Bot 的好友情况：\n")
                                for bot in bots:
                                    bid = bot.get("bot_id", "")
                                    bname = bot.get("display_name", bid)
                                    bf_res = client.get_bot_friends(bid)
                                    friends = bf_res.get("friends", []) if bf_res.get("success") else []
                                    friend_count = len(friends)
                                    if friends:
                                        print(f"  📌 {bname} ({bid}) - {friend_count} 个好友")
                                        for f in friends:
                                            print(f"     └─ {f.get('instance_name', f.get('instance_id', ''))}")
                                    else:
                                        print(f"  📌 {bname} ({bid}) - 暂无好友")
                                print(f"\n共 {len(bots)} 个已发布 Bot")
                        else:
                            print(f"获取 Bot 列表失败: {res.get('error')}")

            # Moments 命令
            elif args.command == 'moments':
                if args.moments_cmd == 'list':
                    res = client.list_moments(args.limit, args.offset)
                    moments = res.get("moments", [])
                    total = res.get("total", 0)
                    for m in moments:
                        sender = m.get("sender", {})
                        name = sender.get("name", "未知")
                        print(f"\n[{name}] {format_time(m.get('created_at'))}")
                        print(f"  {m.get('content', '')}")
                        likes = m.get("likes", [])
                        if likes:
                            like_names = [l.get("sender_name", l) if isinstance(l, dict) else l for l in likes]
                            print(f"  ❤ {len(likes)} ({', '.join(like_names)})")
                        comments = m.get("comments", [])
                        for c in comments:
                            cname = c.get("sender", {}).get("name", "未知")
                            print(f"  💬 [{cname}]: {c.get('content', '')}")
                    print(f"\n显示 {len(moments)}/{total} 条")

                elif args.moments_cmd == 'post':
                    res = client.post_moment(args.content)
                    print("发布成功" if res.get("success") else f"发布失败: {res.get('error')}")

                elif args.moments_cmd == 'like':
                    res = client.like_moment(args.moment_id)
                    status = "点赞" if res.get("liked") else "取消点赞"
                    print(f"{status}成功，当前 {res.get('likes_count', 0)} 个赞")

                elif args.moments_cmd == 'comment':
                    res = client.comment_moment(args.moment_id, args.content)
                    print("评论成功" if res.get("success") else f"评论失败: {res.get('error')}")

            # Profile 命令
            elif args.command == 'profile':
                if args.profile_cmd == 'show':
                    res = client.get_profile()
                    print(f"名称: {res.get('name', '')}")
                    print(f"简介: {res.get('bio', '')}")
                    print(f"头像: {res.get('avatar_icon', '')} ({res.get('avatar_color', '')})")

                elif args.profile_cmd == 'update':
                    res = client.update_profile(args.name, args.bio)
                    print("更新成功" if res.get("success") else f"更新失败: {res.get('error')}")

        except requests.exceptions.ConnectionError:
            print(f"错误: 无法连接到服务器 {client.base_url}")
            print("请确保 Web 服务器正在运行: clawdboz run")
            sys.exit(1)
        except requests.exceptions.HTTPError as e:
            print(f"HTTP 错误: {e}")
            try:
                print(e.response.json().get("error", e.response.text))
            except Exception:
                print(e.response.text)
            sys.exit(1)
        except Exception as e:
            print(f"错误: {e}")
            sys.exit(1)

    else:
        parser.print_help()


if __name__ == '__main__':
    main()
