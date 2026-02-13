# 更新日志 (Changelog)

所有重要的版本变更都会记录在此文件中。

格式基于 [Keep a Changelog](https://keepachangelog.com/zh-CN/1.0.0/)，
版本号遵循 [Semantic Versioning](https://semver.org/lang/zh-CN/)。

## [未发布]

## [2.0.0] - 2026-02-13

### 🎉 重大重构 - 模块化架构升级

本次版本进行了彻底的架构重构，将单体文件拆分为模块化结构，提升可维护性和可扩展性。

### ✨ 新增功能

- **模块化代码结构**
  - 新增 `src/` 包目录，包含所有核心模块
  - 新增 `feishu_tools/` 工具目录
  - 新增 `docs/` 文档目录

- **配置管理增强**
  - 新增 `config.json` 集中式配置
  - 支持 `LARKBOT_ROOT` 环境变量指定项目根目录
  - 所有路径支持相对于项目根目录的相对路径

- **MCP 集成优化**
  - ACP 工作目录自动设置为 `WORKPLACE`
  - MCP 配置从 `.kimi/` 和 `WORKPLACE/.kimi/` 双重加载
  - Skills 支持用户级覆盖

- **AGENTS.md 合并**
  - 支持合并默认 `AGENTS.md` 和 `WORKPLACE/AGENTS.md`
  - 自定义指令与默认指令自动合并

### 🔧 变更

- **代码结构**
  - `clawdboz.py` (1852行) → 拆分为 `src/` 包
    - `src/config.py` - 配置管理
    - `src/acp_client.py` - ACP 客户端
    - `src/bot.py` - 飞书 Bot 核心
    - `src/handlers.py` - 消息处理器
    - `src/main.py` - 入口点
  - `clawdboz.py` 保留为兼容入口（导入 src 包）

- **文件移动**
  - `mcp_feishu_file_server.py` → `feishu_tools/`
  - `notify_feishu.py` → `feishu_tools/`
  - `PRJ.md`, `ARCHITECTURE.md`, `feishu_permissions.json` → `docs/`

- **启动方式**
  - 旧: `python clawdboz.py`
  - 新: `python -m src.main`（推荐）
  - 兼容: `python clawdboz.py` 仍然有效

- **路径系统**
  - 所有路径改为相对于 `project_root`
  - 支持动态项目根目录配置

### 🐛 修复

- 修复 `src/config.py` 中 config.json 路径查找逻辑
- 自动创建缺失的 `WORKPLACE/user_images` 和 `WORKPLACE/user_files` 目录

### 📝 文档

- 新增 `README.md` - 项目概览和快速开始
- 新增 `docs/PRJ.md` - 项目详细说明
- 新增 `docs/ARCHITECTURE.md` - 架构文档
- 新增 `CHANGELOG.md` - 本更新日志
- 新增 `test-todo.md` - 重构测试清单
- 更新 `AGENTS.md` - 使用说明

### 🔒 测试

- 完成 69 项全面测试
- 核心功能: 13/13 通过 ✅
- 功能模块: 27/27 通过 ✅
- 辅助功能: 22/22 通过 ✅
- 特殊场景: 7/7 通过 ✅

### ⚠️ 升级注意

1. **配置迁移**: 如之前使用环境变量或硬编码配置，请迁移到 `config.json`
2. **路径配置**: 确保 `config.json` 中的 `project_root` 指向正确目录
3. **启动脚本**: 如使用自定义启动脚本，请更新为 `python -m src.main`

---

## [1.x.x] - 2026-02-12 及之前

### 原始版本

- 单体文件架构 (`clawdboz.py`)
- 飞书 Bot 基础功能
- Kimi ACP 集成
- MCP 文件发送
- Bot 管理脚本
