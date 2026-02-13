# 嗑唠的宝子 - 代码架构

> **版本**: v2.0.0 | **架构**: 模块化包结构

## 项目结构

```
.
├── src/                          # Python 源代码目录
│   ├── __init__.py               # src 包初始化，导出所有公开接口
│   ├── config.py                 # 配置管理 (73 行)
│   ├── acp_client.py             # ACP 客户端 (569 行)
│   ├── bot.py                    # Bot 核心类 (916 行)
│   ├── handlers.py               # 事件处理器 (28 行)
│   └── main.py                   # 程序入口 (57 行)
│
├── clawdboz.py                   # 兼容入口，导入 src 包
├── feishu_tools/                 # 飞书工具目录
│   ├── mcp_feishu_file_server.py # MCP Server：文件发送
│   └── notify_feishu.py          # 飞书通知工具
│
├── bot_manager.sh                # Bot 管理脚本
├── config.json                   # 配置文件
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
**职责**：项目路径和配置管理

**导出内容**：
- `PROJECT_ROOT`: 项目根目录（全局）
- `CONFIG`: 配置字典（全局）
- `get_project_root()`: 获取项目根目录
- `load_config()`: 加载 config.json
- `get_absolute_path()`: 相对路径转绝对路径

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
  - `chat()`: 流式对话
  - `close()`: 关闭连接

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
  - `_handle_image_message()`: 处理图片
  - `_handle_file_message()`: 处理文件
  - `_get_chat_history()`: 获取聊天记录
  - 等等...

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
**职责**：程序入口

**导出内容**：
- `main()`: 主函数

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
| src/config.py | 73 | 配置管理 |
| src/acp_client.py | 569 | ACP 通信 |
| src/bot.py | 916 | 业务逻辑 |
| src/handlers.py | 28 | 事件处理 |
| src/main.py | 57 | 程序入口 |
| src/__init__.py | 25 | 包初始化 |
| clawdboz.py | 35 | 兼容入口 |
| **总计** | **1703** | - |

## 优点

1. **结构清晰**：所有源码放在 src/ 目录，符合 Python 项目规范
2. **易于维护**：每个模块职责单一
3. **便于测试**：可以单独测试每个模块
4. **代码复用**：其他项目可以只导入需要的模块
5. **向后兼容**：原有代码无需修改即可运行
6. **独立脚本**：feishu_tools/ 目录下的脚本仍可独立运行
