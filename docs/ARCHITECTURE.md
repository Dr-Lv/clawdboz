# 嗑唠的宝子 - 代码架构

> **版本**: v2.1.0 | **架构**: 模块化包结构

## 项目结构

```
.
├── src/                          # Python 源代码目录
│   ├── __init__.py               # src 包初始化，导出所有公开接口
│   ├── config.py                 # 配置管理 (支持 .env、环境变量、config.json)
│   ├── acp_client.py             # ACP 客户端 (与 Kimi 通信，日志优化)
│   ├── bot.py                    # Bot 核心类 (含聊天记录、图片/文件下载)
│   ├── handlers.py               # 事件处理器
│   └── main.py                   # 程序入口 (带 WebSocket 监控)
│
├── clawdboz.py                   # 兼容入口，导入 src 包
├── feishu_tools/                 # 飞书工具目录
│   ├── mcp_feishu_file_server.py # MCP Server：文件发送
│   └── notify_feishu.py          # 飞书通知工具
│
├── bot_manager.sh                # Bot 管理脚本
├── config.json                   # 一般配置文件（非敏感）
├── .env                          # 敏感信息配置（不提交 Git）
├── requirements.txt              # Python 依赖
│
├── docs/                         # 文档目录
│   ├── PRJ.md                    # 项目文档
│   └── ARCHITECTURE.md           # 本文档
│
├── AGENTS.md                     # Bot 系统提示词
├── README.md                     # 项目说明
│
├── WORKPLACE/                    # 工作目录
├── logs/                         # 日志目录
├── test_script/                  # 测试脚本
└── .kimi/                        # MCP 配置
```

## 模块说明

### src/ 包

核心代码全部放在 `src/` 目录下，作为一个 Python 包管理。

#### src/config.py
**职责**：配置管理（支持多源配置）

**功能**：
- 从 `config.json` 加载一般配置
- 从 `.env` 文件加载敏感配置
- 从环境变量读取配置（优先级最高）
- 配置验证（检查必要字段）

**导出内容**：
- `PROJECT_ROOT`: 项目根目录（全局）
- `CONFIG`: 配置字典（全局，已合并所有来源）
- `get_project_root()`: 获取项目根目录
- `load_config()`: 加载并合并配置
- `get_absolute_path()`: 相对路径转绝对路径

**配置优先级**：环境变量 > .env 文件 > config.json

**依赖**：无（最底层模块）

---

#### src/acp_client.py
**职责**：与 Kimi Code CLI 的 ACP 协议通信

**导出内容**：
- `ACPClient`: ACP 客户端类
  - `__init__(bot_ref)`: 初始化
  - `_load_mcp_config()`: 加载 MCP 配置
  - `_load_skills()`: 加载 Skills
  - `call_method()`: 调用 ACP 方法
  - `chat()`: 流式对话（日志已优化）
  - `close()`: 关闭连接

**日志优化**：
- 禁用流式输出日志（减少噪声）
- 保留关键日志：Prompt 发送、错误响应

**依赖**：`src.config`

---

#### src/bot.py
**职责**：飞书 Bot 业务逻辑

**导出内容**：
- `LarkBot`: Bot 核心类
  - `__init__()`: 初始化
  - `on_message()`: 消息处理入口
  - `run_msg_script_streaming()`: 流式 AI 调用
  - `reply_text()`: 发送消息
  - `update_card()`: 更新卡片
  - `_handle_image_message()`: 处理图片消息
  - `_handle_file_message()`: 处理文件消息
  - `_get_chat_history()`: 获取聊天记录（支持图片/文件）
  - `_download_chat_image()`: 下载群聊图片
  - `_download_chat_file()`: 下载群聊文件
  - `_find_local_image_by_key()`: 根据 key 查找本地图片
  - 等等...

**聊天记录增强**：
- 返回字典格式：`{'type': 'text'|'image'|'file', 'sender': 'xxx', 'content': 'xxx'}`
- 自动下载用户发送的图片/文件
- 将本地路径包含在 prompt 中

**依赖**：`src.config`, `src.acp_client`

---

#### src/handlers.py
**职责**：飞书事件回调处理

**导出内容**：
- `do_card_action_trigger()`: 卡片按钮点击
- `do_url_preview_get()`: 链接预览
- `do_bot_p2p_chat_entered()`: 进入单聊
- `do_message_read()`: 消息已读

**依赖**：`lark_oapi`

---

#### src/main.py
**职责**：程序入口（带 WebSocket 监控）

**导出内容**：
- `main()`: 主函数
- `MonitoredWSClient`: 带监控的 WebSocket 客户端类
  - 心跳失败计数
  - 连接/断开/重连事件记录
  - 连续 10 次心跳失败触发 ERROR 告警

**依赖**：`src.config`, `src.bot`, `src.handlers`

---

#### src/__init__.py
**职责**：包初始化，统一导出所有公开接口

```python
from src import (
    PROJECT_ROOT,
    CONFIG,
    LarkBot,
    ACPClient,
    main,
    # ...
)
```

### 根目录文件

#### .env
**职责**：存放敏感信息

**内容示例**：
```bash
FEISHU_APP_ID=cli_xxxxx
FEISHU_APP_SECRET=xxxxx
QVERIS_API_KEY=sk-xxxxx
```

**注意**：此文件已添加到 `.gitignore`，不会被提交到 Git。

#### clawdboz.py
**职责**：向后兼容入口

```python
# 从 src 包导入所有接口
from src import PROJECT_ROOT, CONFIG, LarkBot, ...

if __name__ == "__main__":
    main()
```

**使用方式**：
```bash
python clawdboz.py          # 向后兼容
python -m src.main          # 推荐方式
```

#### feishu_tools/ 目录
**职责**：飞书相关工具脚本

- `mcp_feishu_file_server.py`: MCP Server，处理文件发送
- `notify_feishu.py`: 飞书通知工具，用于运维通知

这两个文件从 `src.config` 导入配置，保持独立运行能力。

## 数据流

### 消息处理流程

```
用户发送消息
    │
    ▼
飞书服务器 ──► src/main.py (WebSocket)
    │
    ▼
src/handlers.py ──► bot.on_message()
    │
    ▼
src/bot.py
    ├── 获取聊天记录 (_get_chat_history)
    │   ├── 下载图片 (_download_chat_image)
    │   └── 下载文件 (_download_chat_file)
    ├── 构建 Prompt (含本地路径)
    └── 调用 ACP
        │
        ▼
    src/acp_client.py ──► Kimi Code CLI
        │
        ▼
    流式响应 ──► 更新飞书卡片
```

### 配置加载流程

```
启动时加载配置
    │
    ├──► 读取 config.json (一般配置)
    │
    ├──► 读取 .env 文件 (敏感配置)
    │
    ├──► 读取环境变量 (覆盖前两者)
    │
    └──► 验证必要字段
         │
         ▼
    合并后的 CONFIG 字典
```

## 依赖关系

```
src/main.py ──► src/bot.py ──► src/acp_client.py ──► src/config.py
              │                                    
              ▼                                    
        src/handlers.py                            
                                                      
clawdboz.py ──► src (所有模块)                       
                                                      
feishu_tools/mcp_feishu_file_server.py ──► src.config          
                                                      
feishu_tools/notify_feishu.py ──► src.config                   
```

## 使用方式

### 启动 Bot

```bash
# 推荐方式
python -m src.main

# 向后兼容
python clawdboz.py

# 使用 bot_manager
./bot_manager.sh start
```

### 导入模块

```python
# 从 src 包导入（推荐）
from src import LarkBot, CONFIG
from src.bot import LarkBot
from src.config import get_absolute_path

# 从根目录导入（向后兼容）
from clawdboz import LarkBot
```

### 独立脚本

```python
# feishu_tools/ 目录下的脚本
# 自动从 src.config 导入配置
```

## 代码统计

| 模块 | 行数 | 职责 |
|------|------|------|
| src/config.py | ~150 | 配置管理（支持 .env） |
| src/acp_client.py | ~570 | ACP 通信（日志优化） |
| src/bot.py | ~1100 | 业务逻辑（聊天记录增强） |
| src/handlers.py | ~30 | 事件处理 |
| src/main.py | ~120 | 程序入口（WebSocket 监控） |
| src/__init__.py | ~25 | 包初始化 |
| clawdboz.py | ~35 | 兼容入口 |
| **总计** | **~2000** | - |

## 关键设计

### 1. 配置分层
- **非敏感配置** → `config.json`（提交 Git）
- **敏感配置** → `.env` 文件（不提交 Git）
- **运行时覆盖** → 环境变量（最高优先级）

### 2. 聊天记录处理
- 返回结构化字典，支持多种消息类型
- 图片/文件自动下载到本地
- 本地路径传递给 ACP，Kimi 可直接读取

### 3. WebSocket 监控
- 继承 SDK Client，添加监控逻辑
- 心跳失败计数，触发告警
- 连接状态记录到 `logs/main.log`

### 4. 日志分级
- `logs/main.log` - WebSocket 连接状态
- `logs/bot_debug.log` - Bot 业务调试
- `logs/bot_output.log` - 标准输出
- `logs/feishu_api.log` - API 调用

## 优点

1. **结构清晰**：所有源码放在 src/ 目录，符合 Python 项目规范
2. **配置安全**：敏感信息隔离在 .env 文件，不提交 Git
3. **功能增强**：聊天记录支持图片/文件，Prompt 更丰富
4. **稳定可靠**：WebSocket 监控，自动重连，故障告警
5. **易于维护**：每个模块职责单一
6. **便于测试**：可以单独测试每个模块
7. **向后兼容**：原有代码无需修改即可运行
