# 嗑唠的宝子 (Clawdboz) - 飞书 Bot

[![Version](https://img.shields.io/badge/version-2.0.0-blue.svg)](CHANGELOG.md)
[![Python](https://img.shields.io/badge/python-3.10+-green.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-yellow.svg)](LICENSE)

基于 Kimi Code CLI 的智能飞书机器人，支持 MCP 工具调用、文件发送和图片处理。

> 📦 **当前版本**: v2.0.0 - 模块化架构重构
> 
> 📝 [查看更新日志](CHANGELOG.md) | 🏗️ [查看架构文档](docs/ARCHITECTURE.md) | 📋 [查看项目文档](docs/PRJ.md)

## 功能特性

- 🤖 **AI 对话**：基于 Kimi Code CLI 的智能对话
- 🔧 **MCP 工具**：支持通过 MCP 协议调用外部工具
- 📁 **文件发送**：支持发送文件到飞书聊天
- 🖼️ **图片处理**：接收并处理用户发送的图片
- 📝 **流式回复**：实时显示思考和工具调用过程
- 🔍 **运维检查**：自动监控 Bot 状态并修复异常

## 项目结构

```
.
├── src/                          # Python 源代码目录
│   ├── __init__.py               # 包初始化，导出所有接口
│   ├── config.py                 # 配置管理
│   ├── acp_client.py             # ACP 客户端（Kimi 通信）
│   ├── bot.py                    # Bot 核心类
│   ├── handlers.py               # 事件处理器
│   └── main.py                   # 程序入口
│
├── clawdboz.py                   # 兼容入口（导入 src 包）
├── feishu_tools/                 # 飞书工具目录
│   ├── mcp_feishu_file_server.py # MCP Server：文件发送
│   └── notify_feishu.py          # 飞书通知工具
├── bot_manager.sh                # Bot 管理脚本
├── config.json                   # 配置文件
├── requirements.txt              # Python 依赖
├── docs/                         # 文档目录
│   ├── PRJ.md                    # 项目文档
│   ├── ARCHITECTURE.md           # 架构文档
│   └── feishu_permissions.json   # 飞书权限配置
├── AGENTS.md                     # Bot 系统提示词
├── docs/                         # 文档目录
│   ├── PRJ.md                    # 项目文档
│   └── ARCHITECTURE.md           # 架构文档
└── README.md                     # 项目说明

其他目录：
├── WORKPLACE/                    # 工作目录（临时文件、用户上传）
├── logs/                         # 日志目录
├── test_script/                  # 测试脚本
└── .kimi/                        # MCP 配置
```

## 安装步骤

### 1. 克隆项目

```bash
git clone <repository-url>
cd larkbot
```

### 2. 创建虚拟环境

```bash
python3 -m venv .venv
source .venv/bin/activate  # Linux/Mac
# 或
.venv\Scripts\activate     # Windows
```

### 3. 安装依赖

```bash
pip install -r requirements.txt
```

### 4. 配置飞书应用

#### 4.1 创建应用

1. 前往 [飞书开放平台](https://open.feishu.cn/) 登录开发者账号
2. 点击「开发者后台」→「创建企业自建应用」
3. 填写应用名称和描述，点击「创建」
4. 进入应用详情页，获取 **App ID** 和 **App Secret**

#### 4.2 配置权限

项目提供了 `docs/feishu_permissions.json` 权限配置文件，可用于**一键批量导入权限配置**。

**使用配置文件批量导入权限：**

1. 打开飞书开放平台 → 进入你的应用 →「权限管理」
2. 点击「批量导入」（如有此功能）或参考配置文件中的权限列表
3. 配置文件包含：
   - **API 权限**：发送消息、更新卡片、上传文件等
   - **事件订阅**：接收消息、消息已读等
   - **机器人能力**：接收和发送消息

**配置文件内容预览：**
```json
{
  "permissions": {
    "api_permissions": [
      "im:message:send",      // 发送消息
      "im:message:update",    // 更新消息卡片
      "im:file:create",       // 上传文件
      ...
    ],
    "event_subscriptions": [
      "im.message.receive_v1",  // 接收消息
      ...
    ]
  }
}
```

> 💡 **提示**：详细权限清单和配置步骤请参考 `docs/feishu_permissions.json` 文件

**手动配置步骤（如无法批量导入）：**

| 权限类型 | 权限名称 | 用途 |
|---------|---------|------|
| API 权限 | `im:message:send` | 发送消息 |
| API 权限 | `im:message:send_as_bot` | 发送消息卡片 |
| API 权限 | `im:message:update` | 更新消息卡片 |
| API 权限 | `im:message.resource` | 获取图片、文件 |
| API 权限 | `im:chat:readonly` | 获取聊天记录 |
| API 权限 | `im:file:create` | 上传文件 |
| API 权限 | `im:file:send` | 发送文件消息 |
| 事件订阅 | `im.message.receive_v1` | 接收消息 |
| 事件订阅 | `im.message.message_read_v1` | 消息已读 |
| 机器人能力 | `receive_message` | 接收消息 |
| 机器人能力 | `send_message` | 发送消息 |

1. 在应用详情页，点击「权限管理」→ 申请上述 API 权限
2. 点击「事件订阅」→ 添加订阅上述事件
3. 点击「机器人」→ 开启「接收消息」和「发送消息」能力

#### 4.3 发布应用

1. 点击「版本管理与发布」→「创建版本」
2. 填写版本号（如 1.0.0）
3. 选择「可用性状态」为「所有员工」
4. 点击「保存」并「申请发布」

#### 4.4 添加机器人到聊天

**单聊**：搜索机器人名称，进入对话

**群聊**：群设置 →「群机器人」→ 添加机器人 → 在群聊中 @机器人

### 5. 配置项目

编辑 `config.json`，填入飞书应用凭证：

```json
{
  "project_root": ".",
  "feishu": {
    "app_id": "your-app-id",
    "app_secret": "your-app-secret"
  },
  "qveris": {
    "api_key": "your-qveris-api-key"
  },
  "logs": {
    "main_log": "logs/main.log",
    "debug_log": "logs/bot_debug.log",
    "feishu_api_log": "logs/feishu_api.log",
    "ops_log": "logs/ops_check.log"
  },
  "paths": {
    "workplace": "WORKPLACE",
    "mcp_config": ".kimi/mcp.json"
  }
}
```

### 6. 初始化项目

```bash
./bot_manager.sh init --auto
```

### 7. 启动 Bot

```bash
# 推荐方式
python -m src.main

# 或使用管理脚本
./bot_manager.sh start
```

## 使用说明

### Bot 管理命令

```bash
# 初始化配置
./bot_manager.sh init

# 启动 Bot
./bot_manager.sh start

# 停止 Bot
./bot_manager.sh stop

# 重启 Bot
./bot_manager.sh restart

# 查看状态
./bot_manager.sh status

# 检查并自动修复异常
./bot_manager.sh check

# 查看日志
./bot_manager.sh log 50

# 实时跟踪日志
./bot_manager.sh follow
```

### 与 Bot 交互

**单聊**：直接发送消息给 Bot

**群聊**：在群聊中 @Bot 后发送消息

**发送文件**：用户可以在 WORKPLACE 目录中放置文件，然后让 Bot 发送到飞书

**处理图片**：直接发送图片给 Bot，Bot 会保存并询问如何处理

## 开发指南

### 导入模块

```python
# 从 src 包导入（推荐）
from src import LarkBot, CONFIG
from src.bot import LarkBot
from src.config import get_absolute_path

# 向后兼容
from clawdboz import LarkBot
```

### 项目架构

详见 [ARCHITECTURE.md](docs/ARCHITECTURE.md)

```
src/main.py ──► src/bot.py ──► src/acp_client.py ──► src/config.py
              │
              ▼
        src/handlers.py
```

## 定时任务

配置每 30 分钟自动执行运维检查：

```bash
crontab -e
```

添加：

```cron
*/30 * * * * cd /project/larkbot && ./bot_manager.sh check >> /project/larkbot/logs/cron_check.log 2>&1
```

## 日志文件

| 日志文件 | 说明 |
|---------|------|
| `logs/main.log` | Bot 主日志 |
| `logs/bot_debug.log` | 调试日志 |
| `logs/feishu_api.log` | 飞书 API 调用日志 |
| `logs/ops_check.log` | 运维检查日志 |

## 许可证

[Your License Here]
