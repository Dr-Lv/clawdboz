"""
Docker 共享容器沙箱管理器
所有发布的沙箱 bot 共享一个 Docker 容器
根据 ACP 配置自动挂载所需目录和凭证
"""
import os
import json
import time
import asyncio
import subprocess
import hashlib
from typing import Dict, Optional, Any, List, Tuple
from dataclasses import dataclass, field

import aiohttp


@dataclass
class DockerSandboxConfig:
    """Docker 沙箱配置"""
    image: str = "python:3.11-slim"
    memory_limit: str = "512m"
    cpu_quota: int = 100000
    cpu_period: int = 100000
    network_disabled: bool = False
    timeout_seconds: int = 120
    container_name: str = "clawdboz-sandbox"
    host_port: int = 18443
    container_port: int = 18443
    host_api_url: str = "http://host.docker.internal:8443"
    host_api_token: str = "clawdboz-test-2024"


class DockerSandboxManager:
    """Docker 共享容器沙箱管理器 — 支持根据 ACP 配置自动挂载"""

    # 安全目录：挂载这些目录中的 executable 时只挂载文件本身，避免覆盖系统目录
    _SAFE_BIN_DIRS = {"/usr/bin", "/usr/local/bin", "/bin", "/sbin"}

    # 已知 provider 的默认凭证路径（相对于 $HOME）
    _CREDENTIAL_PATHS = {
        "kimi": [".kimi"],
        "claude": [".claude.json", ".claude", ".config/claude"],
        "claudecode": [".claude.json", ".claude", ".config/claude"],
        "opencode": [".config/opencode", ".opencode"],
    }

    def __init__(self, config: Optional[DockerSandboxConfig] = None):
        """
        初始化 Docker 沙箱管理器

        Args:
            config: Docker 沙箱配置
        """
        self.config = config or DockerSandboxConfig()
        self.container_id: Optional[str] = None
        self._docker_available = self._check_docker()
        # 当前容器生效的挂载签名，用于检测 ACP 配置变化
        self._container_mount_signature: Optional[str] = None
        # 待应用的挂载配置（由 execute_bot 设置）
        self._pending_mounts: List[Tuple[str, str, str]] = []
        self._pending_env: Dict[str, str] = {}
        self._pending_path_entries: List[str] = []

        if not self._docker_available:
            print("[DockerSandbox] Docker 不可用，沙箱功能将禁用")
        else:
            # 检查镜像是否存在，不存在则尝试从包内导入
            if not self._check_image_exists():
                print(f"[DockerSandbox] 镜像 {self.config.image} 不存在，尝试从包内导入...")
                self._import_image()
            else:
                print(f"[DockerSandbox] 镜像 {self.config.image} 已存在")

    def _check_docker(self) -> bool:
        """检查 Docker daemon 是否实际可用"""
        try:
            # 先检查 docker CLI 是否存在
            result = subprocess.run(
                ["docker", "--version"],
                capture_output=True, text=True, timeout=5
            )
            if result.returncode != 0:
                return False
            # 再检查 daemon 是否可连接
            result = subprocess.run(
                ["docker", "info"],
                capture_output=True, text=True, timeout=5
            )
            return result.returncode == 0
        except Exception as e:
            print(f"[DockerSandbox] Docker check failed: {e}")
            return False

    def _import_image(self) -> bool:
        """从包内 tar 文件导入 Docker 镜像"""
        import os
        import importlib.util
        import inspect

        try:
            # 找到包内 tar 文件路径
            current_file = inspect.getfile(self.__class__)
            tar_path = os.path.join(os.path.dirname(current_file), "docker-images", "python-3.11-slim.tar")

            if not os.path.exists(tar_path):
                print(f"[DockerSandbox] 包内镜像文件不存在: {tar_path}")
                return False

            print(f"[DockerSandbox] 正在从包内导入镜像: {tar_path}")
            result = subprocess.run(
                ["docker", "load", "-i", tar_path],
                capture_output=True, text=True, timeout=300
            )
            if result.returncode == 0:
                print("[DockerSandbox] 镜像导入成功")
                return True
            else:
                print(f"[DockerSandbox] 镜像导入失败: {result.stderr}")
                return False
        except Exception as e:
            print(f"[DockerSandbox] 镜像导入异常: {e}")
            return False

    def _check_image_exists(self) -> bool:
        """检查镜像是否已存在"""
        try:
            result = subprocess.run(
                ["docker", "images", "--format", "{{.Repository}}:{{.Tag}}"],
                capture_output=True, text=True, timeout=10
            )
            images = result.stdout.strip().split("\n")
            return self.config.image in images
        except Exception as e:
            print(f"[DockerSandbox] 检查镜像存在性失败: {e}")
            return False

    # ------------------------------------------------------------------
    # 自动挂载解析
    # ------------------------------------------------------------------
    @staticmethod
    def resolve_acp_mounts(acp_config: dict) -> Tuple[List[Tuple[str, str, str]], Dict[str, str], List[str]]:
        """
        根据 ACP 配置自动解析需要挂载的目录、环境变量和 PATH 条目。

        Returns:
            (mounts, env_vars, path_entries)
            mounts: [(host_path, container_path, mode), ...]
            env_vars: {key: value}
            path_entries: [dir1, dir2, ...]
        """
        mounts: List[Tuple[str, str, str]] = []
        env_vars: Dict[str, str] = {}
        path_entries: List[str] = []
        seen = set()  # 避免重复挂载

        def add_mount(host_path: str, container_path: str, mode: str = "ro") -> None:
            """去重添加挂载"""
            abs_host = os.path.abspath(os.path.expanduser(host_path))
            abs_container = os.path.expanduser(container_path)
            key = (abs_host, abs_container)
            if key in seen:
                return
            seen.add(key)
            if os.path.exists(abs_host):
                mounts.append((abs_host, abs_container, mode))

        def add_path(p: str) -> None:
            """添加 PATH 条目"""
            if p and p not in path_entries:
                path_entries.append(p)

        # ---------- 1. 提取 provider / executable ----------
        clients = acp_config.get("clients", [])
        provider = acp_config.get("provider", "kimi")
        executable = ""

        if clients:
            client_config = clients[0]
            provider = client_config.get("type", provider)
            executable = client_config.get("executable", "")
        else:
            executables = acp_config.get("executables", {})
            executable = executables.get(provider, "")
            if not executable:
                executable = acp_config.get("executable", "")

        # 兜底：根据 provider 推断默认命令名
        if not executable:
            provider_lower = provider.lower()
            if provider_lower == "kimi":
                executable = "kimi"
            elif provider_lower in ("claude", "claudecode"):
                executable = "claude"
            elif provider_lower == "opencode":
                executable = "opencode"
            else:
                executable = provider_lower

        # ---------- 2. Executable 路径挂载 ----------
        exec_path = None
        if executable.startswith("/"):
            exec_path = os.path.expanduser(executable)
        else:
            # 在 $PATH 中查找
            for d in os.environ.get("PATH", "").split(":"):
                candidate = os.path.join(d, executable)
                if os.path.isfile(candidate):
                    exec_path = candidate
                    break

        if exec_path and os.path.exists(exec_path):
            exec_dir = os.path.dirname(exec_path)
            if exec_dir in DockerSandboxManager._SAFE_BIN_DIRS:
                # 只挂载可执行文件本身，避免覆盖系统目录（如 /usr/local/bin 中的 python）
                add_mount(exec_path, exec_path, "ro")
            else:
                add_mount(exec_dir, exec_dir, "ro")
            add_path(exec_dir)

            # 如果是 wrapper 脚本，解析其中引用的其他绝对路径
            if os.path.getsize(exec_path) < 1024 * 1024:  # 只解析小于 1MB 的文件
                try:
                    with open(exec_path, "r", encoding="utf-8", errors="ignore") as f:
                        content = f.read()
                    import re
                    # 匹配常见绝对路径（至少两级目录）
                    for match in re.finditer(r"/[\w/._-]+", content):
                        ref = match.group()
                        if os.path.isdir(ref):
                            add_mount(ref, ref, "ro")
                        elif os.path.isfile(ref):
                            add_mount(os.path.dirname(ref), os.path.dirname(ref), "ro")
                except Exception:
                    pass

            # 对于 npm global 包，executable 通常在 .npm-global/bin/claude
            # 需要同时挂载 lib/node_modules（依赖关系）
            if ".npm-global/bin" in exec_path:
                npm_global = exec_path.split(".npm-global/bin")[0] + ".npm-global"
                if os.path.isdir(npm_global):
                    add_mount(npm_global, npm_global, "ro")

            # 对于 uv 工具链，如果 executable 在 .local/bin 且引用 uv/tools，则已在上面的
            # wrapper 脚本解析中处理。额外检测：如果 executable 是 symlink 到 uv/tools 内部
            if os.path.islink(exec_path):
                try:
                    target = os.readlink(exec_path)
                    if not target.startswith("/"):
                        target = os.path.normpath(os.path.join(exec_dir, target))
                    target_dir = os.path.dirname(target)
                    if os.path.isdir(target_dir):
                        add_mount(target_dir, target_dir, "ro")
                except Exception:
                    pass
        else:
            # executable 找不到，但至少把 PATH 中的常用目录加进去
            add_path("/usr/local/bin")
            add_path("/usr/bin")

        # ---------- 3. 解析 executable 的 shebang，挂载完整虚拟环境 ----------
        if exec_path and os.path.exists(exec_path):
            try:
                with open(exec_path, "r", encoding="utf-8", errors="ignore") as f:
                    first_line = f.readline().strip()
                if first_line.startswith("#!/") and "python" in first_line.lower():
                    shebang_python = first_line[2:].strip().split()[0]
                    if os.path.exists(shebang_python):
                        # 向上两级：bin/python -> 虚拟环境根目录
                        venv_dir = os.path.dirname(os.path.dirname(shebang_python))
                        if os.path.isfile(os.path.join(venv_dir, "pyvenv.cfg")):
                            add_mount(venv_dir, venv_dir, "ro")
            except Exception:
                pass

        # ---------- 4. Provider 额外运行时依赖（启发式） ----------
        provider_lower = provider.lower()
        if provider_lower == "kimi":
            # 如果存在 Python 3.13 运行时（uv 安装的典型位置），一并挂载
            uv_python_candidates = [
                "/root/.local/share/uv/python/cpython-3.13.12-linux-x86_64-gnu",
                "/root/.local/share/uv/python/cpython-3.13.11-linux-x86_64-gnu",
                "/root/.local/share/uv/python/cpython-3.13.10-linux-x86_64-gnu",
                "/root/.local/share/uv/python/cpython-3.13-linux-x86_64-gnu",
            ]
            for cand in uv_python_candidates:
                if os.path.isdir(cand):
                    add_mount(cand, cand, "ro")
                    break
        elif provider_lower in ("claude", "claudecode"):
            # Node.js 运行时：尝试挂载宿主机的 node
            for node_path in ["/usr/bin/node", "/usr/local/bin/node"]:
                if os.path.isfile(node_path):
                    add_mount(node_path, node_path, "ro")
                    add_path(os.path.dirname(node_path))
                    break

            # claude-code-acp 适配器：挂载可执行文件（仅 provider 为 claude 时）
            if provider_lower == "claude":
                cca_found = False
                for cca_path in ["/usr/local/bin/claude-code-acp", "/usr/bin/claude-code-acp"]:
                    if os.path.isfile(cca_path):
                        add_mount(cca_path, cca_path, "ro")
                        add_path(os.path.dirname(cca_path))
                        cca_found = True
                        break
                if not cca_found:
                    # 在 PATH 中查找
                    for d in os.environ.get("PATH", "").split(":"):
                        cca_candidate = os.path.join(d, "claude-code-acp")
                        if os.path.isfile(cca_candidate):
                            add_mount(cca_candidate, cca_candidate, "ro")
                            add_path(d)
                            cca_found = True
                            break
                if not cca_found:
                    # 如果找不到命令，至少确保 python -m claude_code_acp 可用
                    # clawdboz 和 claude-code-acp 已经在 site-packages 中
                    print(f"[DockerSandbox] 警告: 未找到 claude-code-acp 命令，将依赖 python -m claude_code_acp")

        # ---------- 4. 凭证挂载 ----------
        home = os.path.expanduser("~")
        cred_rels = DockerSandboxManager._CREDENTIAL_PATHS.get(provider_lower, [f".{provider_lower}", f".config/{provider_lower}"])
        for rel in cred_rels:
            host_cand = os.path.join(home, rel)
            if os.path.exists(host_cand):
                add_mount(host_cand, host_cand, "rw")

        # ---------- 5. 环境变量（用户自定义） ----------
        custom_env = acp_config.get("env", {})
        if isinstance(custom_env, dict):
            env_vars.update(custom_env)

        return mounts, env_vars, path_entries

    @staticmethod
    def _make_mount_signature(mounts, env_vars, path_entries) -> str:
        """生成挂载配置的唯一签名"""
        parts = []
        for m in sorted(mounts, key=lambda x: x[0]):
            parts.append(f"{m[0]}:{m[1]}:{m[2]}")
        for k in sorted(env_vars.keys()):
            parts.append(f"env:{k}={env_vars[k]}")
        for p in sorted(path_entries):
            parts.append(f"path:{p}")
        return hashlib.sha256("|".join(parts).encode()).hexdigest()[:16]

    # ------------------------------------------------------------------
    # 容器生命周期
    # ------------------------------------------------------------------
    async def ensure_container(self, acp_config: Optional[dict] = None) -> Optional[str]:
        """
        确保沙箱容器正在运行，且挂载配置与当前 ACP 设置匹配。

        Args:
            acp_config: 当前 Bot 的 ACP 配置，用于动态挂载

        Returns:
            容器 ID 或 None
        """
        if not self._docker_available:
            return None

        # 解析 ACP 挂载需求
        if acp_config:
            mounts, env_vars, path_entries = self.resolve_acp_mounts(acp_config)
            self._pending_mounts = mounts
            self._pending_env = env_vars
            self._pending_path_entries = path_entries
            new_signature = self._make_mount_signature(mounts, env_vars, path_entries)
        else:
            new_signature = self._container_mount_signature or ""

        # 检查现有容器
        running = await self._is_container_running()

        if running:
            # 如果挂载签名不匹配，需要重建容器
            # 注意：签名可能为 None（首次创建）或 ""（空配置），都要能正确检测变化
            current_sig = self._container_mount_signature or ""
            if current_sig != new_signature:
                print(f"[DockerSandbox] ACP 配置变化，重建容器 (签名: {current_sig} -> {new_signature})")
                await self.destroy()
                await self._remove_stopped_container()
            else:
                return self.container_id

        # 移除已停止的同名容器
        await self._remove_stopped_container()

        # 创建新容器
        self._container_mount_signature = new_signature
        return await self._create_container()

    async def _is_container_running(self) -> bool:
        """检查容器是否在运行"""
        if not self.container_id:
            # 尝试通过名称查找
            try:
                result = await asyncio.create_subprocess_exec(
                    "docker", "inspect", "-f", "{{.Id}}", self.config.container_name,
                    stdout=asyncio.subprocess.PIPE,
                    stderr=asyncio.subprocess.PIPE
                )
                stdout, _ = await asyncio.wait_for(result.communicate(), timeout=5)
                if result.returncode == 0:
                    self.container_id = stdout.decode().strip()
                else:
                    return False
            except Exception:
                return False

        # 检查容器状态
        try:
            result = await asyncio.create_subprocess_exec(
                "docker", "inspect", "-f", "{{.State.Running}}", self.container_id,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )
            stdout, _ = await asyncio.wait_for(result.communicate(), timeout=5)
            if result.returncode == 0:
                return stdout.decode().strip() == "true"
        except Exception:
            pass

        self.container_id = None
        return False

    async def _remove_stopped_container(self):
        """移除已停止的同名容器"""
        try:
            result = await asyncio.create_subprocess_exec(
                "docker", "rm", "-f", self.config.container_name,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await asyncio.wait_for(result.communicate(), timeout=10)
        except Exception:
            pass

    async def _create_container(self) -> Optional[str]:
        """创建新的沙箱容器，使用动态挂载配置"""
        try:
            # 获取项目根目录（当前工作目录）
            project_root = os.getcwd()
            workplace_dir = os.path.join(project_root, "WORKPLACE")

            # 查找主机虚拟环境的 site-packages 路径
            import sys
            host_site_packages = None
            for p in sys.path:
                if 'site-packages' in p and os.path.isdir(p) and 'clawdboz' in os.listdir(p):
                    host_site_packages = p
                    break
            if not host_site_packages:
                for p in sys.path:
                    if 'site-packages' in p and os.path.isdir(p):
                        host_site_packages = p
                        break

            # 构建 Docker 命令基础部分
            cmd = [
                "docker", "run", "-d",
                "--name", self.config.container_name,
                "--memory", self.config.memory_limit,
                "--cpu-quota", str(self.config.cpu_quota),
                "--cpu-period", str(self.config.cpu_period),
                "-p", f"{self.config.host_port}:{self.config.container_port}",
                "-v", f"{project_root}:/app:ro",
                "-v", f"{workplace_dir}:/workplace:rw",
                "-e", "CLAWDBOZ_SANDBOX_MODE=1",
                "-e", f"CLAWDBOZ_HOST_API={self.config.host_api_url}",
                "-e", f"CLAWDBOZ_HOST_TOKEN={self.config.host_api_token}",
                "-w", "/app",
            ]

            # 挂载主机 site-packages
            if host_site_packages and os.path.isdir(host_site_packages):
                cmd.extend(["-v", f"{host_site_packages}:/host-site-packages:ro"])
                print(f"[DockerSandbox] 挂载 site-packages: {host_site_packages} -> /host-site-packages")
            else:
                print(f"[DockerSandbox] 警告: 未找到主机 site-packages")

            # ---------- 动态 ACP 挂载 ----------
            mounts = getattr(self, '_pending_mounts', [])
            env_vars = getattr(self, '_pending_env', {})
            path_entries = getattr(self, '_pending_path_entries', [])

            # 默认 PATH
            default_path = "/usr/local/bin:/usr/bin:/bin"
            all_paths = list(path_entries) + default_path.split(":")
            # 去重并保持顺序
            dedup_paths = []
            for p in all_paths:
                if p and p not in dedup_paths:
                    dedup_paths.append(p)

            for host_path, container_path, mode in mounts:
                print(f"[DockerSandbox] 挂载: {host_path} -> {container_path} ({mode})")
                cmd.extend(["-v", f"{host_path}:{container_path}:{mode}"])

            # 环境变量
            path_env = ":".join(dedup_paths)
            cmd.extend(["-e", f"PATH={path_env}"])

            for k, v in env_vars.items():
                cmd.extend(["-e", f"{k}={v}"])

            # 网络配置
            if self.config.network_disabled:
                cmd.append("--network=none")

            # 镜像和启动命令
            cmd.extend([
                self.config.image,
                "sh", "-c",
                f"/usr/local/bin/python /host-site-packages/clawdboz/remote/sandbox_server.py --port {self.config.container_port} > /tmp/sandbox_server.log 2>&1"
            ])

            print(f"[DockerSandbox] 创建容器: {self.config.container_name}")
            print(f"[DockerSandbox] 端口映射: {self.config.host_port}:{self.config.container_port}")

            result = await asyncio.create_subprocess_exec(
                *cmd,
                stdout=asyncio.subprocess.PIPE,
                stderr=asyncio.subprocess.PIPE
            )

            stdout, stderr = await asyncio.wait_for(result.communicate(), timeout=30)

            if result.returncode != 0:
                print(f"[DockerSandbox] 创建容器失败: {stderr.decode()}")
                return None

            self.container_id = stdout.decode().strip()
            print(f"[DockerSandbox] 容器创建成功: {self.container_id[:12]}")

            # 等待服务启动
            await asyncio.sleep(2)

            # 验证健康状态
            if await self._health_check():
                print(f"[DockerSandbox] 沙箱服务就绪")
            else:
                print(f"[DockerSandbox] 警告: 健康检查未通过，查看容器日志...")
                try:
                    result = subprocess.run(
                        ["docker", "logs", self.config.container_name],
                        capture_output=True, text=True, timeout=5
                    )
                    if result.stdout:
                        print(f"[DockerSandbox] 容器日志: {result.stdout[-500:]}")
                    if result.stderr:
                        print(f"[DockerSandbox] 容器错误: {result.stderr[-500:]}")
                except Exception as e:
                    print(f"[DockerSandbox] 无法获取容器日志: {e}")

            return self.container_id

        except Exception as e:
            print(f"[DockerSandbox] 创建容器异常: {e}")
            import traceback
            traceback.print_exc()
            return None

    async def _health_check(self) -> bool:
        """健康检查"""
        try:
            url = f"http://localhost:{self.config.host_port}/health"
            timeout = aiohttp.ClientTimeout(total=5)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.get(url) as resp:
                    data = await resp.json()
                    return data.get("status") == "ok"
        except Exception as e:
            print(f"[DockerSandbox] 健康检查失败: {e}")
            return False

    async def register_bot(self, bot_id: str, config: dict, acp_config: dict) -> bool:
        """
        向沙箱容器注册 bot

        Args:
            bot_id: Bot ID
            config: Bot 配置
            acp_config: ACP 配置

        Returns:
            是否成功
        """
        if not await self.ensure_container(acp_config=acp_config):
            return False

        try:
            url = f"http://localhost:{self.config.host_port}/register"
            payload = {
                "bot_id": bot_id,
                "config": config,
                "acp_config": acp_config
            }
            timeout = aiohttp.ClientTimeout(total=10)
            async with aiohttp.ClientSession(timeout=timeout) as session:
                async with session.post(url, json=payload) as resp:
                    result = await resp.json()
                    if result.get("success"):
                        print(f"[DockerSandbox] Bot '{bot_id}' 已注册到沙箱")
                        return True
                    else:
                        print(f"[DockerSandbox] 注册失败: {result.get('error')}")
                        return False

        except Exception as e:
            print(f"[DockerSandbox] 注册 Bot 失败: {e}")
            return False

    async def execute_bot(
        self,
        bot_id: str,
        method: str = "chat",
        params: Optional[dict] = None,
        timeout: int = 120,
        acp_config: Optional[dict] = None
    ) -> dict:
        """
        在沙箱容器中执行 bot 调用

        Args:
            bot_id: Bot ID
            method: 调用方法
            params: 参数
            timeout: 超时时间
            acp_config: Bot 的 ACP 配置，用于动态挂载

        Returns:
            执行结果
        """
        if not await self.ensure_container(acp_config=acp_config):
            return {"success": False, "error": "Sandbox container not available"}

        try:
            url = f"http://localhost:{self.config.host_port}/execute"
            payload = {
                "bot_id": bot_id,
                "method": method,
                "params": params or {},
                "timeout": timeout
            }
            client_timeout = aiohttp.ClientTimeout(total=timeout + 10)
            async with aiohttp.ClientSession(timeout=client_timeout) as session:
                async with session.post(url, json=payload) as resp:
                    return await resp.json()

        except Exception as e:
            error_msg = f"Sandbox execution failed: {str(e)}"
            print(f"[DockerSandbox] {error_msg}")
            return {"success": False, "error": error_msg}

    async def destroy(self):
        """销毁沙箱容器"""
        if not self.container_id:
            return

        try:
            print(f"[DockerSandbox] 销毁容器: {self.container_id[:12]}")
            result = await asyncio.create_subprocess_exec(
                "docker", "rm", "-f", self.container_id,
                stdout=asyncio.subprocess.DEVNULL,
                stderr=asyncio.subprocess.DEVNULL
            )
            await asyncio.wait_for(result.communicate(), timeout=10)
            self.container_id = None
            self._container_mount_signature = None
            print("[DockerSandbox] 容器已销毁")
        except Exception as e:
            print(f"[DockerSandbox] 销毁容器失败: {e}")

    def is_available(self) -> bool:
        """沙箱是否可用"""
        return self._docker_available


# 兼容性：保留旧的 API 但内部委托给新的共享容器管理
class DockerSandboxManagerOld(DockerSandboxManager):
    """旧 API 兼容包装"""
    pass
