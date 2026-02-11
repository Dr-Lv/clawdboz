#!/bin/bash
#
# 飞书 Bot 管理脚本
# 功能：启动、停止、重启、状态查看、测试
#

# 配置
BOT_NAME="feishu_bot"
BOT_SCRIPT="clawdboz.py"
BOT_DIR="/Users/suntom/work/test/larkbot"
LOG_FILE="$BOT_DIR/log"
DEBUG_LOG="$BOT_DIR/bot_debug.log"
FEISHU_API_LOG="$BOT_DIR/feishu_api.log"
PID_FILE="/tmp/${BOT_NAME}.pid"

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
    # 尝试通过进程名查找
    local pid_list=$(pgrep -f "python.*$BOT_SCRIPT" 2>/dev/null)
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
    if [ ! -f "$BOT_DIR/$BOT_SCRIPT" ]; then
        error "找不到脚本: $BOT_DIR/$BOT_SCRIPT"
        return 1
    fi
    
    # 进入工作目录
    cd "$BOT_DIR" || {
        error "无法进入目录: $BOT_DIR"
        return 1
    }
    
    # 启动 Bot
    info "启动 Python 进程..."
    nohup python "$BOT_SCRIPT" > "$LOG_FILE" 2>&1 &
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
        local ws_status=$(grep "connected to wss" "$LOG_FILE" 2>/dev/null | tail -1)
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
        
        # 检查 WebSocket 连接
        if grep -q "connected to wss" "$LOG_FILE" 2>/dev/null; then
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
    
    # 检查 WebSocket 连接
    if grep -q "connected to wss" "$LOG_FILE" 2>/dev/null; then
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
    
    cd "$BOT_DIR" || return 1
    
    python -c "
import sys
sys.path.insert(0, '$BOT_DIR')
from clawdboz import LarkBot
import json

bot = LarkBot('cli_a90ded6b63f89cd6', '3WDKvIVUHPYVXbEVYjRgRg2wORBDb5z3')
result = bot.reply_text('$chat_id', '$message', streaming=False)
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
    
    cd "$BOT_DIR" || return 1
    
    python -c "
import sys
sys.path.insert(0, '$BOT_DIR')
from clawdboz import LarkBot
import json

bot = LarkBot('cli_a90ded6b63f89cd6', '3WDKvIVUHPYVXbEVYjRgRg2wORBDb5z3')
print('启动流式处理...')
bot.run_msg_script_streaming('$chat_id', '$message')
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

# 显示帮助
help() {
    cat << EOF
${GREEN}飞书 Bot 管理脚本${NC}

用法: $0 {command} [options]

命令:
    ${YELLOW}start${NC}              启动 Bot
    ${YELLOW}stop${NC}               停止 Bot
    ${YELLOW}restart${NC}            重启 Bot
    ${YELLOW}status${NC}             查看 Bot 状态
    ${YELLOW}log [n]${NC}            查看最近 n 条日志 (默认 20)
    ${YELLOW}follow${NC}             实时跟踪日志
    ${YELLOW}test${NC}               测试 Bot 功能
    ${YELLOW}send [chat_id] [msg]${NC} 发送测试消息到飞书
    ${YELLOW}clean${NC}              清理日志文件
    ${YELLOW}help${NC}               显示此帮助

示例:
    $0 start                    # 启动 Bot
    $0 status                   # 查看状态
    $0 log 50                   # 查看最近 50 条日志
    $0 send                     # 发送默认测试消息
    $0 send "chat_id" "Hello"   # 发送自定义消息

日志文件:
    主日志: $LOG_FILE
    调试日志: $DEBUG_LOG

EOF
}

# 主函数
main() {
    case "$1" in
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
