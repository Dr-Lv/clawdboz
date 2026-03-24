# 阿里云 DashScope Claude Code 配置指南

**目标**: 使用阿里云通义千问模型替代 Claude 官方模型  
**适用版本**: Clawdboz 2.8.0+  
**最后更新**: 2025年3月

---

## 🎯 概述

通过配置环境变量，你可以让 Claude Code 使用阿里云 DashScope 提供的通义千问模型，而不是官方的 Claude 模型。

**优势**:
- ✅ 国内访问稳定
- ✅ 中文理解更好
- ✅ 成本更低
- ✅ 支持多种模型（qwen-max, qwen3.5-plus 等）

---

## 🚀 快速开始（推荐）

### 方法一：使用自动设置脚本

```bash
# 1. 进入项目目录
cd /path/to/clawdboz

# 2. 运行设置脚本
python setup_dashscope_claude.py

# 3. 按提示输入 API Key 和选择模型

# 4. 启动 Bot
python -m clawdboz
```

脚本会自动：
- 检测或输入 DashScope API Key
- 选择模型（qwen3.5-plus, qwen-max 等）
- 生成配置文件
- 显示使用说明

---

## 📝 手动配置

### 步骤 1: 获取 DashScope API Key

1. 访问 [阿里云 DashScope 控制台](https://dashscope.console.aliyun.com/apiKey)
2. 创建或复制 API Key
3. 确保已开通通义千问模型服务

### 步骤 2: 配置环境变量

```bash
# 添加到 ~/.bashrc 或 ~/.zshrc
export DASHSCOPE_API_KEY="sk-xxxxxx"

# 立即生效
source ~/.bashrc
```

### 步骤 3: 编辑配置文件

创建或编辑 `config.json`：

```json
{
  "kernels": {
    "default": "kimi",
    "available": {
      "kimi": {
        "name": "Kimi Code",
        "type": "kimi-code",
        "command": "kimi",
        "args": ["--mcp", "stdio"],
        "env": {
          "KIMI_API_KEY": "${KIMI_API_KEY}"
        },
        "description": "Moonshot Kimi Code CLI"
      },
      "qwen35": {
        "name": "Claude Code (通义千问3.5)",
        "type": "claude-code-acp",
        "command": "npx",
        "args": ["@zed-industries/claude-code-acp"],
        "env": {
          "ANTHROPIC_AUTH_TOKEN": "${DASHSCOPE_API_KEY}",
          "ANTHROPIC_BASE_URL": "https://dashscope.aliyuncs.com/apps/anthropic",
          "ANTHROPIC_DEFAULT_HAIKU_MODEL": "qwen3.5-plus",
          "ANTHROPIC_DEFAULT_OPUS_MODEL": "qwen3.5-plus",
          "ANTHROPIC_DEFAULT_SONNET_MODEL": "qwen3.5-plus",
          "ANTHROPIC_MODEL": "qwen3.5-plus",
          "ANTHROPIC_REASONING_MODEL": "qwen3.5-plus"
        },
        "description": "基于阿里云 DashScope 的 Claude Code，使用通义千问3.5模型"
      }
    }
  }
}
```

### 步骤 4: 启动测试

```bash
# 启动 Bot
python -m clawdboz

# 在飞书中测试
/kernel qwen35
```

---

## 🔧 支持的模型

| 模型名称 | 说明 | 适用场景 |
|---------|------|---------|
| `qwen-max` | 通义千问Max | 最强性能，复杂任务 |
| `qwen3.5-plus` | 通义千问3.5 Plus | 平衡性能与成本 |
| `qwen-plus` | 通义千问Plus | 高性价比 |
| `qwen-turbo` | 通义千问Turbo | 最快响应，简单任务 |

---

## 🎨 高级配置

### 配置多个模型

```json
{
  "kernels": {
    "available": {
      "qwen35": {
        "name": "Claude Code (通义千问3.5)",
        "env": {
          "ANTHROPIC_MODEL": "qwen3.5-plus"
        }
      },
      "qwenmax": {
        "name": "Claude Code (通义千问Max)",
        "env": {
          "ANTHROPIC_MODEL": "qwen-max"
        }
      },
      "qwencoder": {
        "name": "Claude Code (通义千问Coder)",
        "env": {
          "ANTHROPIC_MODEL": "qwen-coder-plus"
        }
      }
    }
  }
}
```

### 使用 Python API 配置

```python
from clawdboz import setup_dashscope_claude

# 一键设置
kernel_config = setup_dashscope_claude(
    api_key="sk-xxxxxx",
    model="qwen3.5-plus",
    kernel_name="qwen35"
)

print(kernel_config)
```

### 程序化配置管理

```python
from clawdboz import ClaudeCodeConfigurator

# 创建配置器
configurator = ClaudeCodeConfigurator()

# 创建 DashScope 内核
configurator.create_dashscope_kernel(
    kernel_name="my-qwen",
    api_key="sk-xxxxxx",
    model="qwen3.5-plus"
)

# 生成配置条目
config = configurator.generate_kernel_entry("my-qwen")
print(config)
```

---

## 🔍 故障排除

### 问题 1: 切换内核后报错

**症状**: `/kernel qwen35` 后无响应或报错

**检查**:
```bash
# 1. 检查 API Key
echo $DASHSCOPE_API_KEY

# 2. 测试 API 可用性
curl https://dashscope.aliyuncs.com/api/v1/models \n  -H "Authorization: Bearer $DASHSCOPE_API_KEY"

# 3. 检查 Claude Code ACP 安装
npx @zed-industries/claude-code-acp --help
```

### 问题 2: 模型响应慢

**解决**:
- 尝试 `qwen-turbo` 模型（响应更快）
- 检查网络连接
- 查看阿里云 DashScope 服务状态

### 问题 3: 中文输出乱码

**解决**:
确保环境变量设置正确：
```bash
export LANG=zh_CN.UTF-8
export LC_ALL=zh_CN.UTF-8
```

---

## 📊 与官方 Claude 对比

| 特性 | 官方 Claude | DashScope 通义千问 |
|-----|------------|-------------------|
| 访问稳定性 | 需代理 | 国内直连 |
| 中文能力 | 良好 | 优秀 |
| 代码能力 | 优秀 | 优秀 |
| 上下文长度 | 200K | 128K-200K |
| 成本 | 较高 | 较低 |
| 响应速度 | 快 | 快 |

---

## 🎉 使用示例

### 飞书对话示例

```
用户: /kernel list
Bot: 
**🤖 可用内核列表**

▸ **kimi** - Kimi Code
• **qwen35** - Claude Code (通义千问3.5)
• **qwenmax** - Claude Code (通义千问Max)

用户: /kernel qwen35
Bot: ✅ **已切换到 Claude Code (通义千问3.5)**

用户: 用Python写一个快速排序
Bot: [使用通义千问3.5模型生成代码]

用户: /kernel kimi
Bot: ✅ **已切换到 Kimi Code**

用户: 优化一下刚才的代码
Bot: [使用 Kimi 模型优化代码]
```

---

## 📚 参考链接

- [阿里云 DashScope](https://dashscope.aliyun.com/)
- [通义千问模型列表](https://help.aliy