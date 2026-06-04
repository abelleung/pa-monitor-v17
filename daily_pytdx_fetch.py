#!/usr/bin/env python3
"""
daily_pytdx_fetch.py — 每天收盘后从 pytdx 拉取中国平安1分钟K线，保存到本地 history_data/
部署在 /opt/pa-monitor/，每天15:15 crontab 自动运行
用法：
  python3 daily_pytdx_fetch.py              # 拉取今天
  python3 daily_pytdx_fetch.py 2026-06-03  # 拉取指定日期
"""
import sys
import os
from datetime import date, datetime

# ===== 配置 =====
STOCK_CODE   = '601318'
DATA_DIR    = '/opt/pa-monitor/history_data'   # 存储目录
LOG_FILE    = '/opt/pa-monitor/monitor_logs/daily_fetch.log'

def log(msg):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = '[%s] %s' % (ts, msg)
    print(line)
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except:
        pass

def fetch_pytdx(date_str):
    """用 pytdx 拉取指定日期的1分钟K线，保存为 CSV 返回路径"""
    try:
        from pytdx.hq import TdxHq_API
        from pytdx.params import TDXParams
    except Exception as e:
        log('ERROR: pytdx 导入失败: %s' % e)
        return None

    log('正在连接 pytdx 行情服务器...')
    api = TdxHq_API()
    if not api.connect('119.147.212.81', 7709):
        if not api.connect('116.228.27.149', 7709):
            log('ERROR: pytdx 连接失败')
            return None
    log('pytdx 已连接')

    # 拉取当天1分钟K线（最多800根）
    bars = api.get_security_bars(
        TDXParams.KLINE_TYPE_1MIN,
        1,                # 市场：1=上海
        STOCK_CODE,
        0,                # 起始位置
        800               # 获取条数
    )
    api.disconnect()

    if not bars or len(bars) == 0:
        log('ERROR: 未获取到数据')
        return None

    # 过滤指定日期 + 转换格式
    import pandas as pd
    data = []
    y, m, d = map(int, date_str.split('-'))
    for bar in bars:
        t = bar['datetime']  # 格式: 202606030931
        bar_date = '%04d-%02d-%02d' % (t // 100000000, (t // 1000000) % 100, (t // 10000) % 100)
        if bar_date != date_str:
            continue
        hh = (t // 100) % 10000
        mm = t % 100
        time_str = '%04d-%02d-%02d %02d:%02d:00' % (y, m, d, hh, mm)
        data.append({
            '时间':   time_str,
            '开盘':   bar['open'],
            '最高':   bar['high'],
            '最低':   bar['low'],
            '收盘':   bar['close'],
            '成交量': bar['vol'],
            '成交额': bar['amount'],
        })

    if not data:
        log('ERROR: 指定日期 %s 无数据（非交易日？）' % date_str)
        return None

    # 保存 CSV
    os.makedirs(DATA_DIR, exist_ok=True)
    filepath = os.path.join(DATA_DIR, '%s.csv' % date_str)
    df = pd.DataFrame(data)
    df.to_csv(filepath, index=False, encoding='utf-8-sig')
    log('保存成功: %s (%d根K线)' % (filepath, len(df)))
    return filepath

def main():
    # 确定日期
    if len(sys.argv) >= 2:
        date_str = sys.argv[1]
    else:
        today = date.today()
        if today.weekday() >= 5:
            log('WARNING: 今天是周末(%s)，可能无数据' % ['周一','周二','周三','周四','周五','周六','周日'][today.weekday()])
        date_str = today.strftime('%Y-%m-%d')

    # 验证日期格式
    try:
        y, m, d = map(int, date_str.split('-'))
        date(y, m, d)
    except:
        log('ERROR: 日期格式错误，请用 YYYY-MM-DD，如 2026-06-03')
        sys.exit(1)

    log('='*60)
    log('  daily_pytdx_fetch: 拉取 %s 中国平安1分钟K线' % date_str)
    log('='*60)

    filepath = fetch_pytdx(date_str)
    if not filepath:
        sys.exit(1)

    # 验证文件
    log('验证文件: %s' % filepath)
    if os.path.exists(filepath):
        import pandas as pd
        df = pd.read_csv(filepath)
        log('✅ 完成! 文件: %s (%d根K线)' % (filepath, len(df)))
    else:
        log('ERROR: 文件验证失败')

if __name__ == '__main__':
    main()
