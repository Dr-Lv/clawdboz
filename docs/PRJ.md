# 嗑唠的宝子 (Clawdboz) - 项目文档

> **版本**: v2.0.0 | **最后更新**: 2026-02-13

## Agent 指令

1. 你的名字叫 **clawdboz**，中文名称叫 **嗑唠的宝子**
2. 调用 skills 或者 MCP 产生的中间临时文件，请放在 **WORKPLACE** 文件夹中
3. 谨慎使用删除命令，如果需要删除，**向用户询问**确认
4. 当新增功能被用户测试完，确认成功后，**git 更新版本**

## 配置文件 (config.json)

所有配置统一放在 `config.json` 文件中：

```json
{
  "project_root": ".",
  "feishu": {
    "app_id": "飞书应用ID",
    "app_secret": "飞书应用密钥"
  },
  "qveris": {
    "api_key": "QVeris API Key"
  },
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

### 项目根目录配置

**`project_root`**: 项目根目录路径
- 默认为 `"."`（即当前文件所在目录）
- 可以是相对路径（相对于脚本所在目录）或绝对路径
- 也可通过环境变量 `LARKBOT_ROOT` 设置（优先级最高）

**示例：**
```bash
# 使用环境变量指定项目根目录
export LARKBOT_ROOT=/opt/larkbot
./bot_manager.sh start
```

### 路径配置说明

所有路径都相对于 `project_root`：
- `workplace`: 工作目录，存放临时文件
- `user_images`: 用户发送的图片保存目录
- `user_files`: 用户发送的文件保存目录
- `mcp_config`: 默认 MCP 配置文件
- `skills_dir`: 默认 Skills 目录
- `workplace_mcp_config`: 用户自定义 MCP 配置（可覆盖默认）
- `workplace_skills_dir`: 用户自定义 Skills 目录
- `agents_md`: 默认 AGENTS.md
- `workplace_agents_md`: 用户自定义 AGENTS.md

### 环境变量覆盖

- `LARKBOT_ROOT`: 项目根目录
- `QVERIS_API_KEY`: QVeris API Key
- `ENABLE_FEISHU_NOTIFY`: 是否启用飞书通知

## 代码结构

Python 源代码位于 `src/` 目录：

| 文件 | 说明 |
|------|------|
| `src/config.py` | 配置管理（PROJECT_ROOT, CONFIG） |
| `src/acp_client.py` | ACP 客户端（与 Kimi 通信） |
| `src/bot.py` | Bot 核心类（LarkBot） |
| `src/handlers.py` | 事件处理器 |
| `src/main.py` | 程序入口 |
| `clawdboz.py` | 兼容入口（导入 src 包） |

**导入示例**:
```python
# 从 src 包导入（推荐）
from src import LarkBot, CONFIG
from src.bot import LarkBot

# 向后兼容
from clawdboz import LarkBot
```

**启动方式**:
```bash
# 推荐
python -m src.main

# 向后兼容
python clawdboz.py

# 管理脚本
./bot_manager.sh start
```

## MCP 配置

### Feishu File Sender MCP

让 Kimi 能够通过 MCP 协议发送文件到飞书消息。

**配置文件**: `.kimi/mcp.json`

```json
{
  "mcpServers": {
    "FeishuFileSender": {
      "type": "stdio",
      "command": "bash",
      "args": ["-c", "python3 /project/larkbot/feishu_tools/mcp_feishu_file_server.py 2>>/project/larkbot/logs/mcp_server.log"],
      "env": []
    }
  }
}
```

**可用工具**:

| 工具名 | 说明 | 参数 |
|--------|------|------|
| `send_feishu_file` | 发送文件到飞书 | `file_path` (string): 本地文件路径 |

**使用示例**:

用户在聊天中发送文件请求时，Kimi 会自动调用：
```
用户: 帮我把 /path/to/report.pdf 发送到飞书
Kimi: 调用 send_feishu_file
  - file_path: /path/to/report.pdf
结果: 文件已成功发送到飞书
```

**注意事项**:
1. 文件大小限制：飞书限制 100MB
2. 支持所有文件类型
3. 需要飞书应用有发送消息权限
4. MCP Server 日志：`logs/mcp_server.log`

### 用户自定义 MCP

用户可以在 `WORKPLACE/.kimi/mcp.json` 中添加自定义 MCP 配置，会覆盖或补充默认配置。

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

### check 命令详解

`check` 命令会自动检查以下项目：

1. **Bot 进程状态** - 检查是否正在运行
2. **资源使用** - CPU 和内存使用率
3. **WebSocket 连接** - 检查是否正常连接
4. **日志错误** - 检查最近日志中的错误
5. **MCP 配置** - 检查配置文件和脚本
6. **Skills** - 检查已安装的 Skills
7. **MCP 上下文** - 检查上下文文件是否过期
8. **虚拟环境** - 检查 Python 环境

**自动修复：**
- 发现异常时自动调用 `kimi --yolo` 进行修复
- Kimi 会分析问题并尝试修复
- 修复完成后自动重新检查状态

**运维日志：**
- 日志文件：`logs/ops_check.log`
- 自动记录每次检查的详细结果
- 包含时间戳、检查项状态、错误详情
- 保留历史记录，方便排查问题

查看运维日志：
```bash
cat logs/ops_check.log               # 查看全部
tail -20 logs/ops_check.log         # 查看最新 20 条
grep "ERROR" logs/ops_check.log     # 查看错误记录
```

**日志文件位置：**
所有日志文件统一放在 `logs/` 目录下：
- `logs/main.log` - Bot 主日志
- `logs/bot_debug.log` - 调试日志
- `logs/feishu_api.log` - 飞书 API 调用日志
- `logs/ops_check.log` - 运维检查日志
- `logs/cron_check.log` - 定时任务日志
- `logs/mcp_server.log` - MCP Server 日志

**飞书通知：**
- 执行 `check` 命令时，**只在发现问题时**发送飞书通知
- 通知类型包括：
  - 🔴 **发现问题** - 检查发现问题，正在修复
  - 🟢 **修复成功** - 问题已修复完成
  - 🔴 **修复失败** - 自动修复失败
- 检查正常时不会发送通知，避免打扰

- 关闭通知：`ENABLE_FEISHU_NOTIFY=false ./bot_manager.sh check`
- 通知依赖于 `WORKPLACE/mcp_context.json` 中的聊天信息

### 定时任务

已配置每半小时自动执行运维检查：

```bash
# 查看定时任务
crontab -l

# 定时任务日志
tail -f cron_check.log
```

**任务详情：**
- **执行频率**：每 30 分钟（每小时的 00 分和 30 分）
- **执行命令**：`./bot_manager.sh check`
- **日志文件**：`cron_check.log`
- **通知策略**：仅发现问题时发送飞书通知

**管理定时任务：**
```bash
# 编辑定时任务
crontab -e

# 停止定时任务（注释掉对应行）
# */30 * * * * cd /project/larkbot && ./bot_manager.sh check >> /project/larkbot/cron_check.log 2>&1

# 查看 cron 服务状态
ps aux | grep cron
```

### 环境变量

| 变量 | 说明 | 默认值 |
|------|------|--------|
| `ENABLE_FEISHU_NOTIFY` | 是否启用飞书通知 | `true` |
| `QVERIS_API_KEY` | QVeris API Key | （已配置） |

示例：
```bash
# 禁用飞书通知执行检查
ENABLE_FEISHU_NOTIFY=false ./bot_manager.sh check

# 使用自定义 API Key
QVERIS_API_KEY="your-key" ./bot_manager.sh start
```

## 更新记录

### 2026-02-13 - 修复群聊记录获取问题

**问题**: 每次重启 Bot 后，在群聊中 @Bot 无法获取群聊历史记录

**根本原因**:
1. `page_size` 参数最大值是 **50**，代码设置为 **100** 导致 `field validation failed` 错误
2. 飞书 API 消息列表是分页的，`has_more: True` 表示有更多页，代码只获取了第一页（最旧的消息）
3. API 返回的消息中混有 `@_user_1`（@Bot 的标记）和空消息（interactive 卡片）
4. "最近1天"的时间范围太短

**修复内容** (`src/bot.py`):
1. 将 `page_size` 从 100 改为 50
2. 添加分页逻辑，获取所有页面（最多5页）来拿到最新消息
3. 添加过滤逻辑，跳过 `@_user_1` 和空消息
4. 扩展时间范围为最近7天

```python
# 修复前 - 只获取第一页
request = ListMessageRequest.builder() \
    .container_id_type("chat") \
    .container_id(chat_id) \
    .page_size(50) \
    .build()

# 修复后 - 分页获取所有消息
all_items = []
page_token = None
for page in range(5):
    builder = ListMessageRequest.builder() \
        .container_id_type("chat") \
        .container_id(chat_id) \
        .page_size(50)
    if page_token:
        builder = builder.page_token(page_token)
    request = builder.build()
    # ... 处理分页
```
