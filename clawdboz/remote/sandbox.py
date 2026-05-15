"""
沙箱执行器
在隔离的进程中执行 Bot 调用，提供资源限制和超时控制
"""
import os
import sys
import time
import multiprocessing
import signal
import traceback
from typing import Dict, Optional, Any
from dataclasses import dataclass
from pathlib import Path
import json


@dataclass
class SandboxConfig:
    """沙箱配置"""
    max_memory_mb: int = 512  # 最大内存（MB）
    max_cpu_cores: float = 1.0  # 最大 CPU 核心数
    max_disk_mb: int = 500  # 最大磁盘使用（MB）
    timeout_seconds: int = 120  # 默认超时时间（秒）
    cache_timeout_seconds: int = 600  # 沙箱缓存超时（秒，10分钟）


@dataclass
class FileSystemConfig:
    """文件系统配置"""
    api_url: str  # 文件访问 API URL
    token: str  # 认证 Token
    chat_id: str  # 会话 ID


class SandboxExecutor:
    """沙箱执行器"""

    def __init__(self, config: Optional[SandboxConfig] = None):
        """
        初始化沙箱执行器

        Args:
            config: 沙箱配置
        """
        self.config = config or SandboxConfig()

        # 沙箱缓存 {bot_id: (process, last_used_time)}
        self._sandbox_cache: Dict[str, tuple] = {}

        # 清理任务
        self._cleanup_task: Optional[multiprocessing.Process] = None

    def execute_bot_call(
        self,
        bot_id: str,
        method: str,
        params: Dict[str, Any],
        fs_config: Optional[FileSystemConfig] = None,
        timeout: Optional[int] = None
    ) -> Dict[str, Any]:
        """
        在沙箱中执行 Bot 调用

        Args:
            bot_id: Bot ID
            method: 调用方法
            params: 参数
            fs_config: 文件系统配置
            timeout: 超时时间（秒），默认使用 config.timeout_seconds

        Returns:
            执行结果 {"success": bool, "result": Any, "error": str}
        """
        timeout = timeout or self.config.timeout_seconds

        # 检查缓存中是否有可用的沙箱
        process, last_used = self._sandbox_cache.get(bot_id, (None, 0))

        # 如果沙箱超时，销毁并重新创建
        if process and (time.time() - last_used) > self.config.cache_timeout_seconds:
            print(f"[Sandbox] Bot '{bot_id}' 沙箱已超时，重新创建")
            self._destroy_sandbox(bot_id)
            process = None

        # 如果没有可用的沙箱，创建新的
        if not process:
            process = self._create_sandbox(bot_id)
            if not process:
                return {
                    "success": False,
                    "error": "Failed to create sandbox"
                }

        # 执行调用
        try:
            result = self._execute_in_sandbox(
                process,
                bot_id,
                method,
                params,
                fs_config,
                timeout
            )

            # 更新最后使用时间
            self._sandbox_cache[bot_id] = (process, time.time())

            return result

        except Exception as e:
            error_msg = f"Sandbox execution error: {str(e)}"
            print(f"[Sandbox] {error_msg}")
            traceback.print_exc()

            return {
                "success": False,
                "error": error_msg
            }

    def _create_sandbox(self, bot_id: str) -> Optional[multiprocessing.Process]:
        """
        创建新的沙箱进程

        Args:
            bot_id: Bot ID

        Returns:
            沙箱进程或 None
        """
        try:
            # 创建进程间通信队列
            request_queue = multiprocessing.Queue()
            response_queue = multiprocessing.Queue()

            # 创建沙箱进程
            process = multiprocessing.Process(
                target=_sandbox_worker,
                args=(
                    bot_id,
                    request_queue,
                    response_queue,
                    self.config
                )
            )

            process.start()

            # 等待沙箱初始化
            try:
                init_msg = response_queue.get(timeout=10)
                if init_msg.get("status") == "ready":
                    print(f"[Sandbox] Bot '{bot_id}' 沙箱创建成功")

                    # 存储队列引用
                    self._sandbox_cache[bot_id] = (
                        (process, request_queue, response_queue),
                        time.time()
                    )

                    return (process, request_queue, response_queue)
                else:
                    print(f"[Sandbox] Bot '{bot_id}' 沙箱初始化失败: {init_msg}")
                    process.terminate()
                    return None

            except Exception as e:
                print(f"[Sandbox] Bot '{bot_id}' 沙箱初始化超时: {e}")
                process.terminate()
                return None

        except Exception as e:
            print(f"[Sandbox] 创建沙箱失败: {e}")
            traceback.print_exc()
            return None

    def _execute_in_sandbox(
        self,
        sandbox: tuple,
        bot_id: str,
        method: str,
        params: Dict[str, Any],
        fs_config: Optional[FileSystemConfig],
        timeout: int
    ) -> Dict[str, Any]:
        """
        在沙箱中执行调用

        Args:
            sandbox: 沙箱元组 (process, request_queue, response_queue)
            bot_id: Bot ID
            method: 调用方法
            params: 参数
            fs_config: 文件系统配置
            timeout: 超时时间

        Returns:
            执行结果
        """
        process, request_queue, response_queue = sandbox

        # 构建请求
        request = {
            "action": "execute",
            "method": method,
            "params": params,
            "fs_config": fs_config.__dict__ if fs_config else None
        }

        # 发送请求
        request_queue.put(request)

        # 等待响应
        try:
            response = response_queue.get(timeout=timeout)
            return response

        except Exception as e:
            # 超时或错误，终止沙箱
            print(f"[Sandbox] Bot '{bot_id}' 执行超时或错误: {e}")

            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
                if process.is_alive():
                    process.kill()

            # 从缓存中移除
            self._sandbox_cache.pop(bot_id, None)

            return {
                "success": False,
                "error": f"Execution timeout or error: {str(e)}"
            }

    def _destroy_sandbox(self, bot_id: str):
        """
        销毁沙箱

        Args:
            bot_id: Bot ID
        """
        sandbox_data = self._sandbox_cache.pop(bot_id, None)
        if not sandbox_data:
            return

        sandbox, last_used = sandbox_data

        if isinstance(sandbox, tuple) and len(sandbox) == 3:
            process, request_queue, response_queue = sandbox

            # 终止进程
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
                if process.is_alive():
                    process.kill()

            # 关闭队列
            try:
                request_queue.close()
                response_queue.close()
            except Exception:
                pass

            print(f"[Sandbox] Bot '{bot_id}' 沙箱已销毁")

    def destroy_all(self):
        """销毁所有沙箱"""
        for bot_id in list(self._sandbox_cache.keys()):
            self._destroy_sandbox(bot_id)

    def cleanup_idle_sandboxes(self):
        """清理空闲的沙箱"""
        now = time.time()

        for bot_id, (sandbox, last_used) in list(self._sandbox_cache.items()):
            if (now - last_used) > self.config.cache_timeout_seconds:
                print(f"[Sandbox] 清理空闲沙箱: {bot_id}")
                self._destroy_sandbox(bot_id)


def _sandbox_worker(
    bot_id: str,
    request_queue: multiprocessing.Queue,
    response_queue: multiprocessing.Queue,
    config: SandboxConfig
):
    """
    沙箱工作进程（在独立进程中运行）

    Args:
        bot_id: Bot ID
        request_queue: 请求队列
        response_queue: 响应队列
        config: 沙箱配置
    """
    # 设置资源限制
    try:
        # 设置内存限制
        if hasattr(resource, 'setrlimit'):
            import resource
            memory_limit = config.max_memory_mb * 1024 * 1024
            resource.setrlimit(resource.RLIMIT_AS, (memory_limit, memory_limit))

    except Exception as e:
        print(f"[Sandbox Worker] 设置资源限制失败: {e}")

    # 设置超时信号处理
    def timeout_handler(signum, frame):
        raise TimeoutError("Sandbox execution timeout")

    signal.signal(signal.SIGALRM, timeout_handler)

    # 注入文件系统客户端环境变量
    def _inject_fs_client(fs_config_dict: Optional[Dict]):
        """注入文件系统客户端配置到环境变量"""
        if not fs_config_dict:
            return

        os.environ['CLAWDBOZ_FS_API_URL'] = fs_config_dict.get('api_url', '')
        os.environ['CLAWDBOZ_FS_TOKEN'] = fs_config_dict.get('token', '')
        os.environ['CLAWDBOZ_FS_CHAT_ID'] = fs_config_dict.get('chat_id', '')

    # 发送就绪消息
    response_queue.put({"status": "ready"})

    # 主循环
    while True:
        try:
            # 接收请求
            request = request_queue.get()

            if request.get("action") == "shutdown":
                break

            # 设置执行超时
            signal.alarm(config.timeout_seconds)

            try:
                # 注入文件系统客户端配置
                fs_config = request.get("fs_config")
                if fs_config:
                    _inject_fs_client(fs_config)

                # 执行 Bot 调用
                # TODO: 这里需要加载实际的 Bot 并执行调用
                # 目前返回模拟结果
                result = {
                    "success": True,
                    "result": f"Mock response for {bot_id}.{request.get('method')}",
                    "params": request.get("params")
                }

                response_queue.put(result)

            except TimeoutError as e:
                response_queue.put({
                    "success": False,
                    "error": f"Execution timeout: {str(e)}"
                })

            except Exception as e:
                response_queue.put({
                    "success": False,
                    "error": f"Execution error: {str(e)}\n{traceback.format_exc()}"
                })

            finally:
                # 取消超时
                signal.alarm(0)

        except Exception as e:
            response_queue.put({
                "success": False,
                "error": f"Worker error: {str(e)}"
            })

    # 清理
    try:
        request_queue.close()
        response_queue.close()
    except Exception:
        pass
