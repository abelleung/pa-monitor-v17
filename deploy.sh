#!/bin/bash
# 一键部署脚本：本地代码上传到云端并重启服务
# 用法: bash deploy.sh

set -e

SERVER="pa-cloud"
REMOTE_DIR="/opt/pa-monitor"

# 存在的文件列表
FILES="pa_monitor.py pa_notify.py indicators.py strategies.py manual_strategy_v2.py monitor_config.json setup_monitor.sh monitor_healthcheck.sh"

echo "=== 盯盘系统一键部署 ==="
echo "目标: $SERVER:$REMOTE_DIR"

# 1. 上传文件
echo "[1/4] 上传代码文件..."
scp $FILES $SERVER:$REMOTE_DIR/
echo "✅ 上传完成"

# 2. 更新systemd服务描述版本号
echo "[2/4] 更新systemd服务描述..."
# 从pa_monitor.py提取版本号
VERSION=$(head -1 pa_monitor.py | grep -o 'v[0-9.]*' || echo "v17.1")
ssh $SERVER "sed -i 's/中国平安盯盘系统 [^\"]*/中国平安盯盘系统 ${VERSION}/' /etc/systemd/system/pa-monitor.service && systemctl daemon-reload && echo '✅ systemd描述已更新为 ${VERSION}'"

# 3. 清除matplotlib缓存（字体变更后需要）
echo "[3/4] 清除matplotlib缓存..."
ssh $SERVER "rm -rf /root/.cache/matplotlib 2>/dev/null; echo '缓存已清除'"

# 4. 重启服务
echo "[4/4] 重启服务..."
ssh $SERVER "systemctl restart pa-monitor 2>/dev/null; echo '服务已重启'"

echo ""
echo "=== 部署完成 ==="
echo "查看日志: ssh $SERVER 'tail -f $REMOTE_DIR/monitor_logs/service_error.log'"
echo "查看状态: ssh $SERVER 'systemctl status pa-monitor --no-pager'"
