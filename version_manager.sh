#!/bin/bash
# 中国平安监控系统 — 版本回滚/备份工具
# 用法：
#   ./version_manager.sh backup vX.X    # 备份当前版本
#   ./version_manager.sh rollback vX.X  # 回滚到指定版本
#   ./version_manager.sh list           # 查看已有备份
#   ./version_manager.sh current        # 查看当前版本

VERSION_DIR="$(cd "$(dirname "$0")" && pwd)/version_backup"
WORK_DIR="$(cd "$(dirname "$0")" && pwd)"

list_backups() {
    echo "📂 已有版本备份："
    echo "────────────────────────"
    if [ -d "$VERSION_DIR" ]; then
        for d in "$VERSION_DIR"/*/; do
            ver=$(basename "$d")
            count=$(ls -1 "$d" 2>/dev/null | wc -l | tr -d ' ')
            date=$(stat -f "%Sm" -t "%Y-%m-%d %H:%M" "$d" 2>/dev/null)
            echo "  📁 $ver  ($count 个文件, 备份于 $date)"
        done
    else
        echo "  （无备份）"
    fi
    echo ""
}

show_current() {
    if [ -f "$WORK_DIR/pa_monitor.py" ]; then
        ver=$(grep -m1 "版本：" "$WORK_DIR/pa_monitor.py" | sed 's/.*版本：//')
        echo "📌 当前运行版本：$ver"
    else
        echo "❌ pa_monitor.py 不存在"
    fi
}

backup_version() {
    local ver=$1
    local dest="$VERSION_DIR/$ver"
    
    if [ -z "$ver" ]; then
        echo "❌ 请指定版本号，例如：./version_manager.sh backup v11.7"
        exit 1
    fi
    
    mkdir -p "$dest"
    
    for f in pa_monitor.py pa_notify.py monitor_config.json setup_monitor.sh monitor_healthcheck.sh; do
        if [ -f "$WORK_DIR/$f" ]; then
            cp "$WORK_DIR/$f" "$dest/"
            echo "  ✅ $f"
        fi
    done
    
    echo ""
    echo "✅ 版本 $ver 备份完成 → $dest"
}

rollback_version() {
    local ver=$1
    local src="$VERSION_DIR/$ver"
    
    if [ -z "$ver" ]; then
        echo "❌ 请指定版本号，例如：./version_manager.sh rollback v11.5"
        exit 1
    fi
    
    if [ ! -d "$src" ]; then
        echo "❌ 备份 $ver 不存在"
        echo "   运行 ./version_manager.sh list 查看可用版本"
        exit 1
    fi
    
    # 检查是否有进程在跑
    pid=$(ps aux | grep pa_monitor.py | grep -v grep | awk '{print $2}')
    if [ -n "$pid" ]; then
        echo "⚠️  检测到监控进程 PID=$pid，正在停止..."
        kill -9 $pid 2>/dev/null
        sleep 1
        echo "  ✅ 进程已停止"
    fi
    
    echo "🔄 回滚到 $ver..."
    for f in pa_monitor.py pa_notify.py monitor_config.json setup_monitor.sh monitor_healthcheck.sh; do
        if [ -f "$src/$f" ]; then
            cp "$src/$f" "$WORK_DIR/"
            echo "  ✅ $f"
        else
            echo "  ⚠️  $src/$f 不存在，跳过"
        fi
    done
    
    echo ""
    echo "✅ 回滚完成。请手动重启监控："
    echo "   cd $WORK_DIR && nohup python3 pa_monitor.py > /dev/null 2>&1 &"
}

case "$1" in
    list)   list_backups ;;
    current) show_current ;;
    backup) backup_version "$2" ;;
    rollback) rollback_version "$2" ;;
    *)      echo "用法: $0 {list|current|backup <版本>|rollback <版本>}" ;;
esac
