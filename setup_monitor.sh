#!/bin/bash
# 中国平安 v15.3 三策略倒T+正T监控 — 安装/管理脚本
# 使用方法:
#   ./setup_monitor.sh install   — 安装 launchd 定时任务 + cron 自检
#   ./setup_monitor.sh uninstall — 卸载定时任务 + cron 自检
#   ./setup_monitor.sh start     — 立即手动启动监控
#   ./setup_monitor.sh stop      — 停止监控进程
#   ./setup_monitor.sh status    — 查看状态
#   ./setup_monitor.sh test      — 测试推送
#   ./setup_monitor.sh logs      — 查看今日日志

PLIST="com.pa.monitor"
PLIST_PATH="$HOME/Library/LaunchAgents/${PLIST}.plist"
PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
MONITOR_PID_FILE="$PROJECT_DIR/monitor_logs/monitor.pid"
PYTHON="$(which python3 2>/dev/null || which python 2>/dev/null || echo /Library/Frameworks/Python.framework/Versions/3.13/Resources/Python.app/Contents/MacOS/Python)"
HEALTHCHECK_SCRIPT="$PROJECT_DIR/monitor_healthcheck.sh"
CRON_TAG="monitor_healthcheck"

# 颜色
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
NC='\033[0m'

ensure_log_dir() {
    mkdir -p "$PROJECT_DIR/monitor_logs"
    mkdir -p "$PROJECT_DIR/monitor_data"
}

case "$1" in
    install)
        ensure_log_dir
        # 清除代理
        for k in http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy; do
            unset $k 2>/dev/null
        done
        export NO_PROXY='*'
        export no_proxy='*'

        # 测试推送
        echo -e "${YELLOW}先测试推送是否正常...${NC}"
        $PYTHON "$PROJECT_DIR/pa_notify.py"

        echo ""
        echo -e "${YELLOW}加载 launchd 定时任务...${NC}"
        launchctl unload "$PLIST_PATH" 2>/dev/null
        launchctl load "$PLIST_PATH" 2>/dev/null
        if [ $? -eq 0 ]; then
            echo -e "${GREEN}✅ launchd 定时任务已安装${NC}"
        else
            echo -e "${RED}❌ launchd 安装失败，请检查 plist 文件${NC}"
        fi

        # 安装 cron 自检
        echo -e "${YELLOW}安装 cron 自检任务...${NC}"
        if crontab -l 2>/dev/null | grep -q "$CRON_TAG"; then
            echo -e "${GREEN}✅ cron 自检已存在${NC}"
        else
            (crontab -l 2>/dev/null; 
             echo "# PA监控自检 - v15.3 增加09:25/09:35检查点";
             echo "50 8 * * 1-5 $HEALTHCHECK_SCRIPT >> $PROJECT_DIR/monitor_logs/healthcheck.log 2>&1  # $CRON_TAG"; 
             echo "25 9 * * 1-5 $HEALTHCHECK_SCRIPT >> $PROJECT_DIR/monitor_logs/healthcheck.log 2>&1  # $CRON_TAG"; 
             echo "35 9 * * 1-5 $HEALTHCHECK_SCRIPT >> $PROJECT_DIR/monitor_logs/healthcheck.log 2>&1  # $CRON_TAG"; 
             echo "50 12 * * 1-5 $HEALTHCHECK_SCRIPT >> $PROJECT_DIR/monitor_logs/healthcheck.log 2>&1  # $CRON_TAG"
            ) | crontab -
            echo -e "${GREEN}✅ cron 自检已安装（08:50 / 09:25 / 09:35 / 12:50）${NC}"
        fi

        echo ""
        echo -e "${GREEN}安装完成！${NC}"
        echo "  launchd: 周一到周五 09:20 自动启动（失败自动重试）"
        echo "  cron自检: 每天 08:50 / 09:25 / 09:35 / 12:50 检查并重启卡死进程"
        echo "  日志目录: $PROJECT_DIR/monitor_logs/"
        echo "  数据目录: $PROJECT_DIR/monitor_data/"
        echo ""
        echo "  常用命令:"
        echo "    ./setup_monitor.sh status    — 查看状态"
        echo "    ./setup_monitor.sh test      — 测试推送"
        echo "    ./setup_monitor.sh logs      — 查看日志"
        echo "    ./setup_monitor.sh start     — 立即手动启动"
        echo "    ./setup_monitor.sh stop      — 停止"
        echo "    ./setup_monitor.sh uninstall — 卸载"
        ;;

    uninstall)
        echo -e "${YELLOW}卸载 launchd 定时任务...${NC}"
        launchctl unload "$PLIST_PATH" 2>/dev/null
        echo -e "${GREEN}✅ launchd 已卸载${NC}"

        echo -e "${YELLOW}卸载 cron 自检...${NC}"
        crontab -l 2>/dev/null | grep -v "$CRON_TAG" | crontab -
        echo -e "${GREEN}✅ cron 自检已卸载${NC}"
        ;;

    start)
        ensure_log_dir
        # 检查是否已在运行
        if [ -f "$MONITOR_PID_FILE" ]; then
            OLD_PID=$(cat "$MONITOR_PID_FILE")
            if kill -0 "$OLD_PID" 2>/dev/null; then
                echo -e "${RED}❌ 监控已在运行中 (PID: $OLD_PID)${NC}"
                echo "请先执行 ./setup_monitor.sh stop"
                exit 1
            fi
        fi
        echo -e "${YELLOW}启动监控（后台运行）...${NC}"
        cd "$PROJECT_DIR"
        for k in http_proxy https_proxy HTTP_PROXY HTTPS_PROXY ALL_PROXY all_proxy; do
            unset $k 2>/dev/null
        done
        export NO_PROXY='*'
        export no_proxy='*'
        nohup $PYTHON "$PROJECT_DIR/pa_monitor.py" >> "$PROJECT_DIR/monitor_logs/launchd_stdout.log" 2>&1 &
        NEW_PID=$!
        echo $NEW_PID > "$MONITOR_PID_FILE"
        echo -e "${GREEN}✅ 已启动 PID: $NEW_PID${NC}"
        echo "  查看日志: ./setup_monitor.sh logs"
        echo "  查看状态: ./setup_monitor.sh status"
        ;;

    stop)
        echo -e "${YELLOW}停止监控进程...${NC}"
        if [ -f "$MONITOR_PID_FILE" ]; then
            PID=$(cat "$MONITOR_PID_FILE")
            kill "$PID" 2>/dev/null
            sleep 1
            # 如果还活着就强杀
            if kill -0 "$PID" 2>/dev/null; then
                kill -9 "$PID" 2>/dev/null
            fi
            rm -f "$MONITOR_PID_FILE"
            echo -e "${GREEN}✅ 已停止 (PID: $PID)${NC}"
        else
            pkill -f "python.*pa_monitor.py" 2>/dev/null
            echo -e "${GREEN}✅ 已停止${NC}"
        fi
        ;;

    status)
        echo "═══ 监控状态 ═══"
        # 检查 launchd
        loaded=$(launchctl list 2>/dev/null | grep "$PLIST")
        if [ -n "$loaded" ]; then
            echo -e "  launchd:  ${GREEN}已加载 ✅${NC}"
        else
            echo -e "  launchd:  ${RED}未加载 ❌${NC}"
        fi

        # 检查 cron
        if crontab -l 2>/dev/null | grep -q "$CRON_TAG"; then
            echo -e "  cron自检: ${GREEN}已安装 ✅${NC} (08:50 / 12:50)"
        else
            echo -e "  cron自检: ${RED}未安装 ❌${NC}"
        fi

        # 检查进程
        if [ -f "$MONITOR_PID_FILE" ]; then
            PID=$(cat "$MONITOR_PID_FILE")
            if kill -0 "$PID" 2>/dev/null; then
                echo -e "  进程状态:  ${GREEN}运行中 (PID: $PID) ✅${NC}"
            else
                echo -e "  进程状态:  ${RED}PID文件存在但进程已死 (PID: $PID) ❌${NC}"
            fi
        else
            echo -e "  进程状态:  ${YELLOW}未运行${NC}"
        fi

        # 检查最后心跳
        echo ""
        today=$(date +%Y-%m-%d)
        log_file="$PROJECT_DIR/monitor_logs/monitor_${today}.log"
        if [ -f "$log_file" ]; then
            LAST_HB=$(grep "💓" "$log_file" | tail -1)
            if [ -n "$LAST_HB" ]; then
                echo "  最后心跳:"
                echo "    $LAST_HB"
            else
                echo "  最后心跳: 无"
            fi
        else
            echo "  今日暂无日志"
        fi

        # 检查配置
        echo ""
        config="$PROJECT_DIR/monitor_config.json"
        bark_count=$($PYTHON -c "import json; d=json.load(open('$config')); print(len(d.get('bark_urls',[])) + (1 if d.get('bark_url') else 0))" 2>/dev/null || echo 0)
        wechat=$($PYTHON -c "import json; d=json.load(open('$config')); print('✅' if d.get('wechat_webhook') else '❌')" 2>/dev/null)
        echo "  Bark设备: ${bark_count}个"
        echo "  企业微信:  $wechat"
        ;;

    test)
        echo -e "${YELLOW}发送测试推送...${NC}"
        cd "$PROJECT_DIR"
        $PYTHON pa_notify.py
        ;;

    logs)
        ensure_log_dir
        today=$(date +%Y-%m-%d)
        log_file="$PROJECT_DIR/monitor_logs/monitor_${today}.log"
        if [ -f "$log_file" ]; then
            echo "═══ 今日日志 (${today}) ═══"
            tail -50 "$log_file"
        else
            echo -e "${YELLOW}今日暂无日志文件${NC}"
        fi
        ;;

    healthcheck)
        echo -e "${YELLOW}手动执行自检...${NC}"
        bash "$HEALTHCHECK_SCRIPT"
        ;;

    *)
        echo "中国平安 v15.3 三策略倒T+正T监控 — 管理脚本"
        echo ""
        echo "用法: $0 {install|uninstall|start|stop|status|test|logs|healthcheck}"
        echo ""
        echo "  install     — 安装 launchd + cron 自检"
        echo "  uninstall   — 卸载所有定时任务"
        echo "  start       — 手动后台启动监控"
        echo "  stop        — 停止监控进程"
        echo "  status      — 查看运行状态和配置"
        echo "  test        — 测试推送"
        echo "  logs        — 查看今日日志"
        echo "  healthcheck — 手动执行一次自检"
        ;;
esac
