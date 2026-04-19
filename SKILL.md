# Clawdboz 部署指南

> 本指南帮助你在任何环境中部署 **嗑唠的宝子 (Clawdboz)** 飞书 Bot。
>
> 适用对象：AI Agent / 开发者 / 运维人员

---

## 1. 项目简介

**Clawdboz** 是基于 ACP 协议的多 Agent 智能飞书机器人，支持：

- **Kimi Code CLI**（默认）
- **OpenCode**
- **Claude Code**（via `claude-code-acp`）
- **OpenClaw**（via `openclaw-acp`）
- **Hermes Agent**

通过飞书 WebSocket 长连接接收消息，调用 ACP Agent 处理并流式回复。

---

## 2. 前置条件

### 2.1 系统环境

| 要求     | 版本/说明              |
| -------- | ---------------------- |
| Python   | >= 3.9                 |
| 操作系统 | Linux / macOS / Windows (WSL) |
| 网络     | 可访问飞书开放平台     |

### 2.2 安装至少一种 ACP Agent

> 💡 **推荐原则**：选择你**当前正在使用、最熟悉的 Agent**来构建 Bot，无需为了 Bot 而切换 Agent。

---

**1. Kimi Code CLI（推荐，默认）**

Kimi Code CLI 原生支持 ACP 协议，开箱即用。

```bash
# 安装
pip install kimi-cli
# 或
uv tool install --python 3.13 kimi-cli

# 登录（首次使用必需）
kimi login

# 验证
kimi --version
```

---

**2. OpenCode**

OpenCode 原生支持 ACP 协议。

```bash
# 安装（按 OpenCode 官方文档）
# 通常为：
pip install opencode

# 登录
opencode login

# 验证
opencode --version
```

---

**3. Claude Code**

Claude Code **本身不支持 ACP 协议**，需要额外安装 `claude-code-acp` 转换工具。

```bash
# 步骤 1：安装 Claude Code（按官方文档）
# 通常为 npm 安装或官方安装器

# 步骤 2：安装 ACP 转换工具（必需）
pip install claude-code-acp

# 验证
code --version          # Claude Code 版本
claude-code-acp --version  # ACP 转换工具版本
```

> ⚠️ **注意**：必须同时安装 Claude Code 本体和 `claude-code-acp`，Bot 通过 `claude-code-acp` 调用 Claude Code。

---

**4. OpenClaw**

OpenClaw 的 ACP 协议实现**不标准**，需要额外安装 `openclaw-acp` 转换工具进行协议适配。

```bash
# 步骤 1：安装 OpenClaw（按官方文档）

# 步骤 2：安装 ACP 转换工具（必需）
pip install openclaw-acp

# 验证
openclaw --version
openclaw-acp --version
```

> ⚠️ **注意**：必须同时安装 OpenClaw 本体和 `openclaw-acp`，Bot 通过 `openclaw-acp` 进行协议转换后调用 OpenClaw。

---

**5. Hermes Agent**

Hermes 原生支持 ACP 协议。

```bash
# 安装（按 Hermes 官方文档）

# 登录
hermes login

# 验证
hermes --version
```

---

## 3. 安装 Clawdboz

### 3.1 从 PyPI 安装（推荐）

```bash
pip install clawdboz
```

### 3.2 验证安装

```bash
clawdboz --version
# 应输出: 3.5.0
```

---

## 4. 初始化项目

### 4.1 创建项目目录

```bash
mkdir my-bot && cd my-bot
```

### 4.2 运行初始化命令

```bash
clawdboz init
```

**`clawdboz init` 会自动完成：**

- ✅ 检测已安装的 ACP Agent
- ✅ 创建 `config.json`（含 Python 路径和默认 Agent）
- ✅ 创建 `.agents/mcp.json`（飞书 MCP 工具配置）
- ✅ 复制内置 Skills 到 `.agents/skills/`
- ✅ 创建 `bot_manager.sh`（管理脚本）
- ✅ 创建 `bot0.py`（启动脚本）
- ✅ 创建 `.bots.md`（Agent 指令文件）

### 4.3 生成的目录结构

```
my-bot/
├── .agents/
│   ├── mcp.json              # MCP 配置
│   └── skills/               # Skills 目录
│       ├── feishu-api-sender/
│       ├── find-skills/
│       ├── local-memory/
│       └── scheduler/
├── WORKPLACE/                # 工作目录（临时文件）
├── logs/                     # 日志目录
├── .bots.md                  # Agent 指令
├── bot0.py                   # 启动脚本
├── bot_manager.sh            # 管理脚本
└── config.json               # 配置文件
```

---

## 5. 配置飞书凭证

编辑 `config.json`：

```json
{
  "agent": {
    "executable": "your-agent-path(kimi/opencode/claude-code-acp/openclaw-acp/hermes)"
  },
  "feishu": {
    "app_id": "cli_xxxxxxxxxxxxxxxx",
    "app_secret": "xxxxxxxxxxxxxxxxxxxxxx"
  },
  "python": {
    "bin": ".venv/bin/python"
  },
  "logs": {
    "main_log": "logs/main.log",
    "debug_log": "logs/bot_debug.log",
    "feishu_api_log": "logs/feishu_api.log",
    "ops_log": "logs/ops_check.log"
  },
  "paths": {
    "workplace": "WORKPLACE",
    "user_images": "WORKPLACE/user_images",
    "user_files": "WORKPLACE/user_files",
    "mcp_config": ".agents/mcp.json",
    "skills_dir": ".agents/skills"
  },
  "start_script": "bot0.py"
}
```

**Agent 可执行文件配置：**

| Agent         | `executable` 值      |
| ------------- | -------------------- |
| Kimi Code CLI | `kimi` 或绝对路径    |
| OpenCode      | `opencode` 或绝对路径 |
| Claude Code   | `claude-code-acp` 或绝对路径 |
| OpenClaw      | `openclaw-acp` 或绝对路径 |
| Hermes        | `hermes` 或绝对路径  |

---

## 6. 飞书应用配置

### 6.1 创建应用

1. 前往 [飞书开放平台](https://open.feishu.cn/) 登录开发者账号
2. 点击「开发者后台」→「创建企业自建应用」
3. 填写应用名称和描述，点击「创建」
4. 进入应用详情页，获取 **App ID** 和 **App Secret**

### 6.2 配置权限

在应用详情页：

**权限管理 → 申请以下 API 权限：**

| 权限名称                | 用途           |
| ----------------------- | -------------- |
| `im:message:send`       | 发送消息       |
| `im:message:send_as_bot`| 发送消息卡片   |
| `im:message:update`     | 更新消息卡片   |
| `im:message.resource`   | 获取图片、文件 |
| `im:chat:readonly`      | 获取聊天记录   |
| `im:file:create`        | 上传文件       |
| `im:file:send`          | 发送文件消息   |
| `im:image:create`       | 上传图片       |

**事件与回调 → 选择长连接方式：**

> ⚠️ **重要提醒**：首次配置长连接时，**需要先启动 Bot** 与飞书建立连接，连接成功后才能在飞书后台继续配置长连接权限。如果 Bot 未启动，飞书后台可能无法验证连接或配置失败。
>
> 操作顺序：
> 1. 完成第 5 步（配置 `config.json`）
> 2. 跳到第 7 步，先启动 Bot（`./bot_manager.sh start`）
> 3. 确认 `logs/main.log` 中出现 WebSocket 连接成功的日志
> 4. 再回到飞书后台配置长连接权限

- 勾选 `im.message.receive_v1`（接收消息）

**机器人 → 开启能力：**

- ✅ 接收消息
- ✅ 发送消息

### 6.3 发布应用

1. 「版本管理与发布」→「创建版本」
2. 填写版本号（如 1.0.0）
3. 可用性状态选择「所有员工」
4. 点击「保存」并「申请发布」

### 6.4 添加机器人到聊天

- **单聊**：搜索机器人名称，进入对话
- **群聊**：群设置 →「群机器人」→ 添加机器人 → @机器人

---

## 7. 启动 Bot

### 7.1 使用 bot_manager.sh（推荐）

```bash
# 启动
./bot_manager.sh start

# 查看状态
./bot_manager.sh status

# 查看日志（最后 50 行）
./bot_manager.sh log 50

# 实时跟踪日志
./bot_manager.sh follow

# 停止
./bot_manager.sh stop

# 重启
./bot_manager.sh restart

# 运维检查
./bot_manager.sh check
```

### 7.2 直接运行启动脚本

```bash
python bot0.py
```

### 7.3 三行代码快速启动（Python）

```python
from clawdboz import Bot

bot = Bot(app_id="cli_xxx", app_secret="xxx")
bot.run()
```

---

## 8. 验证部署

### 8.1 检查进程

```bash
./bot_manager.sh status
# 预期输出: Bot 运行中 (PID: xxxxx)
```

### 8.2 检查日志

```bash
# 查看主日志
tail -f logs/main.log

# 查看调试日志
tail -f logs/bot_debug.log
```

### 8.3 发送测试消息

在飞书单聊或群聊中 @机器人，发送：

```
你好
```

预期：机器人回复流式消息卡片。

---

## 9. 定时运维监控（推荐）

配置 crontab 每 30 分钟自动检查 Bot 状态：

```bash
crontab -e
```

添加：

```
*/30 * * * * cd /path/to/my-bot && ./bot_manager.sh check >/dev/null 2>&1
```

`check` 命令会：

- 检查 Bot 进程状态
- 检查 WebSocket 连接
- 检查日志错误
- 检查 MCP 配置
- 发现异常时自动发送飞书通知

---

## 10. 常见问题

### Q1: WebSocket 连接失败 "Missing dependencies for SOCKS support"

**原因：** 缺少 PySocks 库。

**解决：**

```bash
pip install pysocks
# 或
uv pip install pysocks
```

### Q2: Bot 启动后无法收发消息

**排查步骤：**

1. 检查 `config.json` 中 `feishu.app_id` 和 `feishu.app_secret` 是否正确
2. 检查飞书应用是否已发布
3. 检查机器人是否已添加到聊天
4. 检查 `logs/main.log` 是否有 WebSocket 连接错误

### Q3: 消息无回复

**排查步骤：**

1. 检查 ACP Agent 是否已安装并可运行：`kimi --version`
2. 检查 `config.json` 中 `agent.executable` 配置是否正确
3. 检查 `logs/bot_debug.log` 是否有 ACP 调用错误

### Q4: 如何切换 Agent？

修改 `config.json`：

```json
{
  "agent": {
    "executable": "claude-code-acp"
  }
}
```

然后重启 Bot：

```bash
./bot_manager.sh restart
```

### Q5: 如何更新到最新版本？

```bash
pip install --upgrade clawdboz
```

---

## 11. 卸载

```bash
# 停止 Bot
./bot_manager.sh stop

# 卸载包
pip uninstall clawdboz
```
