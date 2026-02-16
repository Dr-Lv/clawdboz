# 嗑唠的宝子 (Clawdboz) - 飞书 Bot

[![Version](https://img.shields.io/badge/version-2.2.0-blue.svg)](#)
[![Python](https://img.shields.io/badge/python-3.9+-green.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-yellow.svg)](#)

基于 Kimi Code CLI 的智能飞书机器人，OpenClaw 的平替，更适合代码任务，飞书丝滑适配，交互体验优化得很好。

## ✨ 核心亮点

- 🚀 **开箱即用**：`pip install` 后三行代码即可运行
- 🎯 **代码友好**：原生支持 Kimi Code CLI，代码编辑、文件操作、终端命令样样精通
- 💬 **飞书适配**：自动获取群聊上下文，流式卡片输出，体验丝滑

## 功能特性

| 特性 | 说明 |
|------|------|
| 🤖 **AI 对话** | 基于 Kimi Code CLI 的智能对话 |
| 📝 **流式回复** | 实时显示思考过程，Markdown 卡片美化输出 |
| 🔧 **MCP 工具** | 支持 MCP 协议调用外部工具，可搜索/安装/创建新工具 |
| 📦 **文件处理** | 自动下载图片/文件，支持发送文件到飞书 |
| 💬 **群聊适配** | 自动获取群聊历史，理解对话脉络 |
| 🔍 **运维监控** | 自动监控 Bot 状态，故障自动恢复 |

## 🚀 三行代码运行

```python
from clawdboz import Bot

bot = Bot(app_id="your-app-id", app_secret="your-app-secret")
bot.run()
```

就这么简单！

## 快速开始

### 1. 安装

```bash
pip install clawdboz
```

或从源码安装：

```bash
git clone <repository-url>
cd larkbot
pip install -e .
```

### 2. 启动 Bot

#### 方式一：三行代码（快速体验）

```python
from clawdboz import Bot

bot = Bot(app_id="your-app-id", app_secret="your-app-secret")
bot.run()
```

#### 方式二：使用 bot_manager.sh（推荐生产使用）

**1. 配置方式（二选一）**

方式 A - 环境变量（推荐）：
```bash
export FEISHU_APP_ID="cli_xxxxxxxxxxxxxxxx"
export FEISHU_APP_SECRET="xxxxxxxxxxxxxxxxxxxxxx"
```

方式 B - config.json：
```json
{
  "feishu": {
    "app_id": "cli_xxxxxxxxxxxxxxxx",
    "app_secret": "xxxxxxxxxxxxxxxxxxxxxx"
  }
}
```

**2. 管理命令**

```bash
# 启动 Bot
./bot_manager.sh start

# 停止 Bot
./bot_manager.sh stop

# 重启 Bot
./bot_manager.sh restart

# 查看状态
./bot_manager.sh status

# 查看日志（最后50行）
./bot_manager.sh log 50

# 实时跟踪日志
./bot_manager.sh follow

# 运维检查
./bot_manager.sh check
```

**3. 自定义启动脚本 bot0.py**

如果需要在 `bot0.py` 中添加自定义逻辑，创建该文件：

```python
#!/usr/bin/env python3
import os
from clawdboz import Bot

# 从环境变量或 config.json 读取配置
app_id = os.environ.get('FEISHU_APP_ID', 'your-app-id')
app_secret = os.environ.get('FEISHU_APP_SECRET', 'your-app-secret')

bot = Bot(app_id=app_id, app_secret=app_secret)
bot.run()
```

管理脚本会优先使用 `bot0.py`，如果不存在则使用内置模块启动。

## 项目结构

```
.
├── clawdboz/                   # 主包
│   ├── __init__.py             # 包入口
│   ├── simple_bot.py           # 简化版 Bot API
│   ├── bot.py                  # Bot 核心类
│   ├── acp_client.py           # ACP 客户端
│   ├── config.py               # 配置管理
│   ├── handlers.py             # 事件处理器
│   ├── main.py                 # 程序入口
│   ├── cli.py                  # 命令行工具
│   └── .kimi/                  # MCP 配置
│
├── feishu_tools/               # 飞书 MCP 工具
│   ├── mcp_feishu_file_server.py
│   └── notify_feishu.py
│
├── bot_manager.sh              # 管理脚本
├── pyproject.toml              # 打包配置
├── MANIFEST.in                 # 打包文件清单
└── README.md                   # 项目说明
```

## 飞书应用配置

### 1. 创建应用

1. 前往 [飞书开放平台](https://open.feishu.cn/) 登录开发者账号
2. 点击「开发者后台」→「创建企业自建应用」
3. 填写应用名称和描述，点击「创建」
4. 进入应用详情页，获取 **App ID** 和 **App Secret**

### 2. 配置权限

**需要的权限**:

| 权限类型 | 权限名称 | 用途 |
|---------|---------|------|
| API 权限 | `im:message:send` | 发送消息 |
| API 权限 | `im:message:send_as_bot` | 发送消息卡片 |
| API 权限 | `im:message:update` | 更新消息卡片 |
| API 权限 | `im:message.resource` | 获取图片、文件 |
| API 权限 | `im:chat:readonly` | 获取聊天记录 |
| API 权限 | `im:file:create` | 上传文件 |
| API 权限 | `im:file:send` | 发送文件消息 |
| API 权限 | `im:image:create` | 上传图片 |
| 事件订阅 | `im.message.receive_v1` | 接收消息 |
| 机器人能力 | `receive_message` | 接收消息 |
| 机器人能力 | `send_message` | 发送消息 |

1. 在应用详情页，点击「权限管理」→ 申请上述 API 权限
    备注：可通过feishu_permissions.json批量配置权限
2. 点击「事件与回调」→ 选择长连接方式，勾选所有事件和回调选项
    备注：初次配置长连接，需要先启动bot进行连接，才能在飞书后台配置成功
3. 点击「机器人」→ 开启「接收消息」和「发送消息」能力

### 3. 发布应用

1. 点击「版本管理与发布」→「创建版本」
2. 填写版本号（如 1.0.0）
3. 选择「可用性状态」为「所有员工」
4. 点击「保存」并「申请发布」

### 4. 添加机器人到聊天

- **单聊**：搜索机器人名称，进入对话
- **群聊**：群设置 →「群机器人」→ 添加机器人 → 在群聊中 @机器人

## 与 Bot 交互

- **单聊**：直接发送消息给 Bot
- **群聊**：在群聊中 @Bot 后发送消息
- **文件/图片**：Bot 自动下载到工作目录并分析
- **发送文件**：使用 MCP 工具发送本地文件到飞书

## 打包发布

```bash
# 清理并重新打包
rm -rf build/ dist/ *.egg-info
python3 -m build

# 生成的文件
# dist/clawdboz-2.2.0-py3-none-any.whl
# dist/clawdboz-2.2.0.tar.gz
```

## 许可证

MIT License
