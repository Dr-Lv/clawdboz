#!/bin/bash
# Web Chat 自动化测试脚本
# 使用方式: ./test_web.sh [选项]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$SCRIPT_DIR"

echo "=================================="
echo "Clawdboz Web Chat 自动化测试"
echo "=================================="
echo ""

# 检查虚拟环境
if [ ! -f ".venv/bin/python" ]; then
    echo "✗ 虚拟环境不存在"
    exit 1
fi

# 检查依赖
echo "[1] 检查测试依赖..."
.venv/bin/python -c "import aiohttp, websockets" 2>/dev/null || {
    echo "    安装依赖中..."
    uv pip install aiohttp websockets -q
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

# 运行基础功能测试
echo "[3] 运行基础功能测试..."
echo ""
.venv/bin/python tests/test_web_auto.py
exit_code=$?

# 如果基础测试通过，运行会话切换测试
if [ $exit_code -eq 0 ]; then
    echo ""
    echo "[4] 运行会话切换并发测试..."
    echo ""
    .venv/bin/python tests/test_session_switch.py
    exit_code=$?
fi

echo ""
echo "=================================="
if [ $exit_code -eq 0 ]; then
    echo "✓ 所有测试通过!"
else
    echo "✗ 部分测试失败"
fi
echo "=================================="

exit $exit_code
