# 纯实盘启动（禁用模拟模式）
import sys
sys.path.insert(0, '.')

from pa_monitor import PAMonitor

# 直接实盘运行（不传 --simulate）
monitor = PAMonitor()
monitor.run()
