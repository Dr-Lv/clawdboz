#!/bin/bash
# 会话切换并发测试入口

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=================================="
echo "会话切换并发测试"
echo "=================================="
echo ""

# 检查虚拟环境
if [ ! -f ".venv/bin/python" ]; then
    echo "✗ 虚拟环境不存在"
    exit 1
fi

# 检查依赖
echo "[1] 检查测试依赖..."
.venv/bin/python -c "import websockets" 2>/dev/null || {
    echo "    安装依赖中..."
    uv pip install websockets -q
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
echo "[3] 运行会话切换并发测试..."
echo ""
echo "测试场景:"
echo "  - 创建3个独立会话"
echo "  - 同时发送消息 '数字1', '数字2', '数字3'"
echo "  - 验证消息不串流、无残留加载状态"
echo ""
.venv/bin/python tests/test_session_switch.py
exit_code=$?

echo ""
echo "=================================="
if [ $exit_code -eq 0 ]; then
    echo "✓ 测试通过!"
else
    echo "✗ 测试发现问题"
fi
echo "=================================="

exit $exit_code
