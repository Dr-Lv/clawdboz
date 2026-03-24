# Clawdboz 多内核集成指南

**版本**: 2.8.0  
**更新日期**: 2025年3月  
**功能**: 支持 Kimi Code 和 Claude Code 双内核切换

---

## 🎯 新功能概览

### 核心特性
- ✅ **多内核支持**: Kimi Code + Claude Code
- ✅ **运行时切换**: 对话中随时切换内核
- ✅ **优雅兼容**: 完全向后兼容现有代码
- ✅ **统一接口**: 相同 API，不同内核

### 使用场景
- 代码任务用 **Kimi**（中文优化）
- 复杂推理用 **Claude**（200K 上下文）
- 对比测试两种内核效果

---

## 🚀 快速开始

### 1. 安装依赖

```bash
# 安装 Claude Code ACP 适配器
npm install -g @zed-industries/claude-code-acp

# 验证安装
npx @zed-industries/claude-code-acp --version
```

### 2. 配置 API 密钥

```bash
# 添加到 ~/.bashrc 或 ~/.zshrc
export ANTHROPIC_API_KEY="your-anthropic-api-key"
export KIMI_API_KEY="your-kimi-api-key"

# 立即生效
source ~/.bashrc
```

### 3. 更新配置文件

复制示例配置：
```bash
cp config.json.example config.json
```

编辑 `config.json`，确保包含：
```json
{
  "kernels": {
    "default": "kimi",
    "available": {
      "kimi": {
        "name": "Kimi Code",
        "type": "kimi-code",
        "command": "kimi",
        "args": ["--mcp", "stdio"]
      },
      "claude": {
        "name": "Claude Code",
        "type": "claude-code-acp",
        "command": "npx",
        "args": ["@zed-industries/claude-code-acp"]
      }
    }
  }
}
```

### 4. 启动 Bot

```bash
python -m clawdboz
```

---

## 💬 使用命令

### 飞书中的命令

| 命令 | 说明 | 示例 |
|-----|------|------|
| `/kernel` | 查看当前状态 | `/kernel` |
| `/kernel list` | 列出可用内核 | `/kernel list` |
| `/kernel <名称>` | 切换内核 | `/kernel claude` |
| `/k <名称>` | 快捷切换 | `/k kimi` |
| `/switch <名称>` | 切换内核 | `/switch claude` |

### 使用示例

```
用户: /kernel list
Bot: 
**🤖 可用内核列表**

▸ **kimi** - Kimi Code
  Moonshot Kimi Code CLI - 优秀的代码助手

• **claude** - Claude Code
  Anthropic Claude Code - 强大的 AI 编程助手

**使用方法**: `/kernel <内核名称>` 或 `/k <内核名称>`

---

用户: /kernel claude
Bot: ✅ **已切换到 Claude Code**

类型: `claude-code-acp`
命令: `npx @zed-industries/claude-code-acp`

---

用户: 帮我写一个快速排序
Bot: [使用 Claude Code 回复]

---

用户: /k kimi
Bot: ✅ **已切换到 Kimi Code**

用户: 用中文解释一下快速排序
Bot: [使用 Kimi Code 回复]
```

---

## 🔧 高级配置

### 自定义内核

在 `config.json` 中添加自定义内核：

```json
{
  "kernels": {
    "available": {
      "my-claude": {
        "name": "My Claude",
        "type": "claude-code-acp",
        "command": "npx",
        "args": [
          "@zed-industries/claude-code-acp",
          "--timeout", "120"
        ],
        "env": {
          "ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}",
          "ACP_PERMISSION_MODE": "acceptEdits"
        },
        "description": "自定义 Claude 配置"
      }
    }
  }
}
```

### 环境变量占位符

配置支持环境变量占位符 `${VAR_NAME}`：

```json
{
  "env": {
    "ANTHROPIC_API_KEY": "${ANTHROPIC_API_KEY}",
    "CUSTOM_VAR": "${MY_CUSTOM_VAR}"
  }
}
```

---

## 🏗️ 架构说明

### 核心组件

```
clawdboz/
├── kernel_manager.py      # 内核管理器（新）
├── kernel_commands.py     # 命令处理器（新）
├── acp_client.py          # ACP 客户端（兼容层）
├── bot.py                 # Bot 主类（扩展）
└── config.py              # 配置模块
```

### 类关系图

```
KernelManager
    ├── KernelRegistry (管理内核定义)
    └── Kernel (内核实例)
        ├── Kimi Code
        └── Claude Code

KernelCommandHandler
    └── 处理 /kernel 命令

ACPClient (兼容层)
    └── 包装 KernelManager
```

---

## 📝 代码示例

### 直接使用 KernelManager

```python
from clawdboz import KernelManager

# 创建管理器
manager = KernelManager()

# 列出内核
print(manager.list_available())

# 切换内核
manager.switch_kernel('claude')

# 获取当前内核
kernel = manager.current_kernel

# 调用方法
result, error = kernel.call_method('tools/list', {})
```

### 在 Bot 中集成

```python
from clawdboz import LarkBot, KernelManager

class MyBot(LarkBot):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        
        # 初始化内核管理器
        self.kernel_manager = KernelManager(bot_ref=self)
        
        # 注册命令
        from clawdboz.kernel_commands import create_kernel_commands
        commands = create_kernel_commands(self.kernel_manager)
        self.command_handlers.update(commands)
```

---

## 🔍 故障排除

### Claude Code 启动失败

**症状**: 切换内核后无响应

**检查**:
```bash
# 1. 检查 npx 是否可用
npx --version

# 2. 检查 Claude Code ACP 适配器
npx @zed-industries/claude-code-acp --help

# 3. 检查 API 密钥
echo $ANTHROPIC_API_KEY
```

**解决**:
```bash
# 重新安装适配器
npm install -g @zed-industries/claude-code-acp

# 或使用本地安装
cd /path/to/clawdboz
npm install @zed-industries/claude-code-acp
```

### 内核切换后上下文丢失

**说明**: 这是预期行为，每个内核有独立的会话状态。

**解决**: 如需保持上下文，考虑实现会话持久化（未来版本）。

### 日志查看

```bash
# 查看内核日志
tail -f logs/kernels/claude-code-acp_*.log
tail -f logs/kernels/kimi-code_*.log
```

---

## 📊 性能对比

| 指标 | Kimi Code | Claude Code |
|-----|-----------|-------------|
| 启动时间 | ~2s | ~3s |
| 响应速度 | 快 | 快 |
| 上下文长度 | 128K | 200K |
| 中文能力 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐ |
| 代码能力 | ⭐⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |
| 推理能力 | ⭐⭐⭐⭐ | ⭐⭐⭐⭐⭐ |

---

## 🎉 总结

现在你可以在 Clawdboz 中：

1. **随时切换内核**: `/kernel claude` 或 `/kernel kimi`
2. **对比不同效果**: 同一问题用不同内核回答
3. **选择最佳工具**: 根据任务类型选择合适内核

**下一步**:
- 尝试 `/kernel claude` 体验 Claude Code
- 对比 Kimi 和 Claude 的代码风格差异
- 根据任务类型选择最佳内核

---

## 📚 参考链接

- [Claude Code 官方文档](https://docs.anthropic.com/en/docs/claude-code/overview)
- [Zed ACP 协议](https://zed.dev/blog/acp)
- [Kimi Code CLI](https://www.moonshot.cn/docs/kimi-code)

---

**Happy Coding with Multiple Kernels! 🚀**