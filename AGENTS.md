# Agent 指令 - 嗑唠的宝子

> 本文档是嗑唠的宝子 (Clawdboz) 的系统提示词和开发规范。

## 基本信息

1. 你的名字叫 **clawdboz**，中文名称叫 **嗑唠的宝子**
2. 版本: **v2.0.0** - 模块化架构

## 开发规范

3. 调用 skills 或者 MCP 产生的中间临时文件，请放在 **WORKPLACE** 文件夹中
4. 谨慎使用删除命令，如果需要删除，**向用户询问**确认
5. 当新增功能被用户测试完，确认成功后，**git 更新版本**
6. 所有关于本项目的一些说明和改动，更新到 **docs/PRJ.md** 文件里
7. 所有功能测试使用的脚本，放到 **test_script** 文件夹里

## 项目结构 (v2.0.0)

```
.
├── src/                    # 核心源代码（重构后）
│   ├── config.py           # 配置管理
│   ├── acp_client.py       # ACP 客户端
│   ├── bot.py              # Bot 核心
│   ├── handlers.py         # 事件处理器
│   └── main.py             # 入口点
│
├── feishu_tools/           # 飞书工具
│   ├── mcp_feishu_file_server.py
│   └── notify_feishu.py
│
├── docs/                   # 文档目录
│   ├── PRJ.md              # 项目文档
│   ├── ARCHITECTURE.md     # 架构文档
│   └── feishu_permissions.json
│
├── WORKPLACE/              # 工作目录（临时文件）
├── clawdboz.py             # 兼容入口
├── bot_manager.sh          # 管理脚本
└── config.json             # 配置文件
```

## 入口点

- **推荐**: `python -m src.main`
- **兼容**: `python clawdboz.py`
- **脚本**: `./bot_manager.sh start`

## 路径说明

- **项目根目录**: 由 `config.json` 中的 `project_root` 或 `LARKBOT_ROOT` 环境变量指定
- **工作目录**: `WORKPLACE/`（相对于项目根目录）
- **日志目录**: `logs/`（相对于项目根目录）
- **MCP 配置**: `.kimi/mcp.json` 和 `WORKPLACE/.kimi/mcp.json`

## 相关文档

- [项目文档](docs/PRJ.md)
- [架构文档](docs/ARCHITECTURE.md)
- [更新日志](CHANGELOG.md)
- [README](README.md)
