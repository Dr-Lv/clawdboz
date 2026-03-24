#!/bin/bash
# Web Chat E2E 自动化测试 - 使用已有会话
# 使用 Playwright 模拟真实浏览器操作

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=================================="
echo "Web Chat E2E 自动化测试"
echo "使用已有会话测试"
echo "=================================="
echo ""

# 检查虚拟环境
if [ ! -f ".venv/bin/python" ]; then
    echo "✗ 虚拟环境不存在"
    exit 1
fi

# 检查依赖
echo "[1] 检查测试依赖..."
.venv/bin/python -c "import playwright" 2>/dev/null || {
    echo "    安装依赖中..."
    uv pip install playwright -q
    echo "    安装浏览器..."
    .venv/bin/playwright install chromium
}
echo "    ✓ 依赖检查完成"
echo ""

# 检查 Web 服务器是否运行
echo "[2] 检查 Web 服务器状态..."
if curl -s -o /dev/null http://localhost:8080/static/index.html?token=clawdboz-test-2024; then
    echo "    ✓ Web 服务器运行中"
else
    echo "    ✗ Web 服务器未运行"
    echo ""
    echo "请先启动 Web 服务器:"
    echo "  ./start_all.sh"
    exit 1
fi
echo ""

# 运行测试
echo "[3] 运行 E2E 自动化测试..."
echo ""
echo "测试场景:"
echo "  - 利用已有对话（不新建会话）"
echo "  - 在3个会话中依次发送消息"
echo "  - 等待每个回复完成后再截图"
echo "  - 检查是否有残留加载状态和消息串流"
echo ""
.venv/bin/python tests/test_web_e2e_existing.py
exit_code=$?

echo ""
echo "=================================="
if [ $exit_code -eq 0 ]; then
    echo "✓ 测试通过!"
else
    echo "✗ 测试发现问题"
fi
echo ""
echo "截图保存在: /tmp/web_chat_test_*/"
echo "=================================="

exit $exit_code
