# 嗑唠的宝子 (Clawdboz) - 多 Bot 智能协作平台

[![Version](https://img.shields.io/badge/version-5.0.0-blue.svg)](#)
[![Python](https://img.shields.io/badge/python-3.9+-green.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-MIT-yellow.svg)](#)

基于 Kimi Code CLI 的智能多 Bot 协作平台，支持本地 Bot 管理、远程 Bot 发现调用、群聊协作、飞书集成。OpenClaw 的平替，更适合代码任务，飞书丝滑适配，交互体验优化得很好。

## ✨ 核心亮点

- 🚀 **开箱即用**：`pip install` 后三行代码即可运行
- 🤖 **多 Bot 协作**：支持本地 Bot + 远程 Bot 混合群聊，@提及触发回复
- 🌐 **Web Chat 界面**：完整的单页应用，支持单聊/群聊、文件上传、图片发送
- 🔗 **远程 Bot 发现**：通过注册中心发现其他实例的 Bot，跨服务器调用
- 💬 **飞书适配**：自动获取群聊上下文，流式卡片输出，体验丝滑
- 🏠 **会话管理**：单聊/群聊切换，IndexedDB 本地缓存 + 服务端持久化
- 🐳 **Docker 沙箱**：远程 Bot 在隔离容器中执行，安全可控

## 📺 演示

<p float="left">
  <img src="https://raw.githubusercontent.com/Dr-Lv/clawdboz/main/clawdboz_demo.gif" width="48%" alt="Bot 对话演示" />
  <img src="https://raw.githubusercontent.com/Dr-Lv/clawdboz/main/clawdboz_demo2.gif" width="48%" alt="代码执行演示" />
</p>

## 功能特性

### Web Chat 功能

| 特性 | 说明 |
|------|------|
| 🖥️ **Web 界面** | 单页应用，响应式设计，支持移动端 |
| 💬 **单聊/群聊** | 支持一对一对话和多 Bot 群聊 |
| 📎 **文件上传** | 支持图片、文档等文件上传和预览 |
| 🧠 **思考模式** | 可切换显示/隐藏 AI 思考过程 |
| 📝 **流式回复** | 实时显示 AI 回复内容 |
| 📋 **会话管理** | 创建、重命名、删除会话，本地缓存同步 |
| 👥 **成员管理** | 群聊中动态添加/移除 Bot |
| 🔍 **全局搜索** | 搜索 Bot 和会话 |

### 远程 Bot 功能

| 特性 | 说明 |
|------|------|
| 🌍 **注册中心** | 实例注册、Bot 发布、心跳维护 |
| 🔍 **Bot 发现** | 实时发现其他实例发布的 Bot |
| 🤝 **好友系统** | 实例级别好友请求/接受/移除 |
| 📡 **中心转发** | WebSocket 中心转发模式，P2P 直连模式 |
| 🐳 **Docker 沙箱** | 远程 Bot 在隔离容器中执行 |
| 📞 **远程调用** | 跨实例调用 Bot，120 秒超时 |

### 飞书 Bot 功能

| 特性 | 说明 |
|------|------|
| 🤖 **AI 对话** | 基于 Kimi Code CLI 的智能对话 |
| 📝 **流式回复** | 实时显示思考过程，Markdown 卡片美化输出 |
| 🔧 **MCP 工具** | 支持 MCP 协议调用外部工具，内置飞书文件/消息发送 |
| 📦 **文件处理** | 自动下载图片/文件，支持发送文件到飞书 |
| 💬 **群聊适配** | 自动获取群聊历史，理解对话脉络 |
| ⏰ **定时任务** | 内置定时任务调度，支持自定义定时执行 |

## 🏗️ 架构

```
┌─────────────────────────────────────────────────────────────┐
│                     注册中心 (Registry)                       │
│                  api.clawdboz.chat:443 (WSS)                │
│                    内存存储 + WebSocket 转发                 │
└─────────────────────────────────────────────────────────────┘
                              │
           ┌──────────────────┼──────────────────┐
           │                  │                  │
    ┌──────▼──────┐    ┌─────▼──────┐    ┌─────▼──────┐
    │  本地实例 A  │    │  host1 实例 │    │  其他实例   │
    │  port 7011  │    │ port 6905  │    │  ...       │
    └──────┬──────┘    └─────┬──────┘    └─────┬──────┘
           │                  │                  │
    ┌──────▼──────┐    ┌─────▼──────┐    ┌─────▼──────┐
    │  本地 Bots  │    │ Docker 沙箱 │    │  本地 Bots │
    │  workplace_*│    │  sandbox   │    │  workplace_*│
    └─────────────┘    └────────────┘    └─────────────┘
```

- **注册中心**：维护实例列表、Bot 目录、好友关系、消息转发
- **实例**：每个实例有独立的 hostname-port ID，包含本地 Bots 和/或远程 Bot 客户端
- **Bot**：本地 Bot 直接运行；远程 Bot 通过注册中心或直连调用，可在 Docker 沙箱中执行

## 🚀 快速开始

### 环境准备

**⚠️ 前置依赖：请先安装 [Kimi Code CLI](https://www.agents.com/code/docs/kimi-cli/guides/getting-started.html)**

```bash
# 通过 pip 安装
pip install kimi-cli

# 或使用 uv 安装（推荐）
uv tool install --python 3.13 kimi-cli

# 验证安装
kimi --version
```

### 1. 安装嗑唠的宝子

```bash
pip install clawdboz
```

或从源码安装：

```bash
git clone <repository-url>
cd clawdboz
pip install -e .
```

### 2. 初始化项目

```bash
mkdir my-bot && cd my-bot
clawdboz init
```

`clawdboz init` 会自动完成：
- ✅ 检测 Kimi CLI 安装和登录状态
- ✅ 创建 `config.json`，自动填入 Python 路径
- ✅ 创建 `.agents/mcp.json`，配置飞书 MCP 工具
- ✅ 复制内置 Skills（scheduler、local-memory、find-skills）
- ✅ 创建 `bot_manager.sh` 管理脚本
- ✅ 创建 `bot0.py` 启动脚本
- ✅ 创建 `.bots.md` Agent 指令文件

### 3. 配置远程功能（可选）

编辑 `config.json` 启用远程功能：

```json
{
  "project_root": "/path/to/my-bot",
  "webchat": {
    "port": 8443,
    "https": false,
    "token": "your-secret-token"
  },
  "remote": {
    "enabled": true,
    "registry_url": "https://api.clawdboz.chat",
    "instance_name": "My Instance",
    "host": "your-host",
    "port": 8443,
    "heartbeat_interval": 30,
    "connection_timeout": 10,
    "call_timeout": 120,
    "max_retries": 3,
    "sandbox": {
      "enabled": true,
      "docker": true,
      "max_memory_mb": 512,
      "timeout_seconds": 120
    },
    "connection_mode": "center",
    "registry_ws_url": "wss://api.clawdboz.chat/ws/registry"
  }
}
```

### 4. 启动 Web Chat 服务器

```bash
# 方式一：使用 CLI
clawdboz web --config config.json

# 方式二：直接运行
python web_server.py --port 8443 --host 0.0.0.0
```

访问 `http://localhost:8443/static/index.html?token=your-token`

### 5. 启动飞书 Bot（可选）

```python
from clawdboz import Bot

bot = Bot(app_id="your-app-id", app_secret="your-app-secret")
bot.run()
```

或使用 `bot_manager.sh`：

```bash
./bot_manager.sh start
```

## 📁 项目结构

运行 `clawdboz init` 后生成的项目结构：

```
.
├── .agents/                    # Kimi CLI 配置目录
│   ├── mcp.json               # MCP 配置（自动生成）
│   └── skills/                # Skills 目录（自动生成）
│       ├── find-skills/
│       ├── local-memory/
│       └── scheduler/
│
├── WORKPLACE/                  # 工作目录（Bot workspace）
│   ├── workplace_bot1/        # Bot 1 工作目录
│   ├── workplace_bot2/        # Bot 2 工作目录
│   ├── .remote/               # 远程功能数据
│   │   ├── published_bots.json
│   │   └── added_bots.json
│   ├── user_images/           # 用户图片下载目录
│   └── user_files/            # 用户文件下载目录
│
├── web/static/index.html       # Web Chat 前端（单页应用）
├── web_server.py               # Web 服务器入口
├── registry_server.py          # 注册中心服务器（可选独立部署）
│
├── logs/                       # 日志目录
│   ├── main.log
│   ├── bot_debug.log
│   └── feishu_api.log
│
├── .bots.md                    # Agent 指令文件（自动生成）
├── bot0.py                     # 启动脚本（自动生成）
├── bot_manager.sh              # 管理脚本（自动生成）
└── config.json                 # 配置文件（自动生成）
```

**源码结构**：

```
clawdboz/                       # 主包
├── __init__.py
├── simple_bot.py               # 简化版 Bot API
├── bot.py                      # Bot 核心类
├── cli.py                      # 命令行工具
├── web/                        # Web 服务
│   ├── server.py               # Web 服务器
│   ├── chat/core.py            # 聊天核心
│   ├── routes/                 # API 路由
│   └── static/index.html       # 前端界面
├── remote/                     # 远程功能
│   ├── manager.py              # 远程 Bot 管理器
│   ├── registry_client.py      # 注册中心客户端
│   ├── registry_ws_client.py   # 注册中心 WebSocket
│   ├── remote_client.py        # 远程 Bot 客户端
│   ├── bot_publisher.py        # Bot 发布器
│   ├── friend_manager.py       # 好友管理
│   └── docker_sandbox.py       # Docker 沙箱
└── .agents/                    # 内置 Skills 模板
    └── skills/
```

## 🖥️ Web Chat 使用指南

### 创建会话

1. 点击右上角 `+` 或 `...` → **新建会话**
2. 选择一个或多个 Bot
3. 选择单个 Bot 创建**单聊**，选择多个 Bot 创建**群聊**

### 群聊 @提及

- 在群聊中输入 `@` 选择 Bot，只有被 @ 的 Bot 会回复
- 输入 `@all` 或 `@所有人` 提及所有 Bot
- 不 @ 任何 Bot 时，只保存消息不触发回复

### 管理群成员

- 在群聊中点击右上角 `...` → **管理群成员**
- 可以移除现有 Bot（创建者不可移除）
- 可以添加新的可用 Bot 到群聊

### 文件上传

- 点击输入框左侧的 📎 按钮上传文件
- 支持图片、文档、代码文件等
- Bot 会自动分析文件内容

## 🌍 远程 Bot 使用指南

### 发布 Bot

1. 在 Web Chat 中打开**通讯录**
2. 找到本地 Bot，点击 **发布到远程**
3. 设置显示名称、描述、是否启用沙箱

### 添加远程 Bot

1. 在通讯录中查看**在线实例**标签
2. 浏览其他实例发布的 Bot
3. 点击 **添加好友** 发送好友请求
4. 对方接受后，Bot 会出现在通讯录中

### 调用远程 Bot

- 在创建会话时，远程 Bot 会出现在 Bot 列表中
- 聊天时直接 @提及远程 Bot 即可调用
- 远程 Bot 的回复会实时流式显示

## 🤖 CLI 命令行工具

### Bot 管理

```bash
clawdboz bot list              # 列出所有 Bot
clawdboz bot create <bot_id>   # 创建 Bot
clawdboz bot info <bot_id>     # 查看 Bot 详情
clawdboz bot edit <bot_id>     # 编辑 Bot
clawdboz bot delete <bot_id>   # 删除 Bot
```

### 会话管理

```bash
clawdboz chat list                          # 列出所有会话
clawdboz chat create --bots bot1 --bots bot2 --name "群聊"  # 创建会话
clawdboz chat send <chat_id> "消息"          # 发送消息
clawdboz chat interactive <chat_id>         # 交互式聊天
```

### 朋友圈

```bash
clawdboz contacts list                      # 列出联系人
clawdboz moments list                       # 查看朋友圈
clawdboz moments post "内容"                # 发布动态
```

## 📡 注册中心部署

### 快速部署

```bash
# 使用部署脚本
./deploy_registry.sh
```

或手动部署：

```bash
# 启动注册服务器
./start_registry.sh

# 或使用 uvicorn
python -m uvicorn registry_server:app --host 0.0.0.0 --port 6902
```

### 注册中心 API

| 端点 | 方法 | 说明 |
|------|------|------|
| `/api/registry/register` | POST | 注册实例 |
| `/api/registry/heartbeat` | POST | 实例心跳 |
| `/api/registry/bots` | GET | 发现所有 Bot |
| `/api/registry/discover` | GET | 发现实例 |
| `/api/registry/friend-request` | POST | 发送好友请求 |
| `/api/registry/friend-accept` | POST | 接受好友请求 |

## 💬 飞书应用配置

### 1. 创建应用

1. 前往 [飞书开放平台](https://open.feishu.cn/) 登录开发者账号
2. 点击「开发者后台」→「创建企业自建应用」
3. 填写应用名称和描述，点击「创建」
4. 进入应用详情页，获取 **App ID** 和 **App Secret**

### 2. 配置权限

**需要的权限**：

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

### 3. 发布应用

1. 点击「版本管理与发布」→「创建版本」
2. 填写版本号（如 1.0.0）
3. 选择「可用性状态」为「所有员工」
4. 点击「保存」并「申请发布」

## 🔧 管理命令

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

### 定时运维监控（推荐）

```bash
# 编辑 crontab
export EDITOR=vim && crontab -e

# 每 30 分钟检查一次
*/30 * * * * cd /path/to/your/bot && ./bot_manager.sh check >/dev/null 2>&1
```

## 📦 打包发布

```bash
# 清理并重新打包
rm -rf build/ dist/ *.egg-info
python3 -m build

# 生成的文件
# dist/clawdboz-2.7.5-py3-none-any.whl
# dist/clawdboz-2.7.5.tar.gz
```

## 📄 相关文档

| 文档 | 说明 |
|------|------|
| `ARCHITECTURE.md` | 架构分析和优化建议 |
| `FEATURE.md` | 完整功能清单 |
| `REGISTRY_ARCHITECTURE.md` | 远程功能架构说明 |
| `CONNECT_TO_REGISTRY.md` | 连接注册中心配置指南 |
| `REGISTRY_README.md` | 注册中心详细文档 |
| `DEPLOYMENT_SUMMARY.md` | 部署总结 |
| `TESTING.md` | 测试指南 |

## 📝 许可证

MIT License
