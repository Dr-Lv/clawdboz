"""
文件系统客户端
供远程 Bot 使用，通过 HTTP API 访问文件系统
"""
import os
from typing import List, Optional
import aiohttp


class FileSystemClient:
    """文件系统客户端"""

    def __init__(
        self,
        api_url: str,
        token: str,
        timeout: int = 30
    ):
        """
        初始化文件系统客户端

        Args:
            api_url: 文件访问 API URL (如 https://instance-a/api/remote/fs)
            token: 认证 Token
            timeout: 请求超时时间（秒）
        """
        self.api_url = api_url.rstrip('/')
        self.token = token
        self.timeout = timeout
        self._session: Optional[aiohttp.ClientSession] = None

    async def __aenter__(self):
        """异步上下文管理器入口"""
        self._session = aiohttp.ClientSession()
        return self

    async def __aexit__(self, *args):
        """异步上下文管理器出口"""
        if self._session:
            await self._session.close()

    def _ensure_session(self):
        """确保会话存在"""
        if self._session is None:
            self._session = aiohttp.ClientSession()

    async def _post(self, endpoint: str, data: dict) -> dict:
        """
        发送 POST 请求

        Args:
            endpoint: API 端点
            data: 请求数据

        Returns:
            响应数据

        Raises:
            Exception: 请求失败
        """
        self._ensure_session()

        url = f"{self.api_url}/{endpoint}"
        data['token'] = self.token  # 自动添加 Token

        try:
            async with self._session.post(url, json=data, timeout=self.timeout) as resp:
                if resp.status != 200:
                    error_text = await resp.text()
                    raise Exception(f"API error {resp.status}: {error_text}")

                return await resp.json()

        except aiohttp.ClientError as e:
            raise Exception(f"HTTP client error: {str(e)}")

        except Exception as e:
            raise Exception(f"Request failed: {str(e)}")

    async def list_directory(self, path: str = "") -> List[dict]:
        """
        列出目录内容

        Args:
            path: 目录路径（相对于会话根目录）

        Returns:
            文件/目录列表 [{"name": str, "type": "file|directory", "size": int}]

        Raises:
            Exception: 列出目录失败
        """
        try:
            result = await self._post("ls", {"path": path})

            if result.get("success"):
                return result.get("entries", [])
            else:
                raise Exception(result.get("error", "Unknown error"))

        except Exception as e:
            print(f"[FSClient] 列出目录失败 ({path}): {e}")
            raise

    async def read_file(self, path: str, max_size: int = 10 * 1024 * 1024) -> str:
        """
        读取文件内容

        Args:
            path: 文件路径（相对于会话根目录）
            max_size: 最大文件大小（字节）

        Returns:
            文件内容

        Raises:
            Exception: 读取文件失败
        """
        try:
            result = await self._post("read", {
                "path": path,
                "max_size": max_size
            })

            if result.get("success"):
                return result.get("content", "")
            else:
                raise Exception(result.get("error", "Unknown error"))

        except Exception as e:
            print(f"[FSClient] 读取文件失败 ({path}): {e}")
            raise

    async def write_file(self, path: str, content: str) -> int:
        """
        写入文件

        Args:
            path: 文件路径（相对于会话根目录）
            content: 文件内容

        Returns:
            写入的字节数

        Raises:
            Exception: 写入文件失败
        """
        try:
            result = await self._post("write", {
                "path": path,
                "content": content
            })

            if result.get("success"):
                return result.get("size", 0)
            else:
                raise Exception(result.get("error", "Unknown error"))

        except Exception as e:
            print(f"[FSClient] 写入文件失败 ({path}): {e}")
            raise

    async def make_directory(self, path: str, recursive: bool = False) -> bool:
        """
        创建目录

        Args:
            path: 目录路径（相对于会话根目录）
            recursive: 是否递归创建父目录

        Returns:
            是否成功

        Raises:
            Exception: 创建目录失败
        """
        try:
            result = await self._post("mkdir", {
                "path": path,
                "recursive": recursive
            })

            if result.get("success"):
                return True
            else:
                raise Exception(result.get("error", "Unknown error"))

        except Exception as e:
            print(f"[FSClient] 创建目录失败 ({path}): {e}")
            raise

    async def delete(self, path: str) -> bool:
        """
        删除文件或目录

        Args:
            path: 路径（相对于会话根目录）

        Returns:
            是否成功

        Raises:
            Exception: 删除失败
        """
        try:
            result = await self._post("delete", {"path": path})

            if result.get("success"):
                return True
            else:
                raise Exception(result.get("error", "Unknown error"))

        except Exception as e:
            print(f"[FSClient] 删除失败 ({path}): {e}")
            raise

    async def file_exists(self, path: str) -> bool:
        """
        检查文件是否存在

        Args:
            path: 文件路径

        Returns:
            是否存在
        """
        try:
            # 尝试列出父目录，检查文件是否在列表中
            parent_dir = os.path.dirname(path) or "."
            file_name = os.path.basename(path)

            entries = await self.list_directory(parent_dir)

            return any(entry.get("name") == file_name for entry in entries)

        except Exception:
            return False

    async def is_directory(self, path: str) -> bool:
        """
        检查路径是否是目录

        Args:
            path: 路径

        Returns:
            是否是目录
        """
        try:
            parent_dir = os.path.dirname(path) or "."
            dir_name = os.path.basename(path)

            entries = await self.list_directory(parent_dir)

            for entry in entries:
                if entry.get("name") == dir_name:
                    return entry.get("type") == "directory"

            return False

        except Exception:
            return False

    async def close(self):
        """关闭客户端"""
        if self._session:
            await self._session.close()
            self._session = None


class SyncFileSystemClient:
    """同步版本的文件系统客户端（用于不支持 async 的场景）"""

    def __init__(
        self,
        api_url: str,
        token: str,
        timeout: int = 30
    ):
        """
        初始化同步文件系统客户端

        Args:
            api_url: 文件访问 API URL
            token: 认证 Token
            timeout: 请求超时时间（秒）
        """
        self.api_url = api_url.rstrip('/')
        self.token = token
        self.timeout = timeout

    def _post(self, endpoint: str, data: dict) -> dict:
        """
        发送 POST 请求（同步）

        Args:
            endpoint: API 端点
            data: 请求数据

        Returns:
            响应数据
        """
        import requests

        url = f"{self.api_url}/{endpoint}"
        data['token'] = self.token

        try:
            resp = requests.post(url, json=data, timeout=self.timeout)

            if resp.status_code != 200:
                raise Exception(f"API error {resp.status_code}: {resp.text}")

            return resp.json()

        except requests.RequestException as e:
            raise Exception(f"Request failed: {str(e)}")

    def list_directory(self, path: str = "") -> List[dict]:
        """列出目录内容（同步）"""
        result = self._post("ls", {"path": path})
        if result.get("success"):
            return result.get("entries", [])
        else:
            raise Exception(result.get("error", "Unknown error"))

    def read_file(self, path: str, max_size: int = 10 * 1024 * 1024) -> str:
        """读取文件内容（同步）"""
        result = self._post("read", {
            "path": path,
            "max_size": max_size
        })
        if result.get("success"):
            return result.get("content", "")
        else:
            raise Exception(result.get("error", "Unknown error"))

    def write_file(self, path: str, content: str) -> int:
        """写入文件（同步）"""
        result = self._post("write", {
            "path": path,
            "content": content
        })
        if result.get("success"):
            return result.get("size", 0)
        else:
            raise Exception(result.get("error", "Unknown error"))

    def make_directory(self, path: str, recursive: bool = False) -> bool:
        """创建目录（同步）"""
        result = self._post("mkdir", {
            "path": path,
            "recursive": recursive
        })
        if result.get("success"):
            return True
        else:
            raise Exception(result.get("error", "Unknown error"))

    def delete(self, path: str) -> bool:
        """删除文件或目录（同步）"""
        result = self._post("delete", {"path": path})
        if result.get("success"):
            return True
        else:
            raise Exception(result.get("error", "Unknown error"))

    def file_exists(self, path: str) -> bool:
        """检查文件是否存在（同步）"""
        try:
            parent_dir = os.path.dirname(path) or "."
            file_name = os.path.basename(path)

            entries = self.list_directory(parent_dir)
            return any(entry.get("name") == file_name for entry in entries)

        except Exception:
            return False
