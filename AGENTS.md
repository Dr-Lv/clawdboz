# AGENTS.md — Clawdboz (嗑唠的宝子)

> 本文档面向 AI 编码助手。如果你正在阅读此文件，说明你是来接管或协助开发 Clawdboz 的。

---

## 项目概览

**Clawdboz**（中文：嗑唠的宝子）是一个基于 Kimi Code CLI 的智能多 Bot 协作平台。

- **版本**: 2.7.5
- **语言**: Python 3.9+（后端）+ 纯 HTML/JS 单页应用（前端）
- **许可证**: MIT
- **核心能力**: 本地 Bot 管理、远程 Bot 发现/调用、群聊协作、飞书集成、Docker 沙箱隔离

### 三个核心概念

1. **Bot**: 最小智能单元，通过 ACP 协议（Kimi CLI）执行用户请求。每个 Bot 有独立的工作目录 `WORKPLACE/workplace_{bot_id}/`。
2. **实例 (Instance)**: 运行 Bots 的服务器进程，由 `hostname-port` 唯一标识（如 `iZbp14orv6wgpv91l9xtw0Z-7011`）。
3. **注册中心 (Registry)**: 独立进程，维护实例目录、Bot 发现、好友关系、消息转发。每个实例通过 WebSocket 长连接到 Registry。

### 运行模式

| 模式 | 入口文件 | 说明 |
|------|---------|------|
| Web Chat | `web_server.py` | FastAPI + WebSocket，浏览器访问 `static/index.html` |
| 飞书 Bot | `bot0.py` / `clawdboz.cli` | 接收飞书消息，通过 OpenAPI 回复 |
| 注册中心 | `registry_server.py` | 独立 FastAPI 服务，可选部署 |

---

## 目录结构

```
clawdboz/                       # Python 包
├── __init__.py
├── cli.py                      # 命令行入口 `clawdboz`
├── core/                       # Bot 核心
│   ├── bot.py                  # Bot 基类
│   ├── bot_manager.py          # BotManager（注册、管理）
│   └── simple_bot.py           # 简化版 Bot API
├── web/                        # Web 服务
│   ├── server.py               # WebChatServer (FastAPI)
│   ├── chat/                   # 聊天核心
│   │   ├── core.py             # ChatCore（消息处理、远程调用）
│   │   ├── history.py          # 聊天记录管理
│   │   ├── mentions.py         # @提及解析
│   │   ├── group.py            # 群聊逻辑
│   │   └── acp.py              # ACP 客户端管理
│   ├── routes/                 # API 路由
│   │   ├── bots.py             # /api/bots
│   │   ├── websocket.py        # WebSocket 连接管理
│   │   ├── remote.py           # /api/remote/*
│   │   ├── sessions/           # 会话相关路由
│   │   └── ...
│   ├── static/                 # 前端资源
│   │   ├── index.html          # 主界面（单文件 ~10K 行 JS）
│   │   └── ...
│   └── workspace.py            # 工作区管理
├── remote/                     # 远程功能
│   ├── manager.py              # RemoteBotManager（核心）
│   ├── registry_client.py      # Registry HTTP API 客户端
│   ├── registry_ws_client.py   # Registry WebSocket 客户端
│   ├── bot_publisher.py        # Bot 发布到 Registry
│   ├── remote_client.py        # 远程 Bot 调用客户端
│   ├── docker_sandbox.py       # Docker 沙箱管理
│   ├── friend_manager.py       # 好友关系管理
│   └── ...
├── communication/              # ACP 通信层
│   ├── acp_client.py
│   ├── websocket_acp_client.py
│   └── session_manager.py
└── utils/                      # 工具
    └── logger.py

registry_server.py              # 注册中心（独立部署）
web_server.py                   # Web Chat 入口（加载本地 bots）
bot0.py                         # 飞书 Bot 入口
tests/                          # 测试
WORKPLACE/                      # 运行时数据（gitignored）
    ├── workplace_{bot_id}/     # 各 Bot 工作目录
    │   └── .bot.md             # Bot 元数据（Name, Bio, Avatar, 指令）
    ├── .remote/                # 远程功能数据
    │   ├── added_bots.json     # 已添加的远程 bots
    │   └── published_bots.json # 已发布的本地 bots
    └── user_images/ / user_files/
```

---

## 编码风格与约定

### Python

- **注释**: 使用中文注释。docstring 用中文描述。
- **类型注解**: 鼓励使用，但项目历史遗留代码中并不完整。新代码应加上。
- **行长度**: `black` 配置为 100 字符（`pyproject.toml`）。
- **字符串**: 内部使用双引号 `"` 为主，JSON 处理时混用单引号无所谓。
- **异常**: 不要裸 `except:`，至少 `except Exception as e:`。WebSocket 发送失败通常静默捕获。
- **打印**: 开发调试用 `print()`，日志用 `clawdboz.utils.logger`。生产环境日志输出到 `logs/`。

### 前端 (`index.html`)

- **单文件架构**: 所有 HTML/CSS/JS 都在 `clawdboz/web/static/index.html` 中，没有构建步骤，没有 npm。
- **样式**: Tailwind CSS 类名 + 内联 `<style>`。
- **图标**: Font Awesome (`fas fa-*`)。
- **数据存储**: IndexedDB（前端本地缓存）+ 服务端 REST API。
- **修改原则**: 保持向后兼容，避免破坏现有 DOM 结构 id/class。

### 配置与元数据

- **Bot 元数据**: 每个 bot 工作目录下的 `.bot.md` 文件定义：
  ```markdown
  Name: 显示名称
  Bio: 简介
  Avatar Color: from-blue-500 to-blue-600
  Avatar Icon: fa-robot
  Avatar Image: data:image/...
  ```
- **项目配置**: `config.json`（运行时）或 `config.json.example`（模板）。
- **远程配置**: `config.json` 中 `remote` 字段，映射到 `clawdboz.remote.config.RemoteConfig`。

---

## 构建与测试

### 安装依赖

```bash
pip install -e .          # 开发安装
# 或
pip install -r requirements.txt
```

### 运行测试

```bash
pytest tests/             # 单元测试
python tests/test_web_server.py    # Web 服务测试
```

### 打包发布

```bash
rm -rf build/ dist/ *.egg-info
python3 -m build
# 产出: dist/clawdboz-2.7.5-py3-none-any.whl
```

### 部署

- **Registry**: `./deploy_registry.sh` → 部署到 `/opt/clawdboz-registry/`
- **Instance**: `./deploy_remote_instance.sh` → 部署到 `/opt/clawdboz-instance/`
- **本地开发**: `python3 web_server.py --port 7011 --host 0.0.0.0`

⚠️ **systemd 风险**: 本地机器上 `clawdboz-instance.service` 可能与手动进程竞争端口。修改前务必 `systemctl stop clawdboz-instance.service`。

---

## 关键架构决策

### 1. 远程 Bot 调用流（中心模式）

```
用户 → 本地 ChatCore._call_remote_bot()
  → RemoteBotManager.call_remote_bot()
  → RemoteBotClient._call_via_center()
  → RegistryWebSocketClient.send_to_instance()
  → Registry 转发 → Host1 _handle_forwarded_message()
  → Host1 _handle_center_bot_call()
  → Docker 沙箱 HTTP /execute
  → 响应原路返回（Registry WS `bot_response`）
  → 本地 future.set_result()
```

- Registry 只允许每个 `instance_id` 一个 WebSocket 连接。
- 心跳间隔 30 秒，404 时自动重新注册。
- 超时 120 秒。

### 2. 头像同步机制

```
Host1 .bot.md → _read_bot_avatar() → heartbeat → Registry (avatar_url)
  → 本地 discovery → remote_bot_cache → get_added_remote_bots() → /api/bots
  → 前端 bots 数组
```

- Registry 存储字段名为 `avatar_url`，本地代码统一转换为 `avatar_image`。
- 无自定义头像的 Bot 默认清空 color/icon，前端走哈希预设生成不同颜色。

### 3. 两个 API 的区别

| API | 数据来源 | 包含内容 |
|-----|---------|---------|
| `/api/bots` | `added_bots.json` + 本地 bots | **已添加**的远程 bots |
| `/api/remote/bots` | Registry 实时查询 | **所有发现**的远程 bots |

### 4. WebSocket 消息格式

```json
{"type": "start",  "msg_id": "...", "seq": 0, "bot_id": "...", "bot_name": "...", "avatar_color": "...", "avatar_icon": "...", "avatar_image": "...", "chat_id": "..."}
{"type": "chunk", "msg_id": "...", "seq": 1, "bot_id": "...", "content": "...", "is_thinking": false, "chat_id": "..."}
{"type": "done",  "msg_id": "...", "seq": N, "bot_id": "...", "chat_id": "..."}
```

---

## 常见陷阱

1. **三份代码库风险**: git repo (`/root/code/clawdboz/`) ≠ 运行时 (`/opt/clawdboz-instance/`) ≠ pip 安装路径 (`/usr/lib/python3.11/site-packages/clawdboz/`)。修改后务必确认运行时加载的是正确路径的代码。重启是最安全的验证方式。

2. **Python 模块缓存**: 修改 `.py` 文件后，已运行的进程不会自动加载新代码。必须重启 `web_server.py`。

3. **`added_bots.json` 过期**: 远程实例下架 bot 后，本地 `added_bots.json` 不会自动清理，导致 `/api/bots` 返回幽灵记录。

4. **前端缓存**: `index.html` 可能被浏览器缓存。强制刷新（Ctrl+Shift+R）或检查文件修改时间。

5. **Docker 沙箱端口**: 沙箱容器映射 `18443:18443`。如果容器启动慢，健康检查会失败重试（最多 3 次创建容器）。

6. **Registry WS 单连接**: 同一 `instance_id` 重复连接会导致旧连接被踢（close code 4009）。不要同时运行 systemd 服务和手动进程。

---

## 开发规范（来自 `.bots.md`）

1. 调用 skills 或 MCP 产生的中间临时文件，放在 **WORKPLACE** 文件夹中。
2. 谨慎使用删除命令，如果需要删除，**向用户询问**确认。
3. 当新增功能被用户测试完、确认成功后，**git 更新版本**。
4. 同时支持 **飞书** 和 **Web Chat** 两种平台，通过 `session_config.json` 中的 `platform` 字段区分。

---

## 必读外部文档

以下文件**不在**本 AGENTS.md 的覆盖范围内，但在特定场景下**必须优先读取**：

### `MEMORY.md` — 部署记忆与运维备忘

**何时读取**：
- 任何涉及**服务器连接、部署路径、SSH 登录、systemd 服务、重启命令**的任务
- 需要知道 Registry / Host1 / 本地实例的 IP、端口、密钥路径、安装路径时
- 执行部署、运维、日志查看、服务重启前

**关键内容**：
- Registry 服务器 (`8.136.150.62`) 和 Host1 (`47.110.136.0`) 的 SSH 密钥路径
- 各实例的安装路径（如 `/opt/clawdboz-registry`、`/tmp/clawdboz`）
- systemd 服务名和常用运维命令

### `Bugs_and_Feartures.md`（注意拼写：Feartures）— 待修复 Bug 与待开发 Feature

**何时读取**：
- 用户要求**修复 bug** 或**开发新功能**时，首先读取此文件确认需求是否已记录
- 每次任务完成后，运行 `scripts/check_bugs_and_features.py` 验证修复状态
- 在**开始任何功能开发前**，检查此文件避免重复劳动或遗漏关联需求

**关键内容**：
- 6 个已知 bugs（消息计数、loading 超时、会话切换重复、头像显示、远程通信等）
- 2 个待开发 features（发布 bot 卡片显示好友列表、解除好友关系）
- 4 条开发规范要求（CLI 测试、web 端一致性、浏览器截图验证、减少人工测试）

---

## 相关文档索引

| 文档 | 内容 | 何时读取 |
|------|------|---------|
| `README.md` | 用户-facing 快速开始、功能说明 | 初次了解项目 |
| `ARCHITECTURE.md` | 架构优化建议（偏未来规划） | 做架构级重构时 |
| `ARCHITECTURE_CURRENT.md` | 当前架构详细说明 | 深入理解现有架构 |
| `REGISTRY_ARCHITECTURE.md` | 注册中心架构 | 修改远程/Registry 功能 |
| `FEATURE.md` | 完整功能清单 | 确认功能范围 |
| `TESTING.md` | 测试指南 | 编写或运行测试 |
| `DEPLOYMENT_SUMMARY.md` | 部署总结 | 部署相关任务 |
| `CONNECT_TO_REGISTRY.md` | 连接注册中心配置 | 配置远程连接 |
| `PRD.md` | 产品需求文档 | 理解产品方向 |
| `MEMORY.md` | **部署记忆与运维备忘** | **任何服务器/运维操作前必读** |
| `Bugs_and_Feartures.md` | **待修复 Bug 与待开发 Feature** | **修复bug/开发功能前必读** |
