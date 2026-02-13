#!/bin/bash
# 测试退出码捕获

echo "=== 退出码捕获测试 ==="
echo ""

# 测试1: 成功的命令
echo "测试1: 成功的命令 (ls /tmp)"
ls /tmp > /dev/null 2>&1
EXIT_CODE=$?
echo "  退出码: $EXIT_CODE (期望: 0)"
if [ $EXIT_CODE -eq 0 ]; then
    echo "  ✓ 成功捕获"
else
    echo "  ✗ 捕获失败"
fi
echo ""

# 测试2: 失败的命令（文件不存在）
echo "测试2: 失败的命令 (cat /nonexistent_file)"
cat /nonexistent_file > /dev/null 2>&1
EXIT_CODE=$?
echo "  退出码: $EXIT_CODE (期望: 非0)"
if [ $EXIT_CODE -ne 0 ]; then
    echo "  ✓ 成功捕获错误"
else
    echo "  ✗ 应该返回非零退出码"
fi
echo ""

# 测试3: 管道命令的退出码
echo "测试3: 管道命令 (ls /nonexistent | grep xxx)"
ls /nonexistent 2>/dev/null | grep xxx
EXIT_CODE=$?
echo "  退出码: $EXIT_CODE (注意：管道默认返回最后一个命令的退出码)"
echo ""

# 测试4: 使用 pipefail 选项
echo "测试4: 启用 pipefail 后的管道命令"
set -o pipefail
ls /nonexistent 2>/dev/null | grep xxx
EXIT_CODE=$?
echo "  退出码: $EXIT_CODE (启用 pipefail 后显示第一个失败命令的退出码)"
set +o pipefail
echo ""

# 测试5: Python 脚本的退出码
echo "测试5: Python 脚本退出码 (sys.exit(42))"
python3 -c "import sys; sys.exit(42)"
EXIT_CODE=$?
echo "  退出码: $EXIT_CODE (期望: 42)"
if [ $EXIT_CODE -eq 42 ]; then
    echo "  ✓ 成功捕获 Python 退出码"
else
    echo "  ✗ 退出码不匹配"
fi
echo ""

# 测试6: 在条件判断中捕获
echo "测试6: 在 if 语句中捕获退出码"
if grep -q "xyz123" /etc/passwd 2>/dev/null; then
    echo "  找到匹配"
else
    EXIT_CODE=$?
    echo "  未找到匹配, 退出码: $?"
fi
echo ""

# 测试7: 使用函数返回退出码
echo "测试7: 函数返回退出码"
check_file() {
    if [ -f "$1" ]; then
        return 0
    else
        return 1
    fi
}

check_file "/etc/passwd"
echo "  检查 /etc/passwd 存在: 退出码 $?"

check_file "/nonexistent"
echo "  检查 /nonexistent 存在: 退出码 $?"
echo ""

echo "=== 退出码捕获测试完成 ==="
