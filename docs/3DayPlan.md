# 嗑唠的宝子 v2.2.0 功能升级 3天开发计划

> **版本目标**: v2.2.0 重大功能升级  
> **规划日期**: 2026-02-15  
> **执行方式**: 从易到难，逐层递进

---

## 📊 功能需求清单（7项）

| 序号 | 功能 | 难度 | 优先级 | 规划天数 |
|:----:|------|:----:|:------:|:--------:|
| 1 | 长期记忆 MCP | ⭐⭐⭐ | P1 | Day 2 |
| 2 | 飞书插件支持（文档/表格/任务等） | ⭐⭐⭐⭐⭐ | P2 | Day 3 |
| 3 | 心跳机制 + 定时任务 + 夜间自主活动 + 长时间任务 | ⭐⭐⭐⭐ | P1 | Day 2 |
| 4 | 工作区/软件区分类 + 权限访问控制 | ⭐⭐⭐⭐ | P2 | Day 2 |
| 5 | 多用户聊天记录隔离 + 数据库存储 | ⭐⭐⭐⭐⭐ | P1 | Day 3 |
| 6 | 改造成 pip 安装包（3行代码创建Bot） | ⭐⭐⭐ | P0 | Day 1 |
| 7 | 制作完整 Docker 镜像 | ⭐⭐ | P0 | Day 1 |

---

## 🌅 Day 1: 基础架构升级（低风险，建立基础）

### 目标产出
```bash
# Docker 运行
docker run -d --env-file .env clawdboz/larkbot:v2.2.0

# Pip 安装
pip install clawdboz

# 3行代码创建 Bot
from clawdboz import Bot
bot = Bot(app_id="xxx", app_secret="xxx")
bot.run()
```

### 上午 (4h): Docker 镜像制作

| 时间 | 任务 | 产出物 |
|:----:|------|--------|
| 0-1h | 编写 Dockerfile（多阶段构建） | `Dockerfile` |
| 1-2h | 编写 docker-compose.yml | `docker-compose.yml` |
| 2-3h | 配置环境变量传递机制 | 文档更新 |
| 3-4h | 测试镜像构建和运行 | 可运行镜像 |

**Dockerfile 要点**:
- 基于 `python:3.11-slim`
- 多阶段构建减少镜像体积
- 内置虚拟环境
- 暴露必要端口
- 健康检查脚本

### 下午 (4h): Pip 包改造

| 时间 | 任务 | 产出物 |
|:----:|------|--------|
| 0-1h | 创建 `pyproject.toml` / `setup.py` | 包配置文件 |
| 1-2h | 重构 `src/__init__.py` 导出简洁 API | `src/__init__.py` |
| 2-3h | 设计并实现 `Bot` 简化类 | `src/simple_bot.py` |
| 3-4h | 本地测试 `pip install -e .` | 可安装包 |

**目标 API 设计**:

```python
# src/simple_bot.py
"""简化版 Bot API，3行代码启动"""

from .bot import LarkBot
from .config import load_config

class Bot:
    """简化版 Bot 类"""
    
    def __init__(self, app_id=None, app_secret=None, **kwargs):
        """
        初始化 Bot
        
        Args:
            app_id: 飞书 App ID（优先）
            app_secret: 飞书 App Secret（优先）
            **kwargs: 其他配置项
        """
        config = load_config()
        self.app_id = app_id or config.get('feishu', {}).get('app_id')
        self.app_secret = app_secret or config.get('feishu', {}).get('app_secret')
        self.bot = LarkBot(self.app_id, self.app_secret)
        
    def run(self):
        """启动 Bot（阻塞运行）"""
        from .main import main
        import sys
        sys.argv = ['clawdboz', self.app_id, self.app_secret]
        main()
    
    def send_message(self, chat_id, message):
        """发送消息"""
        return self.bot.reply_text(chat_id, message)
```

**pyproject.toml 示例**:

```toml
[project]
name = "clawdboz"
version = "2.2.0"
description = "基于 Kimi Code CLI 的智能飞书机器人"
readme = "README.md"
requires-python = ">=3.10"
license = {text = "MIT"}
authors = [
    {name = "Clawdboz Team"}
]
classifiers = [
    "Development Status :: 4 - Beta",
    "Intended Audience :: Developers",
    "License :: OSI Approved :: MIT License",
    "Programming Language :: Python :: 3.10",
    "Programming Language :: Python :: 3.11",
    "Programming Language :: Python :: 3.12",
]
dependencies = [
    "lark-oapi>=1.5.0",
    "requests>=2.28.0",
    "apscheduler>=3.10.0",
    "sqlalchemy>=2.0.0",
    "alembic>=1.12.0",
    "pydantic>=2.0.0",
]

[project.scripts]
clawdboz = "clawdboz.cli:main"

[project.urls]
Homepage = "https://github.com/yourusername/clawdboz"
Repository = "https://github.com/yourusername/clawdboz"
```

### Day 1 检查清单

- [ ] Dockerfile 构建成功
- [ ] Docker 镜像运行正常
- [ ] `pip install -e .` 安装成功
- [ ] 3行代码 API 可用
- [ ] 更新 README 安装说明

---

## 🌞 Day 2: 功能扩展（中等复杂度）

### 目标产出
```python
# 长期记忆 MCP 可用
# 定时任务调度器运行
# 夜间自主活动开始
# 工作区/软件区权限控制生效
```

### 上午 (4h): 长期记忆 MCP

| 时间 | 任务 | 产出物 |
|:----:|------|--------|
| 0-1h | 设计记忆存储格式 | 设计文档 |
| 1-2h | 实现 `memory_store` MCP Server | `mcp/memory_server.py` |
| 2-3h | 实现 remember/recall/forget 工具 | 工具实现 |
| 3-4h | 集成到 Bot 初始化流程 | 集成代码 |

**记忆存储设计**:

```python
# mcp/memory_server.py
"""长期记忆 MCP Server"""

import json
import os
import sqlite3
from datetime import datetime
from typing import List, Dict, Optional

class MemoryStore:
    """长期记忆存储"""
    
    def __init__(self, db_path: str = "WORKPLACE/memory.db"):
        self.db_path = db_path
        self._init_db()
    
    def _init_db(self):
        """初始化数据库"""
        conn = sqlite3.connect(self.db_path)
        cursor = conn.cursor()
        cursor.execute('''
            CREATE TABLE IF NOT EXISTS memories (
                id INTEGER PRIMARY KEY AUTOINCREMENT,
                user_id TEXT NOT NULL,
                chat_id TEXT,
                category TEXT DEFAULT 'general',
                content TEXT NOT NULL,
                importance INTEGER DEFAULT 5,
                created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                accessed_at TIMESTAMP,
                access_count INTEGER DEFAULT 0
            )
        ''')
        cursor.execute('''
            CREATE INDEX IF NOT EXISTS idx_user ON memories(user_id);
            CREATE INDEX IF NOT EXISTS idx_category ON memories(category);
        ''')
        conn.commit()
        conn.close()
    
    def remember(self, user_id: str, content: str, 
                 category: str = "general", importance: int = 5) -> bool:
        """保存记忆"""
        pass
    
    def recall(self, user_id: str, query: str, 
               category: str = None, limit: int = 5) -> List[Dict]:
        """回忆记忆"""
        pass
    
    def forget(self, memory_id: int) -> bool:
        """删除记忆"""
        pass
```

### 下午 (5h): 权限控制 + 定时任务

#### 权限控制 (2.5h)

| 时间 | 任务 | 产出物 |
|:----:|------|--------|
| 0-1h | 设计 WorkspaceZone / SoftwareZone 权限模型 | 权限设计文档 |
| 1-2h | 实现路径访问控制装饰器 | `src/security.py` |
| 2-2.5h | 集成到现有代码 | 权限检查点 |

**权限模型设计**:

```python
# src/security.py
"""权限访问控制"""

import os
from enum import Enum
from functools import wraps
from typing import Callable

class Zone(Enum):
    """区域类型"""
    WORKSPACE = "workspace"      # 工作区：用户文件、聊天记录
    SOFTWARE = "software"        # 软件区：源代码、配置
    SYSTEM = "system"            # 系统区：不允许访问

class PermissionManager:
    """权限管理器"""
    
    # 区域路径定义
    ZONE_PATHS = {
        Zone.WORKSPACE: ["WORKPLACE/", "logs/", "data/"],
        Zone.SOFTWARE: ["src/", "feishu_tools/", "docs/"],
        Zone.SYSTEM: ["/etc", "/usr", ".."]
    }
    
    def __init__(self, project_root: str):
        self.project_root = os.path.abspath(project_root)
    
    def check_path(self, path: str, allowed_zones: list = None) -> bool:
        """检查路径是否在允许区域"""
        abs_path = os.path.abspath(path)
        
        # 检查是否在项目根目录内
        if not abs_path.startswith(self.project_root):
            return False
        
        # 检查是否访问系统区域
        for system_path in self.ZONE_PATHS[Zone.SYSTEM]:
            if abs_path.startswith(system_path):
                return False
        
        # 检查是否在允许区域
        if allowed_zones:
            rel_path = os.path.relpath(abs_path, self.project_root)
            for zone in allowed_zones:
                for zone_prefix in self.ZONE_PATHS.get(zone, []):
                    if rel_path.startswith(zone_prefix):
                        return True
            return False
        
        return True

def require_zone(*zones: Zone):
    """区域访问控制装饰器"""
    def decorator(func: Callable):
        @wraps(func)
        def wrapper(self, path: str, *args, **kwargs):
            pm = getattr(self, '_permission_manager', None)
            if pm and not pm.check_path(path, list(zones)):
                raise PermissionError(f"路径 {path} 不在允许访问的区域")
            return func(self, path, *args, **kwargs)
        return wrapper
    return decorator
```

#### 定时任务 (2.5h)

| 时间 | 任务 | 产出物 |
|:----:|------|--------|
| 2.5-3.5h | 集成 APScheduler | `src/scheduler.py` |
| 3.5-4.5h | 实现夜间自主活动任务 | `src/night_activities.py` |
| 4.5-5h | 实现长时间任务队列 | 任务队列实现 |

**定时任务调度器**:

```python
# src/scheduler.py
"""定时任务调度器"""

from apscheduler.schedulers.background import BackgroundScheduler
from apscheduler.triggers.cron import CronTrigger
from datetime import datetime
import logging

logger = logging.getLogger(__name__)

class BotScheduler:
    """Bot 定时任务调度器"""
    
    def __init__(self, bot_ref=None):
        self.bot = bot_ref
        self.scheduler = BackgroundScheduler()
        self._setup_jobs()
    
    def _setup_jobs(self):
        """设置默认任务"""
        # 心跳检查（每5分钟）
        self.scheduler.add_job(
            self._heartbeat_check,
            'interval',
            minutes=5,
            id='heartbeat',
            replace_existing=True
        )
        
        # 夜间自主活动（凌晨2-4点）
        self.scheduler.add_job(
            self._night_activity,
            CronTrigger(hour=2, minute=0),
            id='night_activity',
            replace_existing=True
        )
        
        # 日志清理（每天凌晨3点）
        self.scheduler.add_job(
            self._cleanup_logs,
            CronTrigger(hour=3, minute=0),
            id='cleanup',
            replace_existing=True
        )
    
    def _heartbeat_check(self):
        """心跳检查任务"""
        logger.info("[Scheduler] 执行心跳检查")
        # 检查 WebSocket 连接状态
        # 必要时发送告警
    
    def _night_activity(self):
        """夜间自主活动"""
        logger.info("[Scheduler] 开始夜间自主活动")
        # 分析今日聊天记录
        # 生成日报/摘要
        # 整理记忆
        # 执行预定义的分析任务
    
    def _cleanup_logs(self):
        """清理过期日志"""
        logger.info("[Scheduler] 清理过期日志")
        # 清理7天前的日志文件
    
    def add_long_task(self, task_func, *args, **kwargs):
        """添加长时间任务"""
        # 添加到任务队列，异步执行
        pass
    
    def start(self):
        """启动调度器"""
        self.scheduler.start()
        logger.info("[Scheduler] 定时任务调度器已启动")
    
    def shutdown(self):
        """关闭调度器"""
        self.scheduler.shutdown()


# 长时间任务队列
class LongTaskQueue:
    """长时间任务队列"""
    
    def __init__(self, max_workers: int = 3):
        self.max_workers = max_workers
        self.queue = []
        self.running = []
    
    def submit(self, task_id: str, func, *args, **kwargs):
        """提交长时间任务"""
        pass
    
    def get_status(self, task_id: str) -> dict:
        """获取任务状态"""
        pass
    
    def cancel(self, task_id: str) -> bool:
        """取消任务"""
        pass
```

### Day 2 检查清单

- [ ] 记忆 MCP Server 可独立运行
- [ ] MCP 配置中添加了 memory 工具
- [ ] Bot 能调用 remember/recall
- [ ] 权限控制能阻止非法路径访问
- [ ] APScheduler 集成成功
- [ ] 夜间任务定时触发
- [ ] 长时间任务队列可用

---

## 🌙 Day 3: 核心重构（高难度，改动最大）

### 目标产出
```python
# 聊天记录存入数据库
# 多用户完全隔离
# 飞书文档/表格/任务插件可用
```

### 上午 (5h): 飞书插件支持

| 时间 | 任务 | 产出物 |
|:----:|------|--------|
| 0-1h | 申请飞书开放平台权限 | 权限申请记录 |
| 1-2h | 实现 FeishuDocPlugin | `plugins/feishu_doc.py` |
| 2-3h | 实现 FeishuSheetPlugin | `plugins/feishu_sheet.py` |
| 3-4h | 实现 FeishuTaskPlugin | `plugins/feishu_task.py` |
| 4-5h | 统一插件管理器 | `plugin_manager.py` |

**插件架构设计**:

```python
# plugins/base.py
"""插件基类"""

from abc import ABC, abstractmethod
from typing import Dict, Any

class FeishuPlugin(ABC):
    """飞书插件基类"""
    
    name: str = ""
    description: str = ""
    required_permissions: list = []
    
    def __init__(self, app_id: str, app_secret: str):
        self.app_id = app_id
        self.app_secret = app_secret
        self.token = None
    
    @abstractmethod
    def authenticate(self) -> bool:
        """认证获取 token"""
        pass
    
    @abstractmethod
    def get_tools(self) -> list:
        """返回 MCP 工具列表"""
        pass


# plugins/feishu_doc.py
"""飞书文档插件"""

import requests
from .base import FeishuPlugin

class FeishuDocPlugin(FeishuPlugin):
    """飞书云文档插件"""
    
    name = "feishu_doc"
    description = "飞书云文档操作"
    required_permissions = [
        "docs:document:read",
        "docs:document:write"
    ]
    
    def get_tools(self) -> list:
        return [
            {
                "name": "create_document",
                "description": "创建飞书文档",
                "parameters": {
                    "title": "文档标题",
                    "content": "文档内容（Markdown）"
                }
            },
            {
                "name": "read_document",
                "description": "读取飞书文档内容",
                "parameters": {
                    "doc_token": "文档 token"
                }
            },
            {
                "name": "append_to_document",
                "description": "追加内容到文档",
                "parameters": {
                    "doc_token": "文档 token",
                    "content": "要追加的内容"
                }
            }
        ]
    
    def create_document(self, title: str, content: str = "") -> dict:
        """创建文档"""
        pass
    
    def read_document(self, doc_token: str) -> str:
        """读取文档"""
        pass


# plugins/feishu_sheet.py
"""飞书多维表格插件"""

from .base import FeishuPlugin

class FeishuSheetPlugin(FeishuPlugin):
    """飞书多维表格插件"""
    
    name = "feishu_sheet"
    description = "飞书多维表格操作"
    required_permissions = [
        "sheets:spreadsheet:read",
        "sheets:spreadsheet:write"
    ]
    
    def get_tools(self) -> list:
        return [
            {
                "name": "create_spreadsheet",
                "description": "创建电子表格"
            },
            {
                "name": "read_sheet",
                "description": "读取表格数据"
            },
            {
                "name": "write_sheet",
                "description": "写入表格数据"
            },
            {
                "name": "query_records",
                "description": "查询多维表格记录"
            }
        ]


# plugins/feishu_task.py
"""飞书任务插件"""

from .base import FeishuPlugin

class FeishuTaskPlugin(FeishuPlugin):
    """飞书任务插件"""
    
    name = "feishu_task"
    description = "飞书任务管理"
    required_permissions = [
        "task:task:read",
        "task:task:write"
    ]
    
    def get_tools(self) -> list:
        return [
            {
                "name": "create_task",
                "description": "创建任务"
            },
            {
                "name": "list_tasks",
                "description": "列出任务"
            },
            {
                "name": "update_task",
                "description": "更新任务"
            },
            {
                "name": "complete_task",
                "description": "完成任务"
            }
        ]
```

### 下午 (6h): 数据库重构 + 多用户隔离

| 时间 | 任务 | 产出物 |
|:----:|------|--------|
| 0-1.5h | 设计数据模型（SQLAlchemy） | `models/` |
| 1.5-3h | 实现聊天记录存储逻辑 | `services/chat_service.py` |
| 3-4.5h | 实现多用户隔离 | `middleware/user_isolation.py` |
| 4.5-5.5h | 数据库迁移脚本（Alembic） | `alembic/` |
| 5.5-6h | 完整回归测试 | 测试报告 |

**数据模型设计**:

```python
# models/base.py
"""数据库基础"""

from sqlalchemy import create_engine
from sqlalchemy.ext.declarative import declarative_base
from sqlalchemy.orm import sessionmaker

Base = declarative_base()

# 数据库连接（默认SQLite，生产用PostgreSQL）
engine = create_engine('sqlite:///WORKPLACE/clawdboz.db', echo=False)
SessionLocal = sessionmaker(bind=engine)


def get_db():
    """获取数据库会话"""
    db = SessionLocal()
    try:
        yield db
    finally:
        db.close()


# models/user.py
"""用户模型"""

from sqlalchemy import Column, String, DateTime, Integer
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base

class User(Base):
    """用户表"""
    __tablename__ = "users"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String(64), unique=True, nullable=False, index=True)
    name = Column(String(128))
    avatar = Column(String(512))
    created_at = Column(DateTime, default=datetime.utcnow)
    last_active = Column(DateTime, default=datetime.utcnow)
    
    # 关系
    chats = relationship("Chat", back_populates="user")
    memories = relationship("Memory", back_populates="user")


# models/chat.py
"""聊天模型"""

from sqlalchemy import Column, String, DateTime, Integer, ForeignKey, Text, JSON
from sqlalchemy.orm import relationship
from datetime import datetime
from .base import Base

class Chat(Base):
    """聊天会话表"""
    __tablename__ = "chats"
    
    id = Column(Integer, primary_key=True)
    chat_id = Column(String(64), nullable=False, index=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), nullable=False)
    chat_type = Column(String(16))  # group / p2p
    title = Column(String(256))
    created_at = Column(DateTime, default=datetime.utcnow)
    updated_at = Column(DateTime, default=datetime.utcnow)
    
    # 关系
    user = relationship("User", back_populates="chats")
    messages = relationship("Message", back_populates="chat", order_by="Message.created_at")


class Message(Base):
    """消息表"""
    __tablename__ = "messages"
    
    id = Column(Integer, primary_key=True)
    message_id = Column(String(64), unique=True, nullable=False, index=True)
    chat_id = Column(Integer, ForeignKey("chats.id"), nullable=False)
    sender_id = Column(String(64), nullable=False)
    sender_name = Column(String(128))
    msg_type = Column(String(32))  # text / image / file / card
    content = Column(Text)  # 文本内容或JSON
    content_path = Column(String(512))  # 图片/文件本地路径
    created_at = Column(DateTime, default=datetime.utcnow)
    
    # 关系
    chat = relationship("Chat", back_populates="messages")


# models/file.py
"""文件模型"""

from sqlalchemy import Column, String, DateTime, Integer, ForeignKey
from datetime import datetime
from .base import Base

class File(Base):
    """文件表"""
    __tablename__ = "files"
    
    id = Column(Integer, primary_key=True)
    file_key = Column(String(128), unique=True, nullable=False)
    file_name = Column(String(256))
    file_type = Column(String(64))
    local_path = Column(String(512))
    chat_id = Column(String(64), ForeignKey("chats.chat_id"))
    uploaded_by = Column(String(64))
    file_size = Column(Integer)
    created_at = Column(DateTime, default=datetime.utcnow)


# models/memory.py
"""记忆模型"""

from sqlalchemy import Column, String, DateTime, Integer, Text, ForeignKey
from datetime import datetime
from .base import Base

class Memory(Base):
    """长期记忆表"""
    __tablename__ = "memories"
    
    id = Column(Integer, primary_key=True)
    user_id = Column(String(64), ForeignKey("users.user_id"), nullable=False)
    chat_id = Column(String(64))
    category = Column(String(64), default="general")  # general / important / todo
    content = Column(Text, nullable=False)
    importance = Column(Integer, default=5)  # 1-10
    tags = Column(String(256))  # 逗号分隔的标签
    created_at = Column(DateTime, default=datetime.utcnow)
    accessed_at = Column(DateTime)
    access_count = Column(Integer, default=0)
    
    # 关系
    user = relationship("User", back_populates="memories")
```

**多用户隔离中间件**:

```python
# middleware/user_isolation.py
"""多用户隔离中间件"""

from contextvars import ContextVar
from typing import Optional

# 当前用户上下文
current_user_var: ContextVar[Optional[str]] = ContextVar('current_user', default=None)


class UserIsolationMiddleware:
    """用户隔离中间件"""
    
    def __init__(self):
        self.user_contexts = {}
    
    def set_current_user(self, user_id: str):
        """设置当前用户"""
        current_user_var.set(user_id)
    
    def get_current_user(self) -> Optional[str]:
        """获取当前用户"""
        return current_user_var.get()
    
    def isolate_chat_history(self, chat_id: str, user_id: str) -> list:
        """获取隔离的聊天记录"""
        # 只返回该用户有权限查看的记录
        pass


def require_user(func):
    """要求用户登录的装饰器"""
    def wrapper(*args, **kwargs):
        user = current_user_var.get()
        if not user:
            raise PermissionError("需要用户身份")
        return func(*args, **kwargs)
    return wrapper
```

### Day 3 检查清单

- [ ] 飞书文档插件可用
- [ ] 飞书表格插件可用
- [ ] 飞书任务插件可用
- [ ] 数据库表创建成功
- [ ] 聊天记录写入数据库
- [ ] 多用户隔离生效
- [ ] 完整回归测试通过
- [ ] Docker 镜像更新

---

## ⚠️ 风险与应对

| 风险点 | 影响 | 应对策略 |
|--------|:----:|----------|
| **Day 3 工作量过大** | 🔴 高 | 飞书插件拆分为 v2.3.0，先实现1个核心插件 |
| **数据库迁移风险** | 🔴 高 | 保留文件存储作为 fallback，渐进式迁移 |
| **MCP 调试复杂** | 🟡 中 | 每个 MCP Server 单独测试通过后再集成 |
| **飞书API权限审核** | 🟡 中 | 提前申请，Day 1 就开始申请流程 |
| **权限控制过度** | 🟡 中 | 默认宽松模式，需要时开启严格模式 |
| **定时任务冲突** | 🟢 低 | 使用锁机制防止任务重复执行 |

---

## 🔄 Plan B：分两期迭代

如果3天无法完成全部，建议分两期：

### v2.2.0（3天）- 核心基础

| 天数 | 内容 | 产出 |
|:----:|------|------|
| Day 1 | Docker + Pip 包 | 可部署的基础包 |
| Day 2 | 记忆 MCP + 定时任务 | 有记忆、能自主运行 |
| Day 3 | 数据库 + 多用户隔离 | 数据持久化、用户隔离 |

**API 目标**:
```python
from clawdboz import Bot

bot = Bot(app_id="xxx", app_secret="xxx")
bot.enable_memory()  # 启用长期记忆
bot.enable_scheduler()  # 启用定时任务
bot.run()
```

### v2.3.0（后续2-3天）- 高级功能

| 内容 | 说明 |
|------|------|
| 飞书全套插件 | 文档、表格、任务、日历 |
| 工作区/软件区权限 | 完整权限控制 |
| 插件市场 | 支持第三方插件 |

---

## 📁 新增文件清单

### Day 1 新增
```
Dockerfile
docker-compose.yml
pyproject.toml
src/simple_bot.py
```

### Day 2 新增
```
mcp/memory_server.py
src/security.py
src/scheduler.py
src/night_activities.py
src/long_task_queue.py
```

### Day 3 新增
```
plugins/
  ├── __init__.py
  ├── base.py
  ├── feishu_doc.py
  ├── feishu_sheet.py
  └── feishu_task.py
models/
  ├── __init__.py
  ├── base.py
  ├── user.py
  ├── chat.py
  ├── message.py
  ├── file.py
  └── memory.py
middleware/
  └── user_isolation.py
services/
  └── chat_service.py
alembic/
  ├── versions/
  └── env.py
```

---

## 📝 每日站会检查项

### Day 1 晚上
- [ ] Docker 镜像构建成功？
- [ ] `pip install -e .` 成功？
- [ ] 3行代码启动 Bot 可用？

### Day 2 晚上
- [ ] 记忆 MCP 可调用？
- [ ] 权限控制能阻止非法路径？
- [ ] 定时任务调度器运行？

### Day 3 晚上
- [ ] 至少1个飞书插件可用？
- [ ] 聊天记录存入数据库？
- [ ] 多用户隔离测试通过？
- [ ] 完整回归测试通过？

---

**规划完成，准备开始执行！** 🚀
