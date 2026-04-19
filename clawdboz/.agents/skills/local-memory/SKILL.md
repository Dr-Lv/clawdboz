---
name: local-memory
description: Local memory management for persistent conversation context and information storage. Enables saving, retrieving, and managing memories with keyword and semantic search capabilities.
triggers:
  - pattern: "记住|保存|记下来|存档"
    description: "Detect save memory intent"
  - pattern: "回忆|查找|搜索记忆|之前说过"
    description: "Detect memory retrieval intent"
  - pattern: "忘记|删除记忆|清除"
    description: "Detect delete memory intent"
  - pattern: "记忆|历史|上下文"
    description: "Detect memory management queries"
auto_invoke: false
examples:
  - "记住我的邮箱是 example@mail.com"
  - "查找之前关于 Python 的讨论"
  - "删除所有包含密码的记忆"
  - "总结我们的对话历史"
---

# Local Memory Management

本地记忆管理工具，支持持久化存储对话上下文和关键信息，提供关键词搜索和语义检索功能。

## Features

- 💾 **记忆保存**: 保存重要信息、对话片段、用户偏好等
- 🔍 **智能检索**: 支持关键词搜索和语义相似度匹配
- 🗂️ **分类管理**: 按类别、标签组织记忆
- 🧹 **记忆维护**: 删除、更新、清理过期记忆
- 📊 **记忆统计**: 查看记忆库使用情况和统计信息

## Quick Start

### 保存记忆
```python
from local_memory import MemoryManager

memory = MemoryManager()
memory.save(
    content="用户的邮箱是 example@mail.com",
    category="user_info",
    tags=["email", "contact"],
    importance=5
)
```

### 检索记忆
```python
# 关键词搜索
results = memory.search("邮箱")

# 语义搜索
results = memory.search_similar("联系方式", top_k=5)
```

### 管理记忆
```python
# 删除记忆
memory.delete(memory_id="xxx")

# 清理旧记忆
memory.cleanup(days=30)

# 获取统计
stats = memory.get_stats()
```

## CLI Usage

```bash
# 保存记忆
python -m local_memory save "内容" --category general --tags tag1,tag2

# 搜索记忆
python -m local_memory search "关键词"

# 语义搜索
python -m local_memory similar "查询内容" --top-k 5

# 列出所有记忆
python -m local_memory list --limit 20

# 删除记忆
python -m local_memory delete <memory_id>

# 清理旧记忆
python -m local_memory cleanup --days 30

# 导出记忆
python -m local_memory export --output memories.json

# 导入记忆
python -m local_memory import --input memories.json
```

## API Reference

### MemoryManager

```python
class MemoryManager:
    def save(self, content: str, category: str = "general", 
             tags: list = None, importance: int = 3) -> str:
        """保存记忆，返回 memory_id"""
        
    def search(self, keyword: str, category: str = None) -> list:
        """关键词搜索"""
        
    def search_similar(self, query: str, top_k: int = 5) -> list:
        """语义相似度搜索"""
        
    def get(self, memory_id: str) -> dict:
        """获取单个记忆"""
        
    def delete(self, memory_id: str) -> bool:
        """删除记忆"""
        
    def update(self, memory_id: str, **kwargs) -> bool:
        """更新记忆"""
        
    def list_all(self, category: str = None, limit: int = 100) -> list:
        """列出所有记忆"""
        
    def cleanup(self, days: int = 30) -> int:
        """清理指定天数前的记忆，返回删除数量"""
        
    def get_stats(self) -> dict:
        """获取记忆库统计"""
```

## Use Cases

- **用户信息记忆**: 保存用户偏好、联系方式、历史需求
- **对话上下文**: 记录重要对话片段，支持长程上下文理解
- **知识积累**: 保存学习笔记、代码片段、解决方案
- **任务追踪**: 记录待办事项、项目进度、决策记录
- **偏好学习**: 记忆用户交互习惯，提供个性化体验

## Storage

默认存储位置: `~/.local/share/local-memory/`
- `memories.db`: SQLite 主数据库
- `embeddings/`: 语义向量缓存
- `exports/`: 导出文件目录
