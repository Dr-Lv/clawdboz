#!/bin/bash
#
# 飞书 Bot 管理脚本
# 功能：启动、停止、重启、状态查看、测试
#

# 基础配置
BOT_NAME="feishu_bot"
BOT_MODULE="src.main"
BOT_SCRIPT="clawdboz.py"  # 兼容入口，仍用于检测进程

# 获取脚本所在目录（作为默认项目根目录）
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"

# 加载配置文件
CONFIG_FILE="$SCRIPT_DIR/config.json"
if [ ! -f "$CONFIG_FILE" ]; then
    echo "[ERROR] 配置文件不存在: $CONFIG_FILE"
    exit 1
fi

# 使用 Python 解析配置文件
get_config() {
    python3 -c "import json; c=json.load(open('$CONFIG_FILE')); print(c$1)" 2>/dev/null
}

# 获取项目根目录（优先环境变量 LARKBOT_ROOT，其次 config.json 中的 project_root）
PROJECT_ROOT="${LARKBOT_ROOT:-}"
if [ -z "$PROJECT_ROOT" ]; then
    PROJECT_ROOT_CONFIG=$(get_config "['project_root']" || echo '.')
    if [ "${PROJECT_ROOT_CONFIG:0:1}" = "/" ]; then
        # 绝对路径
        PROJECT_ROOT="$PROJECT_ROOT_CONFIG"
    else
        # 相对路径，相对于脚本所在目录
        PROJECT_ROOT="$SCRIPT_DIR/$PROJECT_ROOT_CONFIG"
    fi
fi
# 规范化路径
PROJECT_ROOT="$(cd "$PROJECT_ROOT" && pwd)"

# 导出项目根目录环境变量（供 Python 脚本使用）
export LARKBOT_ROOT="$PROJECT_ROOT"

PID_FILE="/tmp/${BOT_NAME}.pid"
VENV_DIR="$PROJECT_ROOT/.venv"
PYTHON_BIN="$VENV_DIR/bin/python"
KIMI_DIR="/root/.local/bin/"

# 日志路径（从配置文件读取，基于项目根目录）
LOG_FILE="$PROJECT_ROOT/$(get_config "['logs']['main_log']" || echo 'logs/main.log')"
DEBUG_LOG="$PROJECT_ROOT/$(get_config "['logs']['debug_log']" || echo 'logs/bot_debug.log')"
# WebSocket 连接日志在 bot_output.log
BOT_OUTPUT_LOG="$PROJECT_ROOT/logs/bot_output.log"
FEISHU_API_LOG="$PROJECT_ROOT/$(get_config "['logs']['feishu_api_log']" || echo 'logs/feishu_api.log')"
OPS_LOG="$PROJECT_ROOT/$(get_config "['logs']['ops_log']" || echo 'logs/ops_check.log')"

# 飞书通知配置（优先环境变量，其次配置文件）
NOTIFICATION_ENABLED=$(get_config "['notification']['enabled']" || echo 'true')
ENABLE_FEISHU_NOTIFY="${ENABLE_FEISHU_NOTIFY:-$NOTIFICATION_ENABLED}"
NOTIFY_SCRIPT_NAME=$(get_config "['notification']['script']" || echo 'feishu_tools/notify_feishu.py')
NOTIFY_SCRIPT="$PROJECT_ROOT/$NOTIFY_SCRIPT_NAME"

# SSL 证书配置（解决 WebSocket SSL 连接问题）
CERT_PATH="$VENV_DIR/lib/python3.10/site-packages/certifi/cacert.pem"
if [ -f "$CERT_PATH" ]; then
    export SSL_CERT_FILE="$CERT_PATH"
    export REQUESTS_CA_BUNDLE="$CERT_PATH"
fi

# QVeris API Key 配置（优先环境变量，其次配置文件）
QVERIS_API_KEY_CONFIG=$(get_config "['qveris']['api_key']" || echo '')
export QVERIS_API_KEY="${QVERIS_API_KEY:-$QVERIS_API_KEY_CONFIG}"

# 确保日志目录存在
mkdir -p "$(dirname "$LOG_FILE")" "$(dirname "$DEBUG_LOG")" "$(dirname "$FEISHU_API_LOG")" "$(dirname "$OPS_LOG")" 2>/dev/null

# 颜色定义
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

# 获取当前时间
get_time() {
    date '+%Y-%m-%d %H:%M:%S'
}

# 打印信息
info() {
    echo -e "${BLUE}[$(get_time)] INFO:${NC} $1"
}

# 打印成功
success() {
    echo -e "${GREEN}[$(get_time)] SUCCESS:${NC} $1"
}

# 打印警告
warn() {
    echo -e "${YELLOW}[$(get_time)] WARN:${NC} $1"
}

# 打印错误
error() {
    echo -e "${RED}[$(get_time)] ERROR:${NC} $1"
}

# 检查是否在运行
check_running() {
    # 尝试通过进程名查找，排除 kimi-cli 进程
    local pid_list=$(pgrep -f "python.*(clawdboz|src/main|src\.main)" 2>/dev/null | while read pid; do
        # 检查该进程的命令行是否包含 kimi，如果包含则跳过
        if ! cat /proc/$pid/cmdline 2>/dev/null | tr '\0' ' ' | grep -q "kimi"; then
            echo "$pid"
        fi
    done)
    if [ -n "$pid_list" ]; then
        local pid=$(echo "$pid_list" | head -1)
        echo "$pid" > "$PID_FILE"
        echo "$pid"
        return 0
    fi
    
    # 清理 PID 文件
    rm -f "$PID_FILE"
    return 1
}

# 启动 Bot
start() {
    info "正在启动 $BOT_NAME..."
    
    # 检查是否已在运行
    local existing_pid
    existing_pid=$(check_running)
    if [ $? -eq 0 ] && [ -n "$existing_pid" ]; then
        warn "$BOT_NAME 已在运行 (PID: $existing_pid)"
        return 1
    fi
    
    # 清理旧日志
    info "清理旧日志..."
    > "$LOG_FILE" 2>/dev/null
    > "$DEBUG_LOG" 2>/dev/null
    
    # 检查脚本是否存在
    # 检查 src 目录是否存在
    if [ ! -d "$PROJECT_ROOT/src" ]; then
        error "找不到 src 目录: $PROJECT_ROOT/src"
        return 1
    fi
    
    # 进入工作目录
    cd "$PROJECT_ROOT" || {
        error "无法进入目录: $PROJECT_ROOT"
        return 1
    }
    
    # 检查虚拟环境
    if [ ! -f "$PYTHON_BIN" ]; then
        error "虚拟环境不存在: $PYTHON_BIN"
        return 1
    fi

    # 启动 Bot（带环境变量）
    info "启动 Python 进程 (使用虚拟环境)..."
    if [ -f "$CERT_PATH" ]; then
        export SSL_CERT_FILE="$CERT_PATH"
        export REQUESTS_CA_BUNDLE="$CERT_PATH"
    fi
    nohup "$PYTHON_BIN" -m "$BOT_MODULE" > "$LOG_FILE" 2>&1 &
    local pid=$!
    
    # 等待启动
    sleep 2
    
    # 检查是否成功启动
    if ps -p "$pid" > /dev/null 2>&1; then
        echo "$pid" > "$PID_FILE"
        success "$BOT_NAME 启动成功 (PID: $pid)"
        info "日志文件: $LOG_FILE"
        info "调试日志: $DEBUG_LOG"
        
        # 显示启动信息
        sleep 1
        local ws_log_file="$BOT_OUTPUT_LOG"
        if [ ! -f "$ws_log_file" ]; then
            ws_log_file="$LOG_FILE"
        fi
        local ws_status=$(grep "connected to wss" "$ws_log_file" 2>/dev/null | tail -1)
        if [ -n "$ws_status" ]; then
            success "WebSocket 连接成功"
        else
            warn "等待 WebSocket 连接中..."
        fi
        
        return 0
    else
        error "$BOT_NAME 启动失败"
        return 1
    fi
}

# 停止 Bot
stop() {
    info "正在停止 $BOT_NAME..."
    
    local pid
    pid=$(check_running)
    if [ $? -ne 0 ] || [ -z "$pid" ]; then
        warn "$BOT_NAME 未在运行"
        rm -f "$PID_FILE"
        return 0
    fi
    
    info "正在终止进程 (PID: $pid)..."
    
    # 先尝试优雅终止
    kill "$pid" 2>/dev/null
    
    # 等待进程结束
    local count=0
    while [ $count -lt 10 ]; do
        if ! ps -p "$pid" > /dev/null 2>&1; then
            success "$BOT_NAME 已停止"
            rm -f "$PID_FILE"
            return 0
        fi
        sleep 1
        count=$((count + 1))
    done
    
    # 强制终止
    warn "强制终止进程..."
    kill -9 "$pid" 2>/dev/null
    sleep 1
    
    if ! ps -p "$pid" > /dev/null 2>&1; then
        success "$BOT_NAME 已强制停止"
        rm -f "$PID_FILE"
        return 0
    else
        error "无法停止 $BOT_NAME"
        return 1
    fi
}

# 重启 Bot
restart() {
    info "正在重启 $BOT_NAME..."
    stop
    sleep 2
    start
}

# 查看状态
status() {
    local pid
    pid=$(check_running)
    
    if [ $? -eq 0 ] && [ -n "$pid" ]; then
        success "$BOT_NAME 正在运行 (PID: $pid)"
        
        # 获取进程信息
        local cpu_mem=$(ps -o %cpu,%mem -p "$pid" | tail -1)
        info "CPU/内存: $cpu_mem"
        
        # 检查 WebSocket 连接（优先检查 bot_output.log）
        local ws_log_file="$BOT_OUTPUT_LOG"
        if [ ! -f "$ws_log_file" ]; then
            ws_log_file="$LOG_FILE"
        fi
        if grep -q "connected to wss" "$ws_log_file" 2>/dev/null; then
            success "WebSocket 状态: 已连接"
        else
            warn "WebSocket 状态: 未连接或连接中"
        fi
        
        # 显示最近的日志
        info "最近 3 条日志:"
        tail -3 "$DEBUG_LOG" 2>/dev/null | while read line; do
            echo "  $line"
        done
        
        return 0
    else
        error "$BOT_NAME 未运行"
        return 1
    fi
}

# 查看日志
log() {
    local lines=${1:-20}
    
    if [ ! -f "$DEBUG_LOG" ]; then
        error "日志文件不存在: $DEBUG_LOG"
        return 1
    fi
    
    echo -e "${BLUE}=== 最近 $lines 条调试日志 ===${NC}"
    tail -n "$lines" "$DEBUG_LOG"
}

# 实时查看日志
follow() {
    if [ ! -f "$DEBUG_LOG" ]; then
        error "日志文件不存在: $DEBUG_LOG"
        return 1
    fi
    
    info "正在跟踪日志 (按 Ctrl+C 退出)..."
    tail -f "$DEBUG_LOG"
}

# 测试 Bot
test_bot_func() {
    info "测试 $BOT_NAME 功能..."
    
    local pid
    pid=$(check_running)
    if [ $? -ne 0 ] || [ -z "$pid" ]; then
        error "$BOT_NAME 未运行，先启动服务"
        return 1
    fi
    
    success "$BOT_NAME 正在运行 (PID: $pid)"
    
    # 检查 WebSocket 连接（优先检查 bot_output.log）
    local ws_log_file="$BOT_OUTPUT_LOG"
    if [ ! -f "$ws_log_file" ]; then
        ws_log_file="$LOG_FILE"
    fi
    if grep -q "connected to wss" "$ws_log_file" 2>/dev/null; then
        success "✓ WebSocket 连接正常"
    else
        error "✗ WebSocket 未连接"
        return 1
    fi
    
    # 检查最近的错误
    local recent_errors=$(tail -100 "$DEBUG_LOG" 2>/dev/null | grep -i "error\|exception\|fail" | wc -l)
    if [ "$recent_errors" -eq 0 ]; then
        success "✓ 最近无错误日志"
    else
        warn "✗ 发现 $recent_errors 条错误日志"
    fi
    
    # 检查 ACP 会话
    local acp_sessions=$(grep "ACP 会话创建成功" "$DEBUG_LOG" 2>/dev/null | wc -l)
    if [ "$acp_sessions" -gt 0 ]; then
        success "✓ ACP 会话创建成功 ($acp_sessions 次)"
    fi
    
    # 检查消息处理
    local messages=$(grep "on_message 被调用" "$DEBUG_LOG" 2>/dev/null | wc -l)
    if [ "$messages" -gt 0 ]; then
        success "✓ 已处理 $messages 条消息"
    else
        warn "⚠ 尚未处理消息"
    fi
    
    # 显示统计
    echo ""
    info "日志统计:"
    echo "  总日志行数: $(wc -l < "$DEBUG_LOG" 2>/dev/null)"
    echo "  错误数: $(grep -c "ERROR" "$DEBUG_LOG" 2>/dev/null || echo 0)"
    echo "  警告数: $(grep -c "WARN" "$DEBUG_LOG" 2>/dev/null || echo 0)"
    
    return 0
}

# 测试发送消息到飞书
test_send() {
    local chat_id=${1:-"oc_d24a689f16656bb78b5a6b75c5a2b552"}
    local message=${2:-"测试消息：Bot 运行正常 🎉"}
    
    info "发送测试消息到飞书..."
    info "Chat ID: $chat_id"
    info "消息: $message"
    
    cd "$PROJECT_ROOT" || return 1
    
    # 设置 SSL 环境变量
    if [ -f "$CERT_PATH" ]; then
        export SSL_CERT_FILE="$CERT_PATH"
        export REQUESTS_CA_BUNDLE="$CERT_PATH"
    fi
    
    python -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT')
from src import LarkBot
import json

bot = LarkBot()  # 从配置文件读取凭证
result = bot.reply_text('\$chat_id', '\$message', streaming=False)
if result:
    print('消息发送成功')
else:
    print('消息发送失败')
    sys.exit(1)
" 2>&1
    
    if [ $? -eq 0 ]; then
        success "测试消息已发送"
    else
        error "测试消息发送失败"
    fi
}

# 测试流式消息
test_streaming() {
    local chat_id=${1:-"oc_d24a689f16656bb78b5a6b75c5a2b552"}
    local message=${2:-"用3个要点介绍你自己，每点之间停顿一下"}
    
    info "发送流式测试消息到飞书..."
    info "Chat ID: $chat_id"
    info "消息: $message"
    
    cd "$PROJECT_ROOT" || return 1
    
    python -c "
import sys
sys.path.insert(0, '$PROJECT_ROOT')
from src import LarkBot

bot = LarkBot()  # 从配置文件读取凭证
print('启动流式处理...')
bot.run_msg_script_streaming('\$chat_id', '\$message')
" 2>&1 &
    
    local pid=$!
    info "流式处理进程 PID: $pid"
    info "等待15秒让流式处理完成..."
    sleep 15
    
    # 显示对比日志
    echo ""
    info "=== 流式日志对比 ==="
    echo ""
    echo "[ACP 调试日志 - bot_debug.log]"
    tail -50 "$DEBUG_LOG" 2>/dev/null | grep -E "STREAM|CHUNK|CONTENT|通知"
    echo ""
    echo "[飞书 API 日志 - feishu_api.log]"
    tail -50 "$FEISHU_API_LOG" 2>/dev/null
}

# 清理日志
clean() {
    info "清理日志文件..."
    
    > "$LOG_FILE" 2>/dev/null && success "已清空: log"
    > "$DEBUG_LOG" 2>/dev/null && success "已清空: bot_debug.log"
    
    info "清理完成"
}

# 记录运维日志
log_ops() {
    local level="$1"
    local message="$2"
    local timestamp=$(get_time)
    local log_dir=$(dirname "$OPS_LOG")
    
    # 确保日志目录存在
    mkdir -p "$log_dir" 2>/dev/null
    
    # 写入日志文件
    echo "[$timestamp] [$level] $message" >> "$OPS_LOG"
}

# 发送飞书通知
notify_feishu() {
    local command="$1"
    local message="${2:-}"
    
    # 检查是否启用通知
    if [ "$ENABLE_FEISHU_NOTIFY" != "true" ]; then
        return 0
    fi
    
    # 检查通知脚本是否存在
    if [ ! -f "$NOTIFY_SCRIPT" ]; then
        warn "通知脚本不存在: $NOTIFY_SCRIPT"
        return 1
    fi
    
    # 检查上下文文件是否存在（确保有聊天信息）
    local context_file="$PROJECT_ROOT/WORKPLACE/mcp_context.json"
    if [ ! -f "$context_file" ]; then
        warn "上下文文件不存在，跳过飞书通知"
        return 1
    fi
    
    # 发送通知（后台执行，不阻塞）
    case "$command" in
        check_start)
            (python3 "$NOTIFY_SCRIPT" check_start >/dev/null 2>&1 &)
            ;;
        issues_found)
            (python3 "$NOTIFY_SCRIPT" issues_found "$message" >/dev/null 2>&1 &)
            ;;
        repair_success)
            (python3 "$NOTIFY_SCRIPT" repair_success >/dev/null 2>&1 &)
            ;;
        repair_failed)
            (python3 "$NOTIFY_SCRIPT" repair_failed "$message" >/dev/null 2>&1 &)
            ;;
        check_passed)
            (python3 "$NOTIFY_SCRIPT" check_passed >/dev/null 2>&1 &)
            ;;
    esac
}

# 检查和修复 Bot
check() {
    info "开始检查 Bot 状态..."
    
    # 记录运维检查开始
    log_ops "INFO" "========== 运维检查开始 =========="
    
    local has_error=0
    local error_details=""
    local check_results=""
    
    # 1. 检查 Bot 进程状态
    info "检查 Bot 进程..."
    local pid
    pid=$(check_running)
    if [ $? -ne 0 ] || [ -z "$pid" ]; then
        error "✗ Bot 未运行"
        has_error=1
        error_details="${error_details}\n- Bot 进程未运行"
        log_ops "ERROR" "Bot 进程未运行"
        check_results="${check_results}\n[FAIL] Bot 进程: 未运行"
    else
        success "✓ Bot 正在运行 (PID: $pid)"
        log_ops "INFO" "Bot 进程正常，PID: $pid"
        check_results="${check_results}\n[OK] Bot 进程: 运行中 (PID: $pid)"
        
        # 检查 CPU 和内存使用
        local cpu_mem=$(ps -o %cpu,%mem -p "$pid" | tail -1)
        local cpu=$(echo "$cpu_mem" | awk '{print $1}')
        local mem=$(echo "$cpu_mem" | awk '{print $2}')
        log_ops "INFO" "资源使用: CPU ${cpu}%, 内存 ${mem}%"
        
        # 检查资源使用是否异常
        if (( $(echo "$cpu > 80" | bc -l 2>/dev/null || echo "0") )); then
            warn "⚠ CPU 使用率过高: ${cpu}%"
            has_error=1
            error_details="${error_details}\n- CPU 使用率过高: ${cpu}%"
            log_ops "WARN" "CPU 使用率过高: ${cpu}%"
            check_results="${check_results}\n[WARN] CPU 使用率: ${cpu}%"
        fi
        if (( $(echo "$mem > 50" | bc -l 2>/dev/null || echo "0") )); then
            warn "⚠ 内存使用率过高: ${mem}%"
            has_error=1
            error_details="${error_details}\n- 内存使用率过高: ${mem}%"
            log_ops "WARN" "内存使用率过高: ${mem}%"
            check_results="${check_results}\n[WARN] 内存使用率: ${mem}%"
        fi
    fi
    
    # 2. 检查 WebSocket 连接
    info "检查 WebSocket 连接..."
    # 优先检查 bot_output.log，如果不存在则检查 main.log
    local ws_log_file="$BOT_OUTPUT_LOG"
    if [ ! -f "$ws_log_file" ]; then
        ws_log_file="$LOG_FILE"
    fi
    
    if [ -f "$ws_log_file" ]; then
        if grep -q "connected to wss" "$ws_log_file" 2>/dev/null; then
            success "✓ WebSocket 已连接"
            log_ops "INFO" "WebSocket 连接正常"
            check_results="${check_results}\n[OK] WebSocket: 已连接"
        else
            error "✗ WebSocket 未连接"
            has_error=1
            error_details="${error_details}\n- WebSocket 连接失败"
            log_ops "ERROR" "WebSocket 未连接"
            check_results="${check_results}\n[FAIL] WebSocket: 未连接"
        fi
        
        # 检查是否有连接错误
        local ws_errors=$(grep "WebSocket.*error\|wss.*error\|connection.*closed" "$ws_log_file" 2>/dev/null | wc -l)
        if [ "$ws_errors" -gt 0 ]; then
            warn "⚠ 发现 $ws_errors 次 WebSocket 错误"
            has_error=1
            error_details="${error_details}\n- WebSocket 连接错误次数: $ws_errors"
            log_ops "WARN" "WebSocket 错误次数: $ws_errors"
            check_results="${check_results}\n[WARN] WebSocket 错误: $ws_errors 次"
        fi
    else
        warn "⚠ 日志文件不存在，跳过 WebSocket 检查"
        log_ops "WARN" "日志文件不存在，跳过 WebSocket 检查"
        check_results="${check_results}\n[SKIP] WebSocket: 日志文件不存在"
    fi
    
    # 3. 检查日志错误（只检查最近 40 分钟内的）
    info "检查日志错误（最近40分钟）..."
    if [ -f "$DEBUG_LOG" ]; then
        # 获取当前时间戳
        local current_timestamp=$(date +%s)
        local time_threshold=2400  # 40分钟 = 2400秒
        local recent_errors=0
        local error_lines=""
        
        # 读取最近 100 条日志，检查时间戳
        while IFS= read -r line; do
            # 尝试提取时间戳 [HH:MM:SS] 或 2026-02-13 HH:MM:SS 格式
            local log_time=$(echo "$line" | grep -oE '\[[0-9]{2}:[0-9]{2}:[0-9]{2}\]' | tr -d '[]' || \
                             echo "$line" | grep -oE '[0-9]{4}-[0-9]{2}-[0-9]{2} [0-9]{2}:[0-9]{2}:[0-9]{2}' | awk '{print $2}')
            
            if [ -n "$log_time" ]; then
                # 将日志时间转换为秒（今天）
                local log_hour=$(echo "$log_time" | cut -d: -f1)
                local log_min=$(echo "$log_time" | cut -d: -f2)
                local log_sec=$(echo "$log_time" | cut -d: -f3)
                local log_timestamp=$(date -d "${log_hour}:${log_min}:${log_sec}" +%s 2>/dev/null || echo 0)
                
                # 处理跨天情况（如果日志时间比当前时间晚，认为是昨天的日志）
                if [ $log_timestamp -gt $current_timestamp ]; then
                    log_timestamp=$((log_timestamp - 86400))
                fi
                
                # 检查是否是错误日志且在 10 分钟内
                local time_diff=$((current_timestamp - log_timestamp))
                if [ $time_diff -le $time_threshold ] && [ $time_diff -ge -60 ]; then
                    if echo "$line" | grep -qiE "ERROR|Exception|Traceback|Failed"; then
                        recent_errors=$((recent_errors + 1))
                        error_lines="${error_lines}${line}\n"
                    fi
                fi
            else
                # 没有时间戳的行，如果包含错误关键词也算（保守策略）
                if echo "$line" | grep -qiE "ERROR|Exception|Traceback|Failed"; then
                    recent_errors=$((recent_errors + 1))
                    error_lines="${error_lines}${line}\n"
                fi
            fi
        done < <(tail -100 "$DEBUG_LOG" 2>/dev/null)
        
        if [ "$recent_errors" -gt 0 ]; then
            error "✗ 最近40分钟日志中发现 $recent_errors 个错误"
            has_error=1
            error_details="${error_details}\n- 日志错误数: $recent_errors"
            log_ops "ERROR" "日志错误数(40分钟内): $recent_errors"
            check_results="${check_results}\n[FAIL] 日志错误: $recent_errors 个"
            
            # 显示具体错误
            info "最近的错误日志:"
            echo -e "$error_lines" | head -3 | while read line; do
                if [ -n "$line" ]; then
                    echo "  ${RED}$line${NC}"
                    log_ops "ERROR" "详细错误: $line"
                fi
            done
        else
            success "✓ 最近40分钟日志无错误"
            log_ops "INFO" "最近40分钟日志无错误"
            check_results="${check_results}\n[OK] 日志错误: 无"
        fi
        
        # 检查 MCP 连接错误
        local mcp_errors=$(grep "MCP.*error\|Failed to connect MCP" "$DEBUG_LOG" 2>/dev/null | wc -l)
        if [ "$mcp_errors" -gt 0 ]; then
            error "✗ 发现 $mcp_errors 次 MCP 连接错误"
            has_error=1
            error_details="${error_details}\n- MCP 连接错误次数: $mcp_errors"
            log_ops "ERROR" "MCP 连接错误次数: $mcp_errors"
            check_results="${check_results}\n[FAIL] MCP 错误: $mcp_errors 次"
        fi
    else
        warn "⚠ 调试日志不存在"
        log_ops "WARN" "调试日志不存在"
        check_results="${check_results}\n[SKIP] 日志检查: 调试日志不存在"
    fi
    
    # 4. 检查 MCP 配置
    info "检查 MCP 配置..."
    if [ -f "$PROJECT_ROOT/.kimi/mcp.json" ]; then
        if grep -q "mcp_feishu_file_server.py" "$PROJECT_ROOT/.kimi/mcp.json" 2>/dev/null; then
            success "✓ MCP 配置文件存在"
            log_ops "INFO" "MCP 配置文件存在"
            check_results="${check_results}\n[OK] MCP 配置: 存在"
            
            # 检查路径是否正确
            local mcp_path=$(grep -o '/[^"]*mcp_feishu_file_server.py' "$PROJECT_ROOT/.kimi/mcp.json" 2>/dev/null)
            if [ -f "$mcp_path" ]; then
                success "✓ MCP Server 脚本存在"
                log_ops "INFO" "MCP Server 脚本存在: $mcp_path"
                check_results="${check_results}\n[OK] MCP 脚本: 存在"
            else
                error "✗ MCP Server 脚本不存在: $mcp_path"
                has_error=1
                error_details="${error_details}\n- MCP Server 脚本路径错误: $mcp_path"
                log_ops "ERROR" "MCP Server 脚本不存在: $mcp_path"
                check_results="${check_results}\n[FAIL] MCP 脚本: 不存在"
            fi
        else
            error "✗ MCP 配置中找不到 send_feishu_file"
            has_error=1
            error_details="${error_details}\n- MCP 配置不完整"
            log_ops "ERROR" "MCP 配置不完整"
            check_results="${check_results}\n[FAIL] MCP 配置: 不完整"
        fi
    else
        error "✗ MCP 配置文件不存在"
        has_error=1
        error_details="${error_details}\n- MCP 配置文件缺失"
        log_ops "ERROR" "MCP 配置文件缺失"
        check_results="${check_results}\n[FAIL] MCP 配置: 缺失"
    fi
    
    # 5. 检查 Skills
    info "检查 Skills..."
    local skills_dir="$PROJECT_ROOT/.kimi/skills"
    if [ -d "$skills_dir" ]; then
        local skill_count=$(find "$skills_dir" -name "SKILL.md" 2>/dev/null | wc -l)
        success "✓ 发现 $skill_count 个 Skills"
        log_ops "INFO" "Skills 数量: $skill_count"
        check_results="${check_results}\n[OK] Skills: $skill_count 个"
    else
        warn "⚠ Skills 目录不存在"
        log_ops "WARN" "Skills 目录不存在"
        check_results="${check_results}\n[WARN] Skills: 目录不存在"
    fi
    
    # 6. 检查上下文文件
    info "检查 MCP 上下文..."
    local context_file="$PROJECT_ROOT/WORKPLACE/mcp_context.json"
    if [ -f "$context_file" ]; then
        success "✓ MCP 上下文文件存在"
        log_ops "INFO" "MCP 上下文文件存在"
        check_results="${check_results}\n[OK] MCP 上下文: 存在"
        
        # 检查是否过期
        local context_time=$(python3 -c "import json,time,sys; d=json.load(open('$context_file')); print(d.get('timestamp',0))" 2>/dev/null || echo 0)
        local current_time=$(date +%s)
        local time_diff=$((current_time - ${context_time%.*}))
        if [ $time_diff -gt 86400 ]; then
            warn "⚠ MCP 上下文已过期 ($((time_diff/3600)) 小时前)"
            has_error=1
            error_details="${error_details}\n- MCP 上下文过期"
            log_ops "WARN" "MCP 上下文已过期 ($((time_diff/60)) 分钟前)"
            check_results="${check_results}\n[WARN] MCP 上下文: 已过期 $((time_diff/60)) 分钟"
        fi
    else
        warn "⚠ MCP 上下文文件不存在（将在收到消息时自动创建）"
        log_ops "WARN" "MCP 上下文文件不存在"
        check_results="${check_results}\n[WARN] MCP 上下文: 不存在"
    fi
    
    # 7. 检查虚拟环境
    info "检查虚拟环境..."
    if [ -f "$PYTHON_BIN" ]; then
        success "✓ 虚拟环境正常"
        log_ops "INFO" "虚拟环境正常"
        check_results="${check_results}\n[OK] 虚拟环境: 正常"
    else
        error "✗ 虚拟环境不存在"
        has_error=1
        error_details="${error_details}\n- 虚拟环境缺失"
        log_ops "ERROR" "虚拟环境缺失"
        check_results="${check_results}\n[FAIL] 虚拟环境: 缺失"
    fi
    
    echo ""
    info "检查完成"
    log_ops "INFO" "检查完成，结果汇总:$check_results"
    
    # 如果发现异常，调用 Kimi 进行修复
    if [ $has_error -eq 1 ]; then
        echo ""
        warn "发现异常，准备调用 Kimi 进行修复..."
        error "问题列表:$error_details"
        log_ops "ERROR" "发现异常，准备调用 Kimi 修复"
        log_ops "ERROR" "问题详情:$error_details"
        
        # 发送问题通知
        notify_feishu "issues_found" "$error_details"
        
        # 构建运维指令
        local repair_prompt="请修复飞书 Bot 的以下问题:$error_details

项目目录: $PROJECT_ROOT
当前工作目录: $(pwd)
Bot 进程状态: $(check_running && echo "运行中 (PID: $(check_running))" || echo "未运行")

请执行以下操作:
1. 分析问题原因
2. 修复所有检测到的问题
3. 确保 Bot 正常运行
4. 验证修复结果

Bot 主脚本: src/main.py (或兼容入口 clawdboz.py)
MCP 配置: .kimi/mcp.json
日志文件: logs/bot_debug.log, logs/main.log

如果需要重启 Bot，使用: ./bot_manager.sh restart"

        info "调用 Kimi 进行自动修复..."
        log_ops "INFO" "开始调用 Kimi 自动修复"
        cd "$PROJECT_ROOT" && $KIMI_DIR/kimi --yolo -p "$repair_prompt"
        local repair_result=$?
        
        if [ $repair_result -eq 0 ]; then
            log_ops "INFO" "Kimi 修复执行完成"
            # 发送修复成功通知
            notify_feishu "repair_success"
        else
            log_ops "ERROR" "Kimi 修复执行失败，退出码: $repair_result"
            # 发送修复失败通知
            notify_feishu "repair_failed" "Kimi 执行失败，退出码: $repair_result"
        fi
        
        echo ""
        info "Kimi 修复完成，重新检查状态..."
        log_ops "INFO" "Kimi 修复完成，准备重新检查"
        sleep 2
        status
        log_ops "INFO" "========== 运维检查结束（已修复）=========="
    else
        echo ""
        success "所有检查通过，Bot 运行正常！"
        log_ops "INFO" "所有检查通过，Bot 运行正常"
        # 无异常，不发送通知
        log_ops "INFO" "========== 运维检查结束（正常）=========="
    fi
}

# 初始化项目配置
init() {
    local auto_mode="${2:-}"  # 如果传入 --auto 则自动设置
    
    info "初始化 Bot 配置..."
    
    local current_project_root=$(get_config "['project_root']" 2>/dev/null || echo '.')
    local detected_root="$SCRIPT_DIR"
    
    echo ""
    echo "当前配置:"
    echo "  project_root (config.json): $current_project_root"
    echo "  脚本所在目录: $detected_root"
    echo "  环境变量 LARKBOT_ROOT: ${LARKBOT_ROOT:-未设置}"
    echo ""
    
    # 检查当前配置是否正确
    if [ "$current_project_root" = "." ] || [ -z "$current_project_root" ]; then
        warn "project_root 未设置或为默认值 '.'"
        
        if [ "$auto_mode" = "--auto" ]; then
            info "自动模式：正在设置 project_root..."
            confirm="y"
        else
            # 检查是否在交互式终端
            if [ -t 0 ]; then
                read -p "是否将 project_root 设置为脚本所在目录? [Y/n]: " confirm
            else
                warn "非交互式终端，使用 --auto 参数可自动设置"
                return 1
            fi
        fi
        
        if [ -z "$confirm" ] || [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
            # 使用 Python 更新 config.json
            python3 << PYEOF
import json
import os
import re

config_path = "$CONFIG_FILE"
detected_root = "$detected_root"

try:
    # 更新 config.json
    with open(config_path, 'r', encoding='utf-8') as f:
        config = json.load(f)
    
    config['project_root'] = detected_root
    
    with open(config_path, 'w', encoding='utf-8') as f:
        json.dump(config, f, indent=2, ensure_ascii=False)
    
    print("✓ 已更新 project_root: {}".format(detected_root))
    
    # 更新 .kimi/mcp.json 中的路径
    mcp_config_path = os.path.join(detected_root, '.kimi', 'mcp.json')
    if os.path.exists(mcp_config_path):
        with open(mcp_config_path, 'r', encoding='utf-8') as f:
            mcp_config = json.load(f)
        
        # 获取旧的项目根目录（从 mcp.json 中的路径推断）
        old_root = None
        mcp_servers = mcp_config.get('mcpServers', {})
        for server_name, server_config in mcp_servers.items():
            if 'command' in server_config:
                cmd = server_config['command']
                # 匹配类似 /project/larkbot/.venv/bin/python3 的路径
                match = re.match(r'^(/[^/]+/[^/]+)/\.venv/', cmd)
                if match:
                    old_root = match.group(1)
                    break
        
        if old_root and old_root != detected_root:
            # 替换所有路径
            updated = False
            for server_name, server_config in mcp_servers.items():
                # 更新 command
                if 'command' in server_config and old_root in server_config['command']:
                    server_config['command'] = server_config['command'].replace(old_root, detected_root)
                    updated = True
                # 更新 args
                if 'args' in server_config:
                    server_config['args'] = [arg.replace(old_root, detected_root) for arg in server_config['args']]
                    updated = True
                # 更新 env
                if 'env' in server_config:
                    for key in server_config['env']:
                        if old_root in str(server_config['env'][key]):
                            server_config['env'][key] = server_config['env'][key].replace(old_root, detected_root)
                            updated = True
            
            if updated:
                with open(mcp_config_path, 'w', encoding='utf-8') as f:
                    json.dump(mcp_config, f, indent=2, ensure_ascii=False)
                print("✓ 已更新 mcp.json 路径: {} -> {}".format(old_root, detected_root))
            else:
                print("  mcp.json 路径已正确，无需更新")
        else:
            print("  mcp.json 路径已正确，无需更新")
    else:
        print("  未找到 mcp.json，跳过")
        
except Exception as e:
    print(f"✗ 更新失败: {e}")
    exit(1)
PYEOF
            if [ $? -eq 0 ]; then
                success "初始化完成！"
                info "重新加载配置..."
                # 重新加载配置
                PROJECT_ROOT="$detected_root"
                export LARKBOT_ROOT="$PROJECT_ROOT"
                echo ""
                echo "新的项目根目录: $PROJECT_ROOT"
            else
                error "初始化失败"
                return 1
            fi
        else
            info "已取消"
            return 0
        fi
    else
        success "project_root 已设置为: $current_project_root"
        
        # 检查配置的路径是否存在
        if [ ! -d "$current_project_root" ]; then
            warn "配置的 project_root 目录不存在: $current_project_root"
            
            if [ "$auto_mode" = "--auto" ]; then
                confirm="y"
            elif [ -t 0 ]; then
                read -p "是否修复为脚本所在目录? [Y/n]: " confirm
            else
                return 1
            fi
            
            if [ -z "$confirm" ] || [ "$confirm" = "y" ] || [ "$confirm" = "Y" ]; then
                python3 << PYEOF
import json
import os
import re

config_path = "$CONFIG_FILE"
detected_root = "$detected_root"

with open(config_path, 'r', encoding='utf-8') as f:
    config = json.load(f)
config['project_root'] = detected_root
with open(config_path, 'w', encoding='utf-8') as f:
    json.dump(config, f, indent=2, ensure_ascii=False)
print("✓ 已修复 project_root")

# 更新 .kimi/mcp.json 中的路径
mcp_config_path = os.path.join(detected_root, '.kimi', 'mcp.json')
if os.path.exists(mcp_config_path):
    with open(mcp_config_path, 'r', encoding='utf-8') as f:
        mcp_config = json.load(f)
    
    # 获取旧的项目根目录（从 mcp.json 中的路径推断）
    old_root = None
    mcp_servers = mcp_config.get('mcpServers', {})
    for server_name, server_config in mcp_servers.items():
        if 'command' in server_config:
            cmd = server_config['command']
            match = re.match(r'^(/[^/]+/[^/]+)/\.venv/', cmd)
            if match:
                old_root = match.group(1)
                break
    
    if old_root and old_root != detected_root:
        updated = False
        for server_name, server_config in mcp_servers.items():
            if 'command' in server_config and old_root in server_config['command']:
                server_config['command'] = server_config['command'].replace(old_root, detected_root)
                updated = True
            if 'args' in server_config:
                server_config['args'] = [arg.replace(old_root, detected_root) for arg in server_config['args']]
                updated = True
            if 'env' in server_config:
                for key in server_config['env']:
                    if old_root in str(server_config['env'][key]):
                        server_config['env'][key] = server_config['env'][key].replace(old_root, detected_root)
                        updated = True
        
        if updated:
            with open(mcp_config_path, 'w', encoding='utf-8') as f:
                json.dump(mcp_config, f, indent=2, ensure_ascii=False)
            print("✓ 已更新 mcp.json 路径: {} -> {}".format(old_root, detected_root))
        else:
            print("  mcp.json 路径已正确，无需更新")
    else:
        print("  mcp.json 路径已正确，无需更新")
else:
    print("  未找到 mcp.json，跳过")
PYEOF
                success "修复完成！"
            fi
        fi
    fi
    
    echo ""
    info "配置检查:"
    echo "  项目根目录: $(get_config "['project_root']" 2>/dev/null || echo '未设置')"
    echo "  工作目录: $(get_config "['paths']['workplace']" 2>/dev/null || echo 'WORKPLACE')"
    echo "  日志目录: $(dirname $(get_config "['logs']['main_log']" 2>/dev/null || echo 'logs/main.log'))"
    echo ""
    success "初始化检查完成"
}

# 显示帮助
help() {
    cat << EOF
${GREEN}飞书 Bot 管理脚本${NC}

用法: $0 {command} [options]

命令:
    ${YELLOW}init [--auto]${NC}       初始化项目配置（设置 project_root）
    ${YELLOW}start${NC}              启动 Bot
    ${YELLOW}stop${NC}               停止 Bot
    ${YELLOW}restart${NC}            重启 Bot
    ${YELLOW}status${NC}             查看 Bot 状态
    ${YELLOW}check${NC}              检查 Bot 状态并自动修复异常
    ${YELLOW}log [n]${NC}            查看最近 n 条日志 (默认 20)
    ${YELLOW}follow${NC}             实时跟踪日志
    ${YELLOW}test${NC}               测试 Bot 功能
    ${YELLOW}send [chat_id] [msg]${NC} 发送测试消息到飞书
    ${YELLOW}clean${NC}              清理日志文件
    ${YELLOW}help${NC}               显示此帮助

示例:
    $0 init                     # 初始化配置（交互式）
    $0 init --auto              # 自动初始化（非交互式）
    $0 start                    # 启动 Bot
    $0 status                   # 查看状态
    $0 check                    # 检查并自动修复异常
    $0 log 50                   # 查看最近 50 条日志
    $0 send                     # 发送默认测试消息
    $0 send "chat_id" "Hello"   # 发送自定义消息

环境变量:
    LARKBOT_ROOT=/path/to/bot     # 项目根目录（优先级最高）
    ENABLE_FEISHU_NOTIFY=true/false  # 是否启用飞书通知（默认 true）

配置文件:
    config.json                     # 统一配置文件，包含所有 API 密钥和日志路径

日志文件:
    主日志: $LOG_FILE
    调试日志: $DEBUG_LOG
    飞书API日志: $FEISHU_API_LOG
    运维日志: $OPS_LOG

EOF
}

# 主函数
main() {
    case "$1" in
        init)
            init "$1" "$2"
            ;;
        start)
            start
            ;;
        stop)
            stop
            ;;
        restart)
            restart
            ;;
        status)
            status
            ;;
        log)
            log "$2"
            ;;
        follow)
            follow
            ;;
        test)
            test_bot_func
            ;;
        send)
            test_send "$2" "$3"
            ;;
        check)
            check
            ;;
        test-streaming)
            test_streaming "$2" "$3"
            ;;
        clean)
            clean
            ;;
        help|--help|-h)
            help
            ;;
        *)
            error "未知命令: $1"
            help
            exit 1
            ;;
    esac
}

# 运行主函数
main "$@"
