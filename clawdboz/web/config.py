"""
Web Server Configuration and Type Definitions

This module contains configuration constants and type definitions for the Clawdboz Web Chat server.
"""

# =============================================================================
# Imports
# =============================================================================
from typing import Dict, List, Optional, Set, Tuple, TypedDict, Union, Any


# =============================================================================
# Default Configuration Constants
# =============================================================================

# Server defaults
DEFAULT_PORT: int = 8080
DEFAULT_HOST: str = "0.0.0.0"
DEFAULT_AUTH_TOKEN_LENGTH: int = 16

# Workplace and workspace defaults
DEFAULT_WORKPLACE_DIR: str = "WORKPLACE"
DEFAULT_BOT_WORKPLACE_PREFIX: str = "workplace_"
DEFAULT_SESSION_PREFIX: str = "w_"
DEFAULT_GROUP_PREFIX: str = "g_"
DEFAULT_GROUPSPACE_DIR: str = "groupspace"

# History and caching defaults
DEFAULT_MAX_HISTORY: int = 30
DEFAULT_MAX_MENTION_DEPTH: int = 3

# File upload defaults
DEFAULT_UPLOAD_DIR: str = "uploads"

# Subdirectory names for workspace structure
WORKSPACE_LOGS_DIR: str = "logs"
WORKSPACE_TEMP_DIR: str = "temp"
WORKSPACE_USER_FILES_DIR: str = "user_files"
WORKSPACE_USER_IMAGES_DIR: str = "user_images"
WORKSPACE_SKILLS_DIR: str = ".agents/skills"

# Bot configuration files
BOT_CONFIG_FILE: str = ".bot.md"
SESSION_MEMORY_FILE: str = ".session_memory.md"

# Session file (merged history + meta)
SESSION_FILE: str = "session.json"
SCHEDULER_TASKS_FILE: str = "scheduler_tasks.json"

# Deprecated: for backward compatibility only
HISTORY_FILE: str = "history.json"
META_FILE: str = "meta.json"

# Environment variable names
ENV_MOMENTS_WORKPLACE: str = "MOMENTS_WORKPLACE"
ENV_SESSION_WORK_DIR: str = "CLAWDBOZ_SESSION_WORK_DIR"
ENV_BOT_WORK_DIR: str = "CLAWDBOZ_BOT_WORK_DIR"
ENV_MCP_MODE: str = "CLAWDBOZ_MCP_MODE"
ENV_WEBCHAT_URL: str = "CLAWDBOZ_WEBCHAT_URL"
ENV_WEBCHAT_TOKEN: str = "CLAWDBOZ_WEBCHAT_TOKEN"

# MCP modes
MCP_MODE_WEBCHAT: str = "webchat"
MCP_MODE_FEISHU: str = "feishu"


# =============================================================================
# Type Definitions
# =============================================================================

class MessageDict(TypedDict, total=False):
    """Message structure for chat history and WebSocket communication."""
    sender: str
    content: str
    timestamp: Optional[float]
    type: Optional[str]  # "text", "file", "image", etc.
    is_thinking: Optional[bool]
    thinking_content: Optional[str]


class ConnectionDict(TypedDict, total=False):
    """WebSocket connection metadata."""
    websocket: Any  # WebSocket instance
    session_id: str
    connected_at: float


class BotConfigDict(TypedDict, total=False):
    """Bot configuration structure."""
    system_prompt: str
    app_id: str
    app_secret: str
    model: Optional[str]
    temperature: Optional[float]


class SessionMetaDict(TypedDict, total=False):
    """Session metadata structure."""
    id: str
    created_at: Optional[float]
    updated_at: Optional[float]
    bot_ids: Optional[List[str]]
    is_group: Optional[bool]
    title: Optional[str]


class HistoryEntryDict(TypedDict, total=False):
    """History file entry structure."""
    role: str  # "user", "assistant", "system"
    content: str
    timestamp: Optional[float]
    bot_id: Optional[str]
    metadata: Optional[Dict[str, Any]]


class SchedulerTaskDict(TypedDict, total=False):
    """Scheduled task structure."""
    id: str
    cron: str
    message: str
    bot_id: Optional[str]
    chat_id: Optional[str]
    created_at: Optional[float]
    updated_at: Optional[float]
    enabled: Optional[bool]


class MentionPermissionDict(TypedDict, total=False):
    """Mention permission configuration for a chat."""
    allowed_directions: Dict[str, List[str]]  # sender_id -> list of target_ids
    depth: int


class MCPMessageDict(TypedDict, total=False):
    """MCP message structure for internal communication."""
    type: str  # "mcp_message", "mcp_file", "mcp_notify"
    content: Optional[str]
    file_path: Optional[str]
    file_name: Optional[str]
    chat_id: Optional[str]
    sender: Optional[str]
    is_hidden: Optional[bool]


class FileUploadDict(TypedDict, total=False):
    """File upload metadata structure."""
    filename: str
    content_type: str
    size: int
    path: str
    uploaded_at: float


# Type aliases
ChatId = str
BotId = str
SessionId = str
WorkspacePath = str
LockKey = Tuple[str, str]  # (session_id, bot_id)


# =============================================================================
# WebSocket Message Types
# =============================================================================

WS_MESSAGE_TYPE_TEXT: str = "text"
WS_MESSAGE_TYPE_THINKING: str = "thinking"
WS_MESSAGE_TYPE_FILE: str = "file"
WS_MESSAGE_TYPE_IMAGE: str = "image"
WS_MESSAGE_TYPE_ERROR: str = "error"
WS_MESSAGE_TYPE_SYSTEM: str = "system"
WS_MESSAGE_TYPE_MCP: str = "mcp_message"
WS_MESSAGE_TYPE_MCP_FILE: str = "mcp_file"
WS_MESSAGE_TYPE_MCP_NOTIFY: str = "mcp_notify"


# =============================================================================
# Sender Type Constants
# =============================================================================

SENDER_USER: str = "user"
SENDER_SYSTEM: str = "system"
SENDER_PREFIX_BOT: str = "bot_"


# =============================================================================
# HTTP Status and Error Messages
# =============================================================================

ERROR_MISSING_TOKEN: str = "Missing authentication token"
ERROR_INVALID_TOKEN: str = "Invalid authentication token"
ERROR_BOT_NOT_FOUND: str = "Bot not found"
ERROR_SESSION_NOT_FOUND: str = "Session not found"
ERROR_FILE_TOO_LARGE: str = "File too large"
ERROR_INVALID_FILE_TYPE: str = "Invalid file type"


# =============================================================================
# File Upload Constraints
# =============================================================================

MAX_FILE_SIZE_MB: int = 10
MAX_FILE_SIZE_BYTES: int = MAX_FILE_SIZE_MB * 1024 * 1024
ALLOWED_IMAGE_TYPES: Set[str] = {"image/jpeg", "image/png", "image/gif", "image/webp"}
ALLOWED_DOCUMENT_TYPES: Set[str] = {
    "text/plain",
    "text/markdown",
    "application/pdf",
    "application/msword",
    "application/vnd.openxmlformats-officedocument.wordprocessingml.document",
    "application/vnd.ms-excel",
    "application/vnd.openxmlformats-officedocument.spreadsheetml.sheet",
}
