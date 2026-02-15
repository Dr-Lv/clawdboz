# 嗑唠的宝子 (Clawdboz) - 项目文档

> **版本**: v2.1.0 | **最后更新**: 2026-02-15

## Agent 指令

1. 你的名字叫 **clawdboz**，中文名称叫 **嗑唠的宝子**
2. 调用 skills 或者 MCP 产生的中间临时文件，请放在 **WORKPLACE** 文件夹中
3. 谨慎使用删除命令，如果需要删除，**向用户询问**确认
4. 当新增功能被用户测试完，确认成功后，**git 更新版本**

## 配置文件

### 敏感信息配置 (.env)

**重要**: 敏感信息（如 API Key、应用密钥）存放在项目根目录的 `.env` 文件中，**不要提交到 Git**。

创建 `.env` 文件：

```bash
# 飞书应用配置（必填）
FEISHU_APP_ID=cli_xxxxx
FEISHU_APP_SECRET=xxxxx

# QVeris API Key（可选）
QVERIS_API_KEY=sk-xxxxx

# 通知配置（可选）
ENABLE_FEISHU_NOTIFY=true
```

### 一般配置 (config.json)

```json
{
  "project_root": "/project/larkbot",
  "logs": {
    "main_log": "logs/main.log",
    "debug_log": "logs/bot_debug.log",
    "feishu_api_log": "logs/feishu_api.log",
    "ops_log": "logs/ops_check.log",
    "cron_log": "logs/cron_check.log"
  },
  "notification": {
    "enabled": true,
    "script": "feishu_tools/notify_feishu.py"
  },
  "paths": {
    "workplace": "WORKPLACE",
    "context_file": "WORKPLACE/mcp_context.json",
    "user_images": "WORKPLACE/user_images",
    "user_files": "WORKPLACE/user_files",
    "mcp_config": ".kimi/mcp.json",
    "skills_dir": ".kimi/skills",
    "workplace_mcp_config": "WORKPLACE/.kimi/mcp.json",
    "workplace_skills_dir": "WORKPLACE/.kimi/skills",
    "agents_md": "AGENTS.md",
    "workplace_agents_md": "WORKPLACE/AGENTS.md"
  }
}
```

### 配置优先级

配置加载优先级（高到低）：

1. **环境变量** - `export FEISHU_APP_ID=xxx`
2. **.env 文件** - 项目根目录下的 `.env`
3. **config.json** - 一般配置文件

### 项目根目录配置

**`project_root`**: 项目根目录路径
- 默认为 `"."`（即当前文件所在目录）
- 可以是相对路径（相对于脚本所在目录）或绝对路径
- 也可通过环境变量 `LARKBOT_ROOT` 设置（优先级最高）

**示例**：
```bash
# 使用环境变量指定项目根目录
export LARKBOT_ROOT=/opt/larkbot
./bot_manager.sh start
```

## 代码结构

Python 源代码位于 `src/` 目录：

| 文件 | 说明 |
|------|------|
| `src/config.py` | 配置管理（支持 .env、环境变量、config.json） |
| `src/acp_client.py` | ACP 客户端（与 Kimi 通信） |
| `src/bot.py` | Bot 核心类（LarkBot） |
| `src/handlers.py` | 事件处理器 |
| `src/main.py` | 程序入口（带 WebSocket 监控） |
| `clawdboz.py` | 兼容入口（导入 src 包） |

**启动方式**:
```bash
# 推荐
python -m src.main

# 向后兼容
python clawdboz.py

# 管理脚本
./bot_manager.sh start
```

## 核心功能

### 1. 群聊记录获取（支持图片/文件）

Bot 会自动获取群聊历史记录，并下载用户发送的图片和文件：

**功能特性**:
- 获取最近 7 天内的聊天记录
- 自动下载用户发送的图片到 `WORKPLACE/user_images/`
- 自动下载用户发送的文件到 `WORKPLACE/user_files/`
- 将图片/文件路径包含在发送给 ACP 的 prompt 中

**消息类型处理**:

| 消息类型 | 处理方式 | Prompt 中的显示 |
|---------|---------|----------------|
| 文本 | 直接提取内容 | `user: 消息内容` |
| 图片 | 下载到本地 | `user: [图片] /path/to/image.png` |
| 文件 | 下载到本地 | `user: [文件: xxx.pdf] /path/to/file` |
| Bot 卡片 | 跳过下载 | `bot: [图片/卡片回复] (Bot 发送的卡片)` |

**限制说明**:
- Bot 发送的卡片消息会被飞书渲染成预览图，无法下载（权限限制）
- 图片大小限制：5MB
- 文件大小限制：20MB

### 2. WebSocket 连接监控

`src/main.py` 实现了 WebSocket 连接状态监控：

**监控功能**:
- 记录连接/断开/重连事件
- 心跳保活检测（每 120 秒）
- 连续 10 次心跳失败触发 ERROR 告警
- 连接统计信息

**日志输出** (`logs/main.log`):
```
[INFO] [CONNECT] WebSocket 连接成功 - conn_id: xxx
[WARN] [RECONNECT] 开始第 1 次重连...
[WARN] [PING] 心跳失败 #1: xxx
[ERROR] [ALERT] 连续 10 次心跳失败！连接可能已断开
```

### 3. MCP 文件发送

让 Kimi 能够通过 MCP 协议发送文件到飞书消息。

**配置文件**: `.kimi/mcp.json`

```json
{
  "mcpServers": {
    "FeishuFileSender": {
      "type": "stdio",
      "command": "/project/larkbot/.venv/bin/python3",
      "args": ["/project/larkbot/feishu_tools/mcp_feishu_file_server.py"],
      "env": {
        "PYTHONPATH": "/project/larkbot"
      }
    }
  }
}
```

**可用工具**:

| 工具名 | 说明 | 参数 |
|--------|------|------|
| `send_feishu_file` | 发送文件到飞书 | `file_path` (string): 本地文件路径 |

## Bot 管理脚本 (bot_manager.sh)

```bash
./bot_manager.sh {command} [options]
```

### 命令列表

| 命令 | 说明 | 示例 |
|------|------|------|
| `start` | 启动 Bot | `./bot_manager.sh start` |
| `stop` | 停止 Bot | `./bot_manager.sh stop` |
| `restart` | 重启 Bot | `./bot_manager.sh restart` |
| `status` | 查看 Bot 状态 | `./bot_manager.sh status` |
| `check` | **检查并自动修复异常** | `./bot_manager.sh check` |
| `log [n]` | 查看最近 n 条日志 | `./bot_manager.sh log 50` |
| `follow` | 实时跟踪日志 | `./bot_manager.sh follow` |
| `test` | 测试 Bot 功能 | `./bot_manager.sh test` |
| `send [chat_id] [msg]` | 发送测试消息 | `./bot_manager.sh send` |
| `clean` | 清理日志文件 | `./bot_manager.sh clean` |
| `help` | 显示帮助 | `./bot_manager.sh help` |

### 日志文件位置

所有日志文件统一放在 `logs/` 目录下：
- `logs/main.log` - WebSocket 连接状态日志
- `logs/bot_debug.log` - Bot 调试日志
- `logs/bot_output.log` - Bot 标准输出
- `logs/feishu_api.log` - 飞书 API 调用日志
- `logs/ops_check.log` - 运维检查日志
- `logs/cron_check.log` - 定时任务日志
- `logs/mcp_server.log` - MCP Server 日志

## 更新记录

### 2026-02-15 - 配置系统重构 & 群聊记录增强

#### 1. 敏感配置迁移到环境变量

**变更**:
- 敏感信息（`FEISHU_APP_ID`, `FEISHU_APP_SECRET`, `QVERIS_API_KEY`）迁移到 `.env` 文件
- 更新 `src/config.py` 支持从 `.env` 和环境变量读取配置
- 更新 `.gitignore` 确保 `.env` 不被提交

**优先级**: 环境变量 > .env 文件 > config.json

#### 2. 群聊记录支持图片/文件下载

**新增功能**:
- `_download_chat_image()` - 下载群聊图片
- `_download_chat_file()` - 下载群聊文件
- `_find_local_image_by_key()` - 根据 image_key 查找本地图片

**改进**:
- `_get_chat_history()` 返回字典格式，包含消息类型和本地路径
- Prompt 中图片/文件显示本地路径，Kimi 可直接读取
- Bot 发送的卡片自动跳过下载（权限受限）

#### 3. WebSocket 连接监控

**新增** (`src/main.py`):
- `MonitoredWSClient` 类，继承自飞书 SDK Client
- 心跳失败计数，连续 10 次失败触发 ERROR 告警
- 记录连接/断开/重连事件

### 2026-02-13 - 修复群聊记录获取问题

**问题**: 每次重启 Bot 后，在群聊中 @Bot 无法获取群聊历史记录

**根本原因**:
1. `page_size` 参数最大值是 **50**，代码设置为 **100** 导致 `field validation failed` 错误
2. 飞书 API 消息列表是分页的，`has_more: True` 表示有更多页，代码只获取了第一页（最旧的消息）
3. API 返回的消息中混有 `@_user_1`（@Bot 的标记）和空消息（interactive 卡片）
4. "最近1天"的时间范围太短

**修复内容** (`src/bot.py`):
1. 将 `page_size` 从 100 改为 50
2. 添加分页逻辑，获取所有页面（最多10页）来拿到最新消息
3. 添加过滤逻辑，跳过 `@_user_1` 和空消息
4. 扩展时间范围为最近7天

---

**维护者**: clawdboz (嗑唠的宝子)  
**项目地址**: /project/larkbot
