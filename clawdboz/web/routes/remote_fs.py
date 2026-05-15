"""
文件访问 API 路由
为远程 Bot 提供安全的文件访问接口
"""
import os
import time
import jwt
from typing import Optional, List
from pathlib import Path
from fastapi import APIRouter, HTTPException, Header, Response
from pydantic import BaseModel

from clawdboz.remote.auth import TokenManager
from clawdboz.remote.chat_context import ChatSessionContext
from clawdboz.remote.path_guard import PathGuard, PathTraversalError
from clawdboz.remote.audit_logger import AuditLogger, OperationType, OperationResult


# ============================================================================
# 数据模型
# ============================================================================

class ListDirectoryRequest(BaseModel):
    """列出目录请求"""
    path: str = ""
    token: str


class ReadFileRequest(BaseModel):
    """读取文件请求"""
    path: str
    token: str
    max_size: int = 10 * 1024 * 1024  # 默认 10MB


class WriteFileRequest(BaseModel):
    """写入文件请求"""
    path: str
    content: str
    token: str


class MakeDirectoryRequest(BaseModel):
    """创建目录请求"""
    path: str
    recursive: bool = False
    token: str


class DeleteRequest(BaseModel):
    """删除请求"""
    path: str
    token: str


# ============================================================================
# 文件系统 API
# ============================================================================

router = APIRouter(prefix="/api/remote/fs", tags=["remote-fs"])

# Token 管理器（需要从配置获取密钥）
# TODO: 从配置中获取密钥
_token_manager: Optional[TokenManager] = None

# 审计日志记录器
_audit_logger = AuditLogger()

# 会话上下文缓存 {token: ChatSessionContext}
_session_contexts: dict = {}


def get_token_manager() -> TokenManager:
    """获取 Token 管理器"""
    global _token_manager
    if _token_manager is None:
        # TODO: 从配置获取密钥
        _token_manager = TokenManager(secret_key="your-secret-key-change-me")
    return _token_manager


def get_workspace_path(chat_id: str) -> Path:
    """
    获取会话工作区路径

    Args:
        chat_id: 会话 ID

    Returns:
        工作区路径
    """
    # 群聊：groupspace/g_{chat_id}
    # 单聊：workplace_{bot_id}/w_{chat_id}
    if chat_id.startswith("g_"):
        return Path("WORKSPACE/groupspace") / chat_id
    else:
        # 单聊需要知道 bot_id，暂时使用默认值
        # TODO: 从 token 中获取 bot_id
        return Path("WORKSPACE") / "workplace_default" / chat_id


def verify_token(token: str) -> ChatSessionContext:
    """
    验证 Token 并返回会话上下文

    Args:
        token: JWT Token

    Returns:
        会话上下文

    Raises:
        HTTPException: Token 无效或过期
    """
    try:
        payload = get_token_manager().verify_chat_token(token)

        # 检查是否过期
        if payload.exp < time.time():
            raise HTTPException(status_code=401, detail="Token has expired")

        # 获取或创建会话上下文
        if token in _session_contexts:
            context = _session_contexts[token]
        else:
            workspace_path = get_workspace_path(payload.chat_id)

            context = ChatSessionContext(
                chat_id=payload.chat_id,
                workspace_path=workspace_path,
                token=token,
                expires_at=payload.exp,
                instance_id=payload.instance_id,
                bot_id=payload.bot_id
            )
            _session_contexts[token] = context

        # 确保工作区存在
        context.workspace_path.mkdir(parents=True, exist_ok=True)

        return context

    except ValueError as e:
        raise HTTPException(status_code=401, detail=str(e))
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Token verification failed: {str(e)}")


# ============================================================================
# API 路由
# ============================================================================

@router.post("/ls")
async def list_directory(request: ListDirectoryRequest):
    """
    列出目录内容

    Args:
        request: 列出目录请求

    Returns:
        目录内容列表
    """
    start_time = time.time()

    try:
        # 验证 Token
        context = verify_token(request.token)

        # 验证路径
        target_path = context.get_allowed_path(request.path)

        # 检查路径遍历
        if PathGuard.detect_path_traversal(request.path):
            _audit_logger.log_operation(
                operation=OperationType.LS,
                chat_id=context.chat_id,
                path=request.path,
                result=OperationResult.UNAUTHORIZED,
                instance_id=context.instance_id,
                bot_id=context.bot_id
            )
            raise HTTPException(status_code=403, detail="Path traversal detected")

        # 规范化路径
        target_path = PathGuard.validate_path(
            request.path or ".",
            context.workspace_path
        )

        # 列出目录
        if not target_path.exists():
            _audit_logger.log_operation(
                operation=OperationType.LS,
                chat_id=context.chat_id,
                path=request.path,
                result=OperationResult.NOT_FOUND,
                instance_id=context.instance_id,
                bot_id=context.bot_id
            )
            raise HTTPException(status_code=404, detail="Directory not found")

        if not target_path.is_dir():
            raise HTTPException(status_code=400, detail="Not a directory")

        entries = []
        for item in target_path.iterdir():
            entries.append({
                "name": item.name,
                "type": "directory" if item.is_dir() else "file",
                "size": item.stat().st_size if item.is_file() else 0
            })

        duration_ms = (time.time() - start_time) * 1000

        _audit_logger.log_operation(
            operation=OperationType.LS,
            chat_id=context.chat_id,
            path=request.path,
            result=OperationResult.SUCCESS,
            instance_id=context.instance_id,
            bot_id=context.bot_id,
            duration_ms=duration_ms
        )

        return {
            "success": True,
            "entries": entries
        }

    except HTTPException:
        raise
    except Exception as e:
        _audit_logger.log_operation(
            operation=OperationType.LS,
            chat_id=context.chat_id,
            path=request.path,
            result=OperationResult.FAILED,
            instance_id=context.instance_id,
            bot_id=context.bot_id,
            error=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/read")
async def read_file(request: ReadFileRequest):
    """
    读取文件内容

    Args:
        request: 读取文件请求

    Returns:
        文件内容
    """
    start_time = time.time()

    try:
        # 验证 Token
        context = verify_token(request.token)

        # 验证路径
        if PathGuard.detect_path_traversal(request.path):
            _audit_logger.log_operation(
                operation=OperationType.READ,
                chat_id=context.chat_id,
                path=request.path,
                result=OperationResult.UNAUTHORIZED,
                instance_id=context.instance_id,
                bot_id=context.bot_id
            )
            raise HTTPException(status_code=403, detail="Path traversal detected")

        target_path = PathGuard.validate_path(request.path, context.workspace_path)

        # 检查文件是否存在
        if not target_path.exists():
            _audit_logger.log_operation(
                operation=OperationType.READ,
                chat_id=context.chat_id,
                path=request.path,
                result=OperationResult.NOT_FOUND,
                instance_id=context.instance_id,
                bot_id=context.bot_id
            )
            raise HTTPException(status_code=404, detail="File not found")

        if not target_path.is_file():
            raise HTTPException(status_code=400, detail="Not a file")

        # 检查文件大小
        file_size = target_path.stat().st_size
        if file_size > request.max_size:
            raise HTTPException(
                status_code=413,
                detail=f"File too large: {file_size} > {request.max_size}"
            )

        # 读取文件
        content = target_path.read_text(encoding='utf-8')

        duration_ms = (time.time() - start_time) * 1000

        _audit_logger.log_operation(
            operation=OperationType.READ,
            chat_id=context.chat_id,
            path=request.path,
            result=OperationResult.SUCCESS,
            instance_id=context.instance_id,
            bot_id=context.bot_id,
            file_size=file_size,
            duration_ms=duration_ms
        )

        return {
            "success": True,
            "content": content,
            "size": file_size
        }

    except HTTPException:
        raise
    except Exception as e:
        _audit_logger.log_operation(
            operation=OperationType.READ,
            chat_id=context.chat_id,
            path=request.path,
            result=OperationResult.FAILED,
            instance_id=context.instance_id,
            bot_id=context.bot_id,
            error=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/write")
async def write_file(request: WriteFileRequest):
    """
    写入文件

    Args:
        request: 写入文件请求

    Returns:
        写入结果
    """
    start_time = time.time()

    try:
        # 验证 Token
        context = verify_token(request.token)

        # 验证路径
        if PathGuard.detect_path_traversal(request.path):
            _audit_logger.log_operation(
                operation=OperationType.WRITE,
                chat_id=context.chat_id,
                path=request.path,
                result=OperationResult.UNAUTHORIZED,
                instance_id=context.instance_id,
                bot_id=context.bot_id
            )
            raise HTTPException(status_code=403, detail="Path traversal detected")

        target_path = PathGuard.validate_path(request.path, context.workspace_path)

        # 确保父目录存在
        target_path.parent.mkdir(parents=True, exist_ok=True)

        # 写入文件
        target_path.write_text(request.content, encoding='utf-8')

        file_size = len(request.content.encode('utf-8'))
        duration_ms = (time.time() - start_time) * 1000

        _audit_logger.log_operation(
            operation=OperationType.WRITE,
            chat_id=context.chat_id,
            path=request.path,
            result=OperationResult.SUCCESS,
            instance_id=context.instance_id,
            bot_id=context.bot_id,
            file_size=file_size,
            duration_ms=duration_ms
        )

        return {
            "success": True,
            "size": file_size
        }

    except HTTPException:
        raise
    except Exception as e:
        _audit_logger.log_operation(
            operation=OperationType.WRITE,
            chat_id=context.chat_id,
            path=request.path,
            result=OperationResult.FAILED,
            instance_id=context.instance_id,
            bot_id=context.bot_id,
            error=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/mkdir")
async def make_directory(request: MakeDirectoryRequest):
    """
    创建目录

    Args:
        request: 创建目录请求

    Returns:
        创建结果
    """
    start_time = time.time()

    try:
        # 验证 Token
        context = verify_token(request.token)

        # 验证路径
        if PathGuard.detect_path_traversal(request.path):
            _audit_logger.log_operation(
                operation=OperationType.MKDIR,
                chat_id=context.chat_id,
                path=request.path,
                result=OperationResult.UNAUTHORIZED,
                instance_id=context.instance_id,
                bot_id=context.bot_id
            )
            raise HTTPException(status_code=403, detail="Path traversal detected")

        target_path = PathGuard.validate_path(request.path, context.workspace_path)

        # 创建目录
        if request.recursive:
            target_path.mkdir(parents=True, exist_ok=True)
        else:
            if not target_path.parent.exists():
                raise HTTPException(
                    status_code=400,
                    detail="Parent directory does not exist"
                )
            target_path.mkdir(exist_ok=True)

        duration_ms = (time.time() - start_time) * 1000

        _audit_logger.log_operation(
            operation=OperationType.MKDIR,
            chat_id=context.chat_id,
            path=request.path,
            result=OperationResult.SUCCESS,
            instance_id=context.instance_id,
            bot_id=context.bot_id,
            duration_ms=duration_ms
        )

        return {
            "success": True
        }

    except HTTPException:
        raise
    except Exception as e:
        _audit_logger.log_operation(
            operation=OperationType.MKDIR,
            chat_id=context.chat_id,
            path=request.path,
            result=OperationResult.FAILED,
            instance_id=context.instance_id,
            bot_id=context.bot_id,
            error=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e))


@router.post("/delete")
async def delete_path(request: DeleteRequest):
    """
    删除文件或目录

    Args:
        request: 删除请求

    Returns:
        删除结果
    """
    start_time = time.time()

    try:
        # 验证 Token
        context = verify_token(request.token)

        # 验证路径
        if PathGuard.detect_path_traversal(request.path):
            # 根据类型记录操作
            target_path = context.get_allowed_path(request.path)
            if target_path.is_dir():
                op_type = OperationType.DELETE_DIR
            else:
                op_type = OperationType.DELETE_FILE

            _audit_logger.log_operation(
                operation=op_type,
                chat_id=context.chat_id,
                path=request.path,
                result=OperationResult.UNAUTHORIZED,
                instance_id=context.instance_id,
                bot_id=context.bot_id
            )
            raise HTTPException(status_code=403, detail="Path traversal detected")

        target_path = PathGuard.validate_path(request.path, context.workspace_path)

        # 检查是否存在
        if not target_path.exists():
            raise HTTPException(status_code=404, detail="Path not found")

        # 删除
        if target_path.is_dir():
            op_type = OperationType.DELETE_DIR
            import shutil
            shutil.rmtree(target_path)
        else:
            op_type = OperationType.DELETE_FILE
            target_path.unlink()

        duration_ms = (time.time() - start_time) * 1000

        _audit_logger.log_operation(
            operation=op_type,
            chat_id=context.chat_id,
            path=request.path,
            result=OperationResult.SUCCESS,
            instance_id=context.instance_id,
            bot_id=context.bot_id,
            duration_ms=duration_ms
        )

        return {
            "success": True
        }

    except HTTPException:
        raise
    except Exception as e:
        _audit_logger.log_operation(
            operation=OperationType.DELETE_FILE,
            chat_id=context.chat_id,
            path=request.path,
            result=OperationResult.FAILED,
            instance_id=context.instance_id,
            bot_id=context.bot_id,
            error=str(e)
        )
        raise HTTPException(status_code=500, detail=str(e))
