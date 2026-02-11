# Feishu File Sender MCP 使用说明

## 功能
让 Kimi 能够发送文件到飞书消息中

## 安装

1. 确保 MCP Server 文件存在:
```bash
/Users/suntom/work/test/larkbot/mcp_feishu_file_server.py
```

2. 配置 MCP (已创建 `.kimi/mcp_feishu_file.json`)

3. 启动 MCP Server 测试:
```bash
cd /Users/suntom/work/test/larkbot
python3 mcp_feishu_file_server.py
```

## 使用方式

### 方式一：添加到现有 MCP 配置

将以下内容添加到 `.kimi/mcp.json`:

```json
{
  "mcpServers": {
    "RedInk": {
      "url": "http://localhost:3011/sse"
    },
    "FeishuFileSender": {
      "type": "stdio",
      "command": "python3",
      "args": ["/Users/suntom/work/test/larkbot/mcp_feishu_file_server.py"],
      "env": {
        "FEISHU_APP_ID": "cli_a90ded6b63f89cd6",
        "FEISHU_APP_SECRET": "3WDKvIVUHPYVXbEVYjRgRg2wORBDb5z3"
      }
    }
  }
}
```

### 方式二：单独加载

在 Kimi 中使用 `--mcp-config` 参数:
```bash
kimi chat --mcp-config .kimi/mcp_feishu_file.json
```

## 工具说明

### `send_feishu_file`

发送文件到飞书消息

**参数:**
- `chat_id` (string, 必需): 飞书会话 ID
- `file_path` (string, 必需): 本地文件路径

**使用示例:**

当用户在 Kimi 中要求发送文件时，Kimi 会自动调用:

```
用户: 帮我把 /Users/suntom/report.pdf 发送到飞书群 oc_d24a689f16656bb78b5a6b75c5a2b552

Kimi: 调用 send_feishu_file
  - chat_id: oc_d24a689f16656bb78b5a6b75c5a2b552
  - file_path: /Users/suntom/report.pdf

结果: 文件已成功发送到飞书
```

## 测试

测试 MCP Server:
```bash
# 启动测试
echo '{"jsonrpc":"2.0","id":1,"method":"initialize","params":{}}' | python3 mcp_feishu_file_server.py
```

## 注意事项

1. 文件大小限制: 飞书限制 100MB
2. 支持的文件类型: 所有文件类型
3. 需要飞书应用有发送消息权限
