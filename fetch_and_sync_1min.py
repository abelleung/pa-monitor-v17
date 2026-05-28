#!/usr/bin/env python3
"""
中国平安1分钟K线数据每日同步脚本

功能：
  1. 从云端拉取pa_monitor收盘导出的1分钟K线CSV
  2. 补全本地缺失的历史数据（从桌面历史CSV拆分）
  3. 云端→本地单向同步（云端是数据源，本地是备份）

使用方法：
  python3 fetch_and_sync_1min.py              # 从云端拉取最新数据
  python3 fetch_and_sync_1min.py --backfill   # 补全本地缺失数据（从桌面CSV拆分）
  python3 fetch_and_sync_1min.py --sync       # 同义词：从云端拉取

定时任务：
  每交易日15:15自动运行（云端收盘导出后）
"""

import os
import sys
import subprocess
from datetime import datetime, timedelta
from pathlib import Path

# 路径配置
LOCAL_DATA_DIR = Path(__file__).parent / "monitor_data"
CLOUD_ALIAS = "pa-cloud"
CLOUD_DATA_DIR = "/opt/pa-monitor/monitor_data"
DESKTOP_CSV = Path.home() / "Desktop" / "中国平安_1分钟线_20260102_20260403.csv"


def get_trading_days(start_date: str, end_date: str) -> list:
    """获取交易日列表（排除周末，简单版）"""
    from datetime import date
    start = datetime.strptime(start_date, "%Y-%m-%d").date()
    end = datetime.strptime(end_date, "%Y-%m-%d").date()
    days = []
    current = start
    while current <= end:
        if current.weekday() < 5:  # 周一到周五
            days.append(current.strftime("%Y-%m-%d"))
        current += timedelta(days=1)
    return days


def pull_from_cloud():
    """从云端拉取K线CSV到本地"""
    print("📡 从云端拉取K线数据...")
    LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    result = subprocess.run(
        ["rsync", "-avz", "--include=2026-*.csv", "--exclude=*",
         f"{CLOUD_ALIAS}:{CLOUD_DATA_DIR}/", str(LOCAL_DATA_DIR) + "/"],
        capture_output=True, text=True
    )
    
    if result.returncode == 0:
        # 统计
        csv_files = sorted([f for f in LOCAL_DATA_DIR.glob("2026-*.csv") if f.stat().st_size > 1000])
        print(f"✅ 同步完成，本地共有 {len(csv_files)} 个交易日文件")
        if csv_files:
            print(f"   日期范围: {csv_files[0].stem} ~ {csv_files[-1].stem}")
        return True
    else:
        print(f"❌ 同步失败: {result.stderr}")
        return False


def backfill_from_desktop_csv():
    """从桌面历史CSV拆分补全1-3月数据"""
    if not DESKTOP_CSV.exists():
        print(f"❌ 桌面历史CSV不存在: {DESKTOP_CSV}")
        return False
    
    import pandas as pd
    
    print(f"📂 从桌面CSV补全: {DESKTOP_CSV.name}")
    df = pd.read_csv(DESKTOP_CSV)
    df['日期'] = df['时间'].str[:10]
    
    count = 0
    for date, group in df.groupby('日期'):
        out_path = LOCAL_DATA_DIR / f'{date}.csv'
        if out_path.exists() and out_path.stat().st_size > 1000:
            continue  # 已存在
        group = group.drop(columns=['日期'])
        group.to_csv(out_path, index=False, encoding='utf-8-sig')
        count += 1
    
    print(f"✅ 补全完成: 新增 {count} 个交易日文件")
    return True


def main():
    LOCAL_DATA_DIR.mkdir(parents=True, exist_ok=True)
    
    if "--backfill" in sys.argv:
        backfill_from_desktop_csv()
        # 补全后再从云端拉取最新数据
        pull_from_cloud()
    elif "--sync" in sys.argv or "--all" in sys.argv or len(sys.argv) == 1:
        # 默认：从云端拉取
        pull_from_cloud()


if __name__ == "__main__":
    main()
