#!/bin/bash
#
# 自动化测试脚本 - 测试 pip install 后 Bot 实例自动创建文件功能
#

set -e  # 遇到错误立即退出

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 路径配置
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
PROJECT_DIR="$SCRIPT_DIR"
TEST_DIR="${PROJECT_DIR}/../test"
WHL_DIR="$PROJECT_DIR/dist"

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}  Clawdboz 自动化安装测试脚本${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# 步骤0: 清理所有运行中的 Bot 进程
echo -e "${YELLOW}[0/7] 清理所有运行中的 Bot 进程...${NC}"
# 查找并终止所有 bot 相关进程
BOT_PIDS=$(ps aux | grep -E "clawdboz|bot1\.py|bot0\.py" | grep -v grep | awk '{print $2}')
if [ -n "$BOT_PIDS" ]; then
    echo -e "${YELLOW}  发现运行中的 Bot 进程: $BOT_PIDS${NC}"
    echo "$BOT_PIDS" | xargs kill 2>/dev/null || true
    sleep 2
    # 检查是否还有残留进程
    REMAINING=$(ps aux | grep -E "clawdboz|bot1\.py|bot0\.py" | grep -v grep | awk '{print $2}')
    if [ -n "$REMAINING" ]; then
        echo -e "${YELLOW}  强制终止残留进程...${NC}"
        echo "$REMAINING" | xargs kill -9 2>/dev/null || true
        sleep 1
    fi
    echo -e "${GREEN}✓ Bot 进程已清理${NC}"
else
    echo -e "${GREEN}✓ 没有发现运行中的 Bot 进程${NC}"
fi
echo ""

# 步骤1: 清理旧的构建产物
echo -e "${YELLOW}[1/7] 清理旧的构建产物...${NC}"
rm -rf "$PROJECT_DIR/dist" "$PROJECT_DIR/build" "$PROJECT_DIR"/*.egg-info
rm -rf "$TEST_DIR"
echo -e "${GREEN}✓ 清理完成${NC}"
echo ""

# 步骤2: 构建 wheel 包
echo -e "${YELLOW}[2/7] 构建 wheel 包...${NC}"
cd "$PROJECT_DIR"
python3 -m build --wheel
if [ ! -d "$WHL_DIR" ] || [ -z "$(ls -A $WHL_DIR/*.whl 2>/dev/null)" ]; then
    echo -e "${RED}✗ 构建失败：未找到 .whl 文件${NC}"
    exit 1
fi
WHL_FILE=$(ls -t $WHL_DIR/*.whl | head -1)
echo -e "${GREEN}✓ 构建成功: $(basename $WHL_FILE)${NC}"
echo ""

# 步骤3: 创建测试目录
echo -e "${YELLOW}[3/7] 创建测试目录...${NC}"
# 如果存在旧的虚拟环境，先删除
if [ -d "$TEST_DIR/.venv" ]; then
    echo -e "${YELLOW}  删除旧的虚拟环境...${NC}"
    rm -rf "$TEST_DIR/.venv"
fi
# 如果 test_auto_create 目录存在，也删除
if [ -d "$TEST_DIR/test_auto_create" ]; then
    echo -e "${YELLOW}  删除旧的测试目录...${NC}"
    rm -rf "$TEST_DIR/test_auto_create"
fi
mkdir -p "$TEST_DIR"
echo -e "${GREEN}✓ 测试目录: $TEST_DIR${NC}"
echo ""

# 步骤4: 使用 uv 创建虚拟环境
echo -e "${YELLOW}[4/7] 使用 uv 创建虚拟环境...${NC}"
cd "$TEST_DIR"
if ! command -v uv &> /dev/null; then
    echo -e "${RED}✗ uv 未安装，请先安装 uv${NC}"
    echo "  安装方式: curl -LsSf https://astral.sh/uv/install.sh | sh"
    exit 1
fi

uv venv
echo -e "${GREEN}✓ 虚拟环境创建完成${NC}"
echo ""

# 步骤5: 安装 wheel 包
echo -e "${YELLOW}[5/7] 安装 wheel 包...${NC}"
source .venv/bin/activate
uv pip install "$WHL_FILE"
echo -e "${GREEN}✓ 安装完成${NC}"
echo ""

# 步骤6: 测试 Bot 实例自动创建文件
echo -e "${YELLOW}[6/7] 测试 Bot 实例自动创建文件...${NC}"

# 创建测试脚本目录
mkdir -p test_auto_create
cd test_auto_create

# 复制 ../bot1.py 到测试目录
if [ -f "$PROJECT_DIR/../bot1.py" ]; then
    cp "$PROJECT_DIR/../bot1.py" .
    echo -e "${GREEN}✓ 已复制 bot1.py 到测试目录${NC}"
else
    echo -e "${RED}✗ 未找到 ../bot1.py，将创建默认测试脚本${NC}"
    cat > bot1.py << 'EOF'
from clawdboz import Bot

bot = Bot(app_id="cli_a907c9018f7a9cc5", app_secret="5VDY7pUnBmQpT1MOiVjQEgRYXjhjdCA7")
bot.run()
EOF
fi

# 创建 Python 测试脚本 - 使用 bot1.py 作为实例
cat > test_bot.py << 'EOF'
import os
import sys
import subprocess
import time
import signal

print("[TEST] 当前目录文件列表（创建前）:")
for f in os.listdir('.'):
    print(f"  - {f}")

print("\n[TEST] 使用 subprocess 运行 bot1.py 创建 Bot 实例...")
print("[TEST] 注意: bot1.py 会自动创建 config.json 和其他必要文件")
print()

# 使用 subprocess 运行 bot1.py
# 给足够的时间让 Bot 初始化并创建文件（约需 5-8 秒）
proc = subprocess.Popen(
    [sys.executable, 'bot1.py'],
    stdout=subprocess.PIPE,
    stderr=subprocess.PIPE,
    text=True
)

# 等待文件创建（最长 15 秒）
print("[TEST] 等待 Bot 初始化并创建文件...")
max_wait = 15
for i in range(max_wait):
    time.sleep(1)
    # 检查关键文件是否已创建
    if os.path.exists('config.json') and os.path.exists('.bots.md'):
        print(f"[TEST] 文件已创建 (用时 {i+1} 秒)")
        break
    print(f"[TEST] 等待中... {i+1}/{max_wait} 秒")

# 终止 subprocess
print("[TEST] 终止 Bot 进程...")
proc.terminate()
try:
    proc.wait(timeout=5)
except:
    proc.kill()

print("\n[TEST] 当前目录文件列表（创建后）:")
for f in os.listdir('.'):
    print(f"  - {f}")

# 检查文件是否存在
errors = []
if not os.path.exists('.bots.md'):
    errors.append(".bots.md 未创建")
else:
    print("\n[TEST] ✓ .bots.md 已创建")
    with open('.bots.md', 'r') as f:
        content = f.read()
        if '嗑唠的宝子' in content:
            print("[TEST] ✓ .bots.md 内容正确")
        else:
            errors.append(".bots.md 内容不正确")

if not os.path.exists('bot_manager.sh'):
    errors.append("bot_manager.sh 未创建")
else:
    print("[TEST] ✓ bot_manager.sh 已创建")
    # 检查是否可执行
    if os.access('bot_manager.sh', os.X_OK):
        print("[TEST] ✓ bot_manager.sh 已设为可执行")
    else:
        errors.append("bot_manager.sh 未设为可执行")

if not os.path.exists('config.json'):
    errors.append("config.json 未创建")
else:
    print("[TEST] ✓ config.json 已创建")
    import json
    with open('config.json', 'r') as f:
        config = json.load(f)
    # 检查 start_script 是否设置为 bot1.py
    if config.get('start_script') == 'bot1.py':
        print("[TEST] ✓ config.json 中 start_script 正确设置为 bot1.py")
    else:
        actual = config.get('start_script', '未设置')
        print(f"[TEST] ℹ config.json 中 start_script: {actual} (期望: bot1.py)")

if errors:
    print("\n[TEST] ✗ 测试失败:")
    for e in errors:
        print(f"  - {e}")
    sys.exit(1)
else:
    print("\n[TEST] ✓ 所有测试通过!")
    sys.exit(0)
EOF

# 运行测试
python3 test_bot.py
TEST_RESULT=$?

echo ""
cd "$TEST_DIR"

# 清理
if [ $TEST_RESULT -eq 0 ]; then
    echo -e "${GREEN}========================================${NC}"
    echo -e "${GREEN}  所有测试通过! ✓${NC}"
    echo -e "${GREEN}========================================${NC}"
else
    echo -e "${RED}========================================${NC}"
    echo -e "${RED}  测试失败 ✗${NC}"
    echo -e "${RED}========================================${NC}"
fi

echo ""

# 步骤7: 启动 Bot
if [ $TEST_RESULT -eq 0 ]; then
    echo -e "${YELLOW}[7/7] 启动 Bot (bot1.py)...${NC}"
    cd "$TEST_DIR/test_auto_create"
    
    # 使用虚拟环境中的 Python 启动 bot1.py
    nohup "$TEST_DIR/.venv/bin/python3" bot1.py > logs/bot_output.log 2>&1 &
    BOT_PID=$!
    
    # 等待 Bot 启动
    echo -e "${YELLOW}  等待 Bot 启动...${NC}"
    sleep 3
    
    # 检查进程是否还在运行
    if kill -0 $BOT_PID 2>/dev/null; then
        echo -e "${GREEN}✓ Bot 已启动 (PID: $BOT_PID)${NC}"
        echo -e "${BLUE}  日志文件: $TEST_DIR/test_auto_create/logs/bot_debug.log${NC}"
        echo -e "${BLUE}  停止命令: kill $BOT_PID${NC}"
    else
        echo -e "${RED}✗ Bot 启动失败，请检查日志${NC}"
        TEST_RESULT=1
    fi
else
    echo -e "${YELLOW}[7/7] 跳过启动 Bot（测试未通过）${NC}"
fi

echo ""
echo -e "${BLUE}测试目录: $TEST_DIR/test_auto_create${NC}"

exit $TEST_RESULT
