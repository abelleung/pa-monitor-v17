#!/usr/bin/env python3
"""
daily_sina_fetch.py — 每天收盘后从新浪财经拉取中国平安1分钟K线，上传到云端
用法：
  python3 daily_sina_fetch.py              # 拉取今天
  python3 daily_sina_fetch.py 2026-06-03  # 拉取指定日期
  crontab: 15 15 * * 1-5  cd /opt/pa-monitor && python3 daily_sina_fetch.py
"""
import sys
import os
import csv
import json
import re
import time
import hashlib
from datetime import datetime, date
import urllib.request, ssl

# ===== 配置 =====
SYMBOL       = 'sh601318'
REMOTE_HOST  = 'root@175.178.232.233'
REMOTE_DIR   = '/opt/pa-monitor/history_data'
SSH_KEY      = os.path.expanduser('~/.ssh/id_cloud_pa')
SINA_URL     = ('https://quotes.sina.cn/cn/api/jsonp.php/'
                'var%20_sh601318=/CN_MarketDataService.'
                'getKLineData?symbol=sh601318&scale=1&ma=no&datalen=500')
LOCAL_DIR    = '/tmp/pa_sina_fetch'
LOG_FILE     = '/tmp/pa_sina_fetch.log'

def log(msg):
    ts = datetime.now().strftime('%Y-%m-%d %H:%M:%S')
    line = '[%s] %s' % (ts, msg)
    print(line)
    try:
        with open(LOG_FILE, 'a', encoding='utf-8') as f:
            f.write(line + '\n')
    except:
        pass

def fetch_sina_1min():
    """从新浪财经拉取1分钟K线"""
    try:
        ctx = ssl.create_default_context()
        ctx.check_hostname = False
        ctx.verify_mode = ssl.CERT_NONE
        req = urllib.request.Request(
            SINA_URL,
            headers={'User-Agent': 'Mozilla/5.0', 'Referer': 'https://finance.sina.com.cn/'}
        )
        with urllib.request.urlopen(req, timeout=15, context=ctx) as resp:
            raw = resp.read().decode('utf-8', errors='replace')
        m = re.search(r'\[.*\]', raw, re.DOTALL)
        if not m:
            log('❌ 解析失败：无法找到JSON数组')
            return []
        data = json.loads(m.group())
        result = []
        for d in data:
            result.append({
                '时间':   d['day'],
                '开盘':   float(d['open']),
                '最高':   float(d['high']),
                '最低':   float(d['low']),
                '收盘':   float(d['close']),
                '成交量': int(d['volume']),
                '成交额': float(d['amount']),
            })
        log('✅ 新浪拉取成功：%d根K线' % len(result))
        return result
    except Exception as e:
        log('❌ 拉取失败：%s' % e)
        return []

def filter_by_date(bars, target_date=None):
    """只保留指定日期的数据"""
    if target_date is None:
        target_date = date.today().strftime('%Y-%m-%d')
    filtered = [b for b in bars if b['时间'].startswith(target_date)]
    log('过滤日期 %s：%d根' % (target_date, len(filtered)))
    return filtered

def save_to_csv(bars, filepath):
    """保存为CSV"""
    if not bars:
        return False
    os.makedirs(os.path.dirname(filepath), exist_ok=True)
    with open(filepath, 'w', encoding='utf-8-sig', newline='') as f:
        writer = csv.DictWriter(f, fieldnames=['时间','开盘','最高','最低','收盘','成交量','成交额'])
        writer.writeheader()
        writer.writerows(bars)
    log('✅ 保存到 %s (%d根)' % (filepath, len(bars)))
    return True

def scp_to_remote(local_path, remote_path):
    """上传到云端"""
    cmd = 'scp -i %s -o StrictHostKeyChecking=no "%s" "%s:%s"' % (SSH_KEY, local_path, REMOTE_HOST, remote_path)
    ret = os.system(cmd)
    return ret == 0

def ssh_remote(cmd):
    """远端执行命令"""
    full = 'ssh -i %s -o StrictHostKeyChecking=no %s "%s"' % (SSH_KEY, REMOTE_HOST, cmd.replace('"', '\\"'))
    ret = os.system(full)
    return ret == 0

def main():
    # 确定日期
    if len(sys.argv) >= 2:
        date_str = sys.argv[1]
    else:
        today = date.today()
        if today.weekday() >= 5:
            log('⚠️ 今天是周末(%s)，可能无数据' % ['周一','周二','周三','周四','周五','周六','周日'][today.weekday()])
        date_str = today.strftime('%Y-%m-%d')

    # 验证日期
    try:
        y, m, d = map(int, date_str.split('-'))
        date(y, m, d)
    except:
        log('ERROR: 日期格式错误，请用 YYYY-MM-DD')
        sys.exit(1)

    log('='*60)
    log('  daily_sina_fetch: 拉取 %s 中国平安1分钟K线' % date_str)
    log('='*60)

    # 1. 拉取数据
    all_bars = fetch_sina_1min()
    if not all_bars:
        log('ERROR: 拉取失败')
        sys.exit(1)

    # 2. 过滤日期
    bars = filter_by_date(all_bars, date_str)
    if not bars:
        log('ERROR: %s 无数据（非交易日？）' % date_str)
        sys.exit(1)

    # 3. 保存本地
    os.makedirs(LOCAL_DIR, exist_ok=True)
    local_file = os.path.join(LOCAL_DIR, '%s.csv' % date_str)
    if not save_to_csv(bars, local_file):
        sys.exit(1)

    # 4. 确保远端目录
    ssh_remote('mkdir -p %s' % REMOTE_DIR)

    # 5. 上传
    remote_file = '%s/%s.csv' % (REMOTE_DIR, date_str)
    log('上传到云端: %s' % remote_file)
    if not scp_to_remote(local_file, remote_file):
        log('ERROR: 上传失败')
        sys.exit(1)

    # 6. 验证
    log('验证远端文件...')
    ssh_remote('ls -lh %s/%s.csv && wc -l %s/%s.csv' % (REMOTE_DIR, date_str, REMOTE_DIR, date_str))

    # 7. 清理本地
    try:
        os.remove(local_file)
        os.rmdir(LOCAL_DIR)
        log('本地临时文件已清理')
    except:
        pass

    log('\n✅ 完成! 文件已保存到云端: %s/%s.csv' % (REMOTE_DIR, date_str))

if __name__ == '__main__':
    main()
