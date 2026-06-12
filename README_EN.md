<div align="center">

# Clawdboz (嗑唠的宝子)

[![Version](https://img.shields.io/badge/version-5.0.5-blue.svg)](#)
[![Python](https://img.shields.io/badge/python-3.10+-green.svg)](https://www.python.org/)
[![License](https://img.shields.io/badge/license-Source%20Open%20License-yellow.svg)](#-license)
[![Website](https://img.shields.io/badge/website-clawdboz.chat-blueviolet.svg)](https://clawdboz.chat)

**A multi-agent IM collaboration platform based on the ACP protocol**

<p>
  <a href="README.md">🇨🇳 中文</a> | 
  🇬🇧 English
</p>

</div>

---

Clawdboz is a multi-agent IM collaboration platform based on the ACP (Agent Client Protocol), supporting mainstream agents including OpenClaw, Hermes Agent, Claude Code, Opencode, and Kimi Code. It delivers a WeChat-like interactive experience, allowing you to quickly create local bots, publish them to remote instances, add bots from other servers, and chat with them. It also supports Feishu (Lark) integration.

## ✨ Highlights

- 🚀 **Out-of-the-box**: Run with just three lines of code after `pip install`
- 🤖 **Multi-Bot Collaboration**: Mix local and remote bots in group chats, trigger replies with @mentions
- 🌐 **Web Chat Interface**: Complete single-page application supporting single/group chats, file uploads, and image sending
- 🔗 **Remote Bot Discovery**: Discover bots from other instances through the registry center and call them across servers
- 💬 **Feishu (Lark) Integration**: Auto-fetch group chat context, stream cards output, silky smooth experience
- 🏠 **Session Management**: Switch between single and group chats, IndexedDB local cache + server-side persistence
- 🐳 **Docker Sandbox**: Remote bots execute in isolated containers, safe and controllable
- 🧠 **Thinking Mode**: Toggle display of AI reasoning process, real-time streaming responses

## 📺 Demo

<p float="left">
  <img src="https://raw.githubusercontent.com/Dr-Lv/clawdboz/main/clawdboz_demo.gif" width="48%" alt="Bot Conversation Demo" />
  <img src="https://raw.githubusercontent.com/Dr-Lv/clawdboz/main/clawdboz_demo2.gif" width="48%" alt="Code Execution Demo" />
</p>

> 🌐 **Try it online**: [https://clawdboz.chat](https://clawdboz.chat)

## Features

### Web Chat Features

| Feature | Description |
|---------|-------------|
| 🖥️ **Web UI** | Single-page application, responsive design, mobile-friendly |
| 💬 **Single/Group Chat** | One-on-one conversations and multi-bot group chats |
| 📎 **File Upload** | Support images, documents, and other file uploads with preview |
| 🧠 **Thinking Mode** | Toggle display of AI reasoning process |
| 📝 **Streaming Replies** | Real-time display of AI responses |
| 📋 **Session Management** | Create, rename, delete sessions, local cache sync |
| 👥 **Member Management** | Dynamically add/remove bots in group chats |
| 🔍 **Global Search** | Search bots and sessions |

### Remote Bot Features

| Feature | Description |
|---------|-------------|
| 🌍 **Registry Center** | Instance registration, bot publishing, heartbeat maintenance |
| 🔍 **Bot Discovery** | Real-time discovery of bots published by other instances |
| 🤝 **Friend System** | Instance-level friend requests/acceptance/removal |
| 📡 **Center Relay** | WebSocket center relay mode, P2P direct connection mode |
| 🐳 **Docker Sandbox** | Remote bots execute in isolated containers |
| 📞 **Remote Invocation** | Cross-instance bot calls with 120-second timeout |

### Feishu Bot Features

| Feature | Description |
|---------|-------------|
| 🤖 **AI Chat** | Intelligent dialogue based on Kimi Code CLI |
| 📝 **Streaming Replies** | Real-time reasoning display with Markdown card beautification |
| 🔧 **MCP Tools** | Support MCP protocol for external tools, built-in Feishu file/message sending |
| 📦 **File Processing** | Auto-download images/files, support sending files to Feishu |
| 💬 **Group Chat Adaptation** | Auto-fetch group chat history, understand conversation context |
| ⏰ **Scheduled Tasks** | Built-in task scheduling, support custom timed execution |

## 🏗️ Architecture

```
┌─────────────────────────────────────────────────────────────┐
│                     Registry Center                         │
│                  api.clawdboz.chat:443 (WSS)                │
│                  In-memory + WebSocket Relay                │
└─────────────────────────────────────────────────────────────┘
                              │
           ┌──────────────────┼──────────────────┐
           │                  │                  │
    ┌──────▼──────┐    ┌─────▼──────┐    ┌─────▼──────┐
    │  Local A    │    │  Host1     │    │  Others    │
    │  port 7011  │    │ port 6905  │    │  ...       │
    └──────┬──────┘    └─────┬──────┘    └─────┬──────┘
           │                  │                  │
    ┌──────▼──────┐    ┌─────▼──────┐    ┌─────▼──────┐
    │  Local Bots │    │ Docker     │    │  Local Bots│
    │  workplace_*│    │  sandbox   │    │  workplace_*│
    └─────────────┘    └────────────┘    └─────────────┘
```

- **Registry Center**: Maintains instance list, bot directory, friend relationships, message relay
- **Instance**: Each instance has a unique hostname-port ID, containing local bots and/or remote bot clients
- **Bot**: Local bots run directly; remote bots are called via registry center or direct connection, can execute in Docker sandbox

## 🚀 Quick Start

### Prerequisites

**⚠️ Please install [Kimi Code CLI](https://www.agents.com/code/docs/kimi-cli/guides/getting-started.html) first**

```bash
# Install via pip
pip install kimi-cli

# Or install via uv (recommended)
uv tool install --python 3.13 kimi-cli

# Verify installation
kimi --version
```

### 1. Install Clawdboz

```bash
pip install clawdboz
```

Or install from source:

```bash
git clone <repository-url>
cd clawdboz
pip install -e .
```

### 2. Initialize Project

```bash
mkdir my-bot && cd my-bot
clawdboz init
```

`clawdboz init` will automatically:
- ✅ Detect Kimi CLI installation and login status
- ✅ Create `config.json`, auto-fill Python path
- ✅ Create `.agents/mcp.json`, configure Feishu MCP tools
- ✅ Copy built-in Skills (scheduler, local-memory, find-skills)
- ✅ Create `bot_manager.sh` management script
- ✅ Create `bot0.py` startup script
- ✅ Create `.bots.md` Agent instruction file

### 3. Configure Remote Features (Optional)

Edit `config.json` to enable remote features:

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

### 4. Start Web Chat Server

```bash
# Method 1: Daemon mode (recommended for production)
clawdboz web start --config config.json

# Method 2: Foreground mode (for development/debugging)
clawdboz web --config config.json

# Method 3: Direct run
python web_server.py --port 8443 --host 0.0.0.0
```

Daemon management commands:

```bash
clawdboz web start   # Start daemon
clawdboz web stop    # Stop daemon
clawdboz web restart # Restart daemon
clawdboz web status  # Check daemon status
```

Visit `http://localhost:8443/static/index.html?token=your-token`

### 5. Start Feishu Bot (Optional)

```python
from clawdboz import Bot

bot = Bot(app_id="your-app-id", app_secret="your-app-secret")
bot.run()
```

Or use `bot_manager.sh`:

```bash
./bot_manager.sh start
```

## 📁 Project Structure

Project structure after running `clawdboz init`:

```
.
├── .agents/                    # Kimi CLI config directory
│   ├── mcp.json               # MCP config (auto-generated)
│   └── skills/                # Skills directory (auto-generated)
│       ├── find-skills/
│       ├── local-memory/
│       └── scheduler/
│
├── WORKPLACE/                  # Working directory (Bot workspace)
│   ├── workplace_bot1/        # Bot 1 workspace
│   ├── workplace_bot2/        # Bot 2 workspace
│   ├── .remote/               # Remote feature data
│   │   ├── published_bots.json
│   │   └── added_bots.json
│   ├── user_images/           # User image download directory
│   └── user_files/            # User file download directory
│
├── clawdboz/web/static/index.html  # Web Chat frontend (SPA)
├── web_server.py                   # Web server entry
│                                   # Note: registry_server.py source is on the central server
│
├── logs/                       # Log directory
│   ├── main.log
│   ├── bot_debug.log
│   └── feishu_api.log
│
├── .bots.md                    # Agent instruction file (auto-generated)
├── bot0.py                     # Startup script (auto-generated)
├── bot_manager.sh              # Management script (auto-generated)
└── config.json                 # Config file (auto-generated)
```

**Source Structure**:

```
clawdboz/                       # Python package
├── __init__.py
├── cli.py                      # CLI entry `clawdboz`
├── core/                       # Bot core
│   ├── bot.py                  # Bot base class
│   ├── bot_manager.py          # BotManager (registration, management)
│   └── simple_bot.py           # Simplified Bot API
├── web/                        # Web service
│   ├── server.py               # WebChatServer (FastAPI)
│   ├── chat/                   # Chat core
│   │   ├── core.py             # ChatCore (message processing, remote calls)
│   │   ├── history.py          # Chat history management
│   │   ├── mentions.py         # @mention parsing
│   │   ├── group.py            # Group chat logic
│   │   └── acp.py              # ACP client management
│   ├── routes/                 # API routes
│   │   ├── bots.py             # /api/bots
│   │   ├── websocket.py        # WebSocket connection management
│   │   ├── remote.py           # /api/remote/*
│   │   ├── sessions/           # Session-related routes
│   │   └── internal.py         # Internal API (e.g., server restart)
│   ├── static/                 # Frontend assets
│   │   ├── index.html          # Main UI (single file ~10K lines JS)
│   │   └── ...
│   └── workspace.py            # Workspace management
├── remote/                     # Remote features
│   ├── manager.py              # RemoteBotManager (core)
│   ├── registry_client.py      # Registry HTTP API client
│   ├── registry_ws_client.py   # Registry WebSocket client
│   ├── bot_publisher.py        # Bot publishing to Registry
│   ├── remote_client.py        # Remote Bot call client
│   ├── docker_sandbox.py       # Docker sandbox management
│   ├── friend_manager.py       # Friend relationship management
│   └── ...
├── communication/              # ACP communication layer
│   ├── acp_client.py
│   ├── websocket_acp_client.py
│   └── session_manager.py
└── utils/                      # Utilities
    └── logger.py
```

## 🖥️ Web Chat Guide

### Create Session

1. Click `+` or `...` in the top right → **New Session**
2. Select one or more bots
3. Select a single bot for **single chat**, multiple bots for **group chat**

### Group Chat @Mentions

- Type `@` in group chat to select a bot; only mentioned bots will reply
- Type `@all` or `@everyone` to mention all bots
- Without mentioning any bot, the message is saved but no reply is triggered

### Manage Group Members

- In group chat, click `...` in the top right → **Manage Members**
- You can remove existing bots (creator cannot be removed)
- You can add new available bots to the group

### File Upload

- Click the 📎 button on the left side of the input box to upload files
- Support images, documents, code files, etc.
- Bots will automatically analyze file content

## 🌍 Remote Bot Guide

### Publish Bot

1. Open **Contacts** in Web Chat
2. Find the local bot, click **Publish to Remote**
3. Set display name, description, whether to enable sandbox

### Add Remote Bot

1. View the **Online Instances** tab in Contacts
2. Browse bots published by other instances
3. Click **Add Friend** to send a friend request
4. After the other party accepts, the bot will appear in Contacts

### Invoke Remote Bot

- Remote bots appear in the bot list when creating sessions
- Directly @mention the remote bot in chat to invoke it
- Remote bot replies are displayed in real-time streaming

## 🤖 CLI Commands

### Bot Management

```bash
clawdboz bot list              # List all bots
clawdboz bot create <bot_id>   # Create bot
clawdboz bot info <bot_id>     # View bot details
clawdboz bot edit <bot_id>     # Edit bot
clawdboz bot delete <bot_id>   # Delete bot
```

### Session Management

```bash
clawdboz chat list                          # List all sessions
clawdboz chat create --bots bot1 --bots bot2 --name "Group Chat"  # Create session
clawdboz chat send <chat_id> "message"      # Send message
clawdboz chat interactive <chat_id>         # Interactive chat
```

### Contacts & Moments

```bash
clawdboz contacts list                      # List contacts
clawdboz moments list                       # View moments
clawdboz moments post "content"             # Post moment
```

## 💬 Feishu App Configuration

### 1. Create App

1. Go to [Feishu Open Platform](https://open.feishu.cn/) and log in with developer account
2. Click "Developer Console" → "Create Enterprise Self-built App"
3. Fill in app name and description, click "Create"
4. Enter app details page, get **App ID** and **App Secret**

### 2. Configure Permissions

**Required permissions**:

| Permission Type | Permission Name | Purpose |
|-----------------|-----------------|---------|
| API | `im:message:send` | Send messages |
| API | `im:message:send_as_bot` | Send message cards |
| API | `im:message:update` | Update message cards |
| API | `im:message.resource` | Get images, files |
| API | `im:chat:readonly` | Get chat history |
| API | `im:file:create` | Upload files |
| API | `im:file:send` | Send file messages |
| API | `im:image:create` | Upload images |
| Event | `im.message.receive_v1` | Receive messages |
| Bot | `receive_message` | Receive messages |
| Bot | `send_message` | Send messages |

### 3. Publish App

1. Click "Version Management & Release" → "Create Version"
2. Fill in version number (e.g., 1.0.0)
3. Select "Availability Status" as "All Employees"
4. Click "Save" and "Apply for Release"

## 🔧 Management Commands

```bash
# Start bot
./bot_manager.sh start

# Stop bot
./bot_manager.sh stop

# Restart bot
./bot_manager.sh restart

# Check status
./bot_manager.sh status

# View logs (last 50 lines)
./bot_manager.sh log 50

# Real-time log tracking
./bot_manager.sh follow

# Ops check
./bot_manager.sh check
```

### Scheduled Ops Monitoring (Recommended)

```bash
# Edit crontab
export EDITOR=vim && crontab -e

# Check every 30 minutes
*/30 * * * * cd /path/to/your/bot && ./bot_manager.sh check >/dev/null 2>&1
```

## 📦 Build & Release

```bash
# Clean and rebuild
rm -rf build/ dist/ *.egg-info
python3 -m build

# Generated files
# dist/clawdboz-5.0.4-py3-none-any.whl
# dist/clawdboz-5.0.4.tar.gz
```

## 📄 Documentation

| Document | Description |
|----------|-------------|
| `ARCHITECTURE.md` | Architecture analysis and optimization suggestions |
| `FEATURE.md` | Complete feature list |
| `REGISTRY_ARCHITECTURE.md` | Remote feature architecture |
| `CONNECT_TO_REGISTRY.md` | Registry connection guide |
| `REGISTRY_README.md` | Registry detailed documentation |
| `DEPLOYMENT_SUMMARY.md` | Deployment summary |
| `TESTING.md` | Testing guide |

## 📝 License

This project is licensed under the [**Source Open License**](LICENSE_SOURCE_OPEN.md).

The license is customized based on Apache License, Version 2.0, **not** the standard Apache 2.0 license. It retains core rights such as source code openness, free use, and redistribution, while setting commercial restrictions on remote friend features:

> **Without written authorization from the author (Dr-Lv), no individual or legal entity shall deploy, operate, maintain, or provide unofficial third-party servers in commercial scenarios using this project or its derivative works to support or replace remote bot discovery, friend relationships, registry center connections, message relay, and other remote friend-related features.**

Non-commercial use (personal learning, research, non-profit organization internal use, etc.) is not subject to this restriction.

For commercial licensing, please contact the author via Issues or official project channels.

