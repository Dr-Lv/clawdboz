#!/bin/bash
# 启动飞书 Bot 和 Web 界面

echo "=================================="
echo "Clawdboz Bot + Web 启动脚本"
echo "=================================="

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

# 启动飞书 Bot
echo ""
echo "[1] 启动飞书 Bot..."
./bot_manager.sh start

# 等待 Bot 启动
sleep 2

# 检查 Bot 状态
if ! ./bot_manager.sh status > /dev/null 2>&1; then
    echo "Bot 启动失败，请检查日志"
    exit 1
fi

# 启动 Web 服务器
echo ""
echo "[2] 启动 Web 服务器..."
nohup .venv/bin/python web_server.py > logs/web_server.log 2>&1 &
echo $! > web_server.pid
sleep 3

# 检查 Web 服务器
if curl -s -o /dev/null http://localhost:8080/static/index.html?token=clawdboz-test-2024; then
    echo "    ✓ Web 服务器已启动"
else
    echo "    ✗ Web 服务器启动失败"
fi

echo ""
echo "=================================="
echo "所有服务已启动!"
echo "=================================="
echo ""
echo "已注册的 Bots:"
echo "  1. feishu-bot    - 嗑唠的宝子（通用助手）"
echo "  2. code-assistant - 代码助手"
echo "  3. doc-writer    - 文档助手"
echo ""
echo "飞书 Bot:"
echo "  ./bot_manager.sh status  # 查看状态"
echo "  ./bot_manager.sh stop    # 停止"
echo ""
echo "Web 界面:"
echo "  URL: http://localhost:8080/static/index.html?token=clawdboz-test-2024"
echo "  Token: clawdboz-test-2024"
echo "  PID: $(cat web_server.pid)"
echo ""
echo "停止所有服务:"
echo "  ./bot_manager.sh stop && kill $(cat web_server.pid)"
echo "=================================="
