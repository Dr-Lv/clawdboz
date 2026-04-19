---
name: feishu-api-sender
description: 直接调用飞书 API 发送文本消息、图片和文件。绕过有问题的 MCP，使用原生 HTTP API。
triggers:
  - "发送飞书消息"
  - "飞书发送"
  - "发送文本"
  - "发送图片"
  - "发送文件"
  - "feishu send"
---

# Feishu API Sender

直接调用飞书开放平台的 HTTP API 发送消息，不依赖 MCP 工具。

## 功能

- ✅ 发送文本消息
- ✅ 发送图片
- ✅ 发送文件

## 配置

从 bot 项目根目录的 `config.json` 中读取（已内置）：
- `feishu.app_id`: 飞书应用 ID
- `feishu.app_secret`: 飞书应用密钥
- `feishu.chat_id`: 目标聊天 ID

自动搜索路径：向上级目录查找 `config.json`。

## 使用方式

### 1. Python 调用

```python
import sys
sys.path.insert(0, '.agents/skills/feishu-api-sender')

from feishu_sender import send_text, send_image, send_file

# 发送文本
send_text("消息内容")

# 发送图片
send_image("path/to/image.png")

# 发送文件
send_file("path/to/file.md")
```

### 2. 命令行

```bash
python .agents/skills/feishu-api-sender/feishu_sender.py text "消息内容"
python .agents/skills/feishu-api-sender/feishu_sender.py image "path/to/image.png"
python .agents/skills/feishu-api-sender/feishu_sender.py file "path/to/file.md"
```

## 返回格式

```python
{
    "success": True/False,
    "message": "操作结果描述",
    "data": {}  # API 返回的原始数据
}
```
