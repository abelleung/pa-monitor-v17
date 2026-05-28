#!/bin/bash
# 中国平安 v15.3 监控 — 定时自检脚本
# 由 crontab 调用，在关键时间点检查监控进程是否正常
# 如果进程卡死（心跳超时15分钟）或不存在，杀掉重启
#
# v15.3 改进：
#   - 增加 09:25 和 09:35 检查点（覆盖launchd启动失败场景）
#   - 启动前等待网络就绪（防止睡眠恢复后网络未连接）
#
# cron 配置（周一到周五）：
#   25 9 * * 1-5   ← 新增：09:25 检查（覆盖09:20启动失败）
#   35 9 * * 1-5   ← 新增：09:35 检查（二次确认）
#   50 8 * * 1-5   ← 预检（确保08:50一切就绪）
#   50 12 * * 1-5  ← 午间检查

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
PID_FILE="$PROJECT_DIR/monitor_logs/monitor.pid"
LOG_DIR="$PROJECT_DIR/monitor_logs"
PYTHON="$(which python3 2>/dev/null || which python 2>/dev/null || echo /Library/Frameworks/Python.framework/Versions/3.13/Resources/Python.app/Contents/MacOS/Python)"
MONITOR_SCRIPT="$PROJECT_DIR/pa_monitor.py"
HEARTBEAT_TIMEOUT=900  # 15分钟无心跳视为卡死

# 清除代理
for k in http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy; do
    unset $k 2>/dev/null
done
export NO_PROXY='*'
export no_proxy='*'

log() {
    echo "[$(date '+%Y-%m-%d %H:%M:%S')] $1"
}

# 检查是否是交易日（简单排除周末，更精确的判断交给监控程序自身）
is_weekday() {
    local dow=$(date '+%u')  # 1=周一 ... 7=周日
    [ "$dow" -le 5 ]
}

# v14.1: 等待网络就绪（最多60秒）
wait_for_network() {
    local max_wait=60
    local waited=0
    while [ $waited -lt $max_wait ]; do
        # 尝试连接通达信服务器
        if nc -z -w 3 180.153.18.170 7709 2>/dev/null; then
            log "网络就绪（等待了${waited}秒）"
            return 0
        fi
        sleep 5
        waited=$((waited + 5))
    done
    log "网络等待超时(${max_wait}秒)，仍然尝试启动"
    return 1
}

# 启动监控进程
start_monitor() {
    wait_for_network
    cd "$PROJECT_DIR"
    nohup $PYTHON "$MONITOR_SCRIPT" >> "$LOG_DIR/launchd_stdout.log" 2>&1 &
    local new_pid=$!
    echo $new_pid > "$PID_FILE"
    log "已启动新进程 PID: $new_pid"
    
    # v15.3: 启动后10秒验证进程还活着
    sleep 10
    if kill -0 "$new_pid" 2>/dev/null; then
        log "进程 $new_pid 运行正常 ✅"
    else
        log "⚠️ 进程 $new_pid 启动后10秒已退出，可能启动失败"
    fi
}

if ! is_weekday; then
    log "周末，跳过自检"
    exit 0
fi

# 1. 检查PID文件和进程
log "开始自检..."

if [ ! -f "$PID_FILE" ]; then
    log "PID文件不存在，启动监控"
    start_monitor
    exit 0
fi

OLD_PID=$(cat "$PID_FILE")
if ! kill -0 "$OLD_PID" 2>/dev/null; then
    log "进程 $OLD_PID 不存在，清理PID文件并重启"
    rm -f "$PID_FILE"
    start_monitor
    exit 0
fi

# 2. 进程存在，检查心跳是否超时
log "进程 $OLD_PID 存在，检查心跳..."

TODAY=$(date '+%Y-%m-%d')
LOG_FILE="$LOG_DIR/monitor_${TODAY}.log"

if [ ! -f "$LOG_FILE" ]; then
    log "今日日志文件不存在（可能太早），跳过心跳检查"
    exit 0
fi

# 获取最后一条心跳的时间戳
LAST_HEARTBEAT=$(grep "💓" "$LOG_FILE" | tail -1 | grep -o '[0-9]\{2\}:[0-9]\{2\}:[0-9]\{2\}')

if [ -z "$LAST_HEARTBEAT" ]; then
    log "未找到心跳记录"
    # 可能还没开盘或太早，不做处理
    exit 0
fi

log "最后心跳时间: $LAST_HEARTBEAT"

# 计算心跳距今秒数
HB_EPOCH=$(date -j -f "%H:%M:%S" "$LAST_HEARTBEAT" '+%s' 2>/dev/null)
NOW_EPOCH=$(date '+%s')

if [ -z "$HB_EPOCH" ]; then
    log "心跳时间解析失败，跳过"
    exit 0
fi

DIFF=$((NOW_EPOCH - HB_EPOCH))

if [ "$DIFF" -gt "$HEARTBEAT_TIMEOUT" ]; then
    log "心跳超时 ${DIFF}秒（阈值${HEARTBEAT_TIMEOUT}秒），判定进程卡死"
    log "杀掉旧进程 $OLD_PID ..."
    kill -9 "$OLD_PID" 2>/dev/null
    sleep 2
    rm -f "$PID_FILE"
    start_monitor
else
    log "心跳正常（${DIFF}秒前），无需处理"
fi

exit 0
