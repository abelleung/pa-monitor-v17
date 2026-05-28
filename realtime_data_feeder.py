#!/usr/bin/env python3
"""
realtime_data_feeder.py - 独立实时数据拉取服务
从腾讯分时接口每15秒拉取中国平安K线数据，写入realtime_bars.json供API读取
与pa_monitor解耦，可独立重启
"""
import json
import os
import urllib.request
import time
from datetime import datetime

DATA_DIR = "/opt/pa-monitor/monitor_data"
REALTIME_FILE = os.path.join(DATA_DIR, "realtime_bars.json")
LOG_FILE = "/opt/pa-monitor/monitor_logs/realtime_feeder.log"


def log(msg):
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = "[{}] {}".format(ts, msg)
    print(line)
    try:
        with open(LOG_FILE, "a") as f:
            f.write(line + "\n")
    except Exception:
        pass


def fetch_tencent_minute():
    """从腾讯分时接口获取当日1分钟数据"""
    url = "http://web.ifzq.gtimg.cn/appstock/app/minute/query?_var=min_data&code=sh601318"
    try:
        req = urllib.request.Request(url, headers={"User-Agent": "Mozilla/5.0"})
        resp = urllib.request.urlopen(req, timeout=10)
        text = resp.read().decode("gbk")
        json_str = text.split("=", 1)[1].strip()
        d = json.loads(json_str)

        bars_raw = None
        for k, v in d["data"].items():
            if isinstance(v, dict) and "data" in v:
                inner = v["data"]
                if isinstance(inner, dict) and "data" in inner:
                    bars_raw = inner["data"]
                elif isinstance(inner, list):
                    bars_raw = inner
                break
        return bars_raw
    except Exception as e:
        log("腾讯API请求失败: {}".format(e))
        return None


def parse_to_bars(raw_lines):
    """将腾讯原始数据转为标准格式"""
    bars = []
    prev_price = None
    prev_cum_amt = 0
    prev_cum_vol = 0
    today_str = datetime.now().strftime("%Y-%m-%d")

    for line in raw_lines:
        parts = line.split()
        if len(parts) < 4:
            continue
        t_raw = parts[0]
        hh, mm = t_raw[:2], t_raw[2:]
        price = float(parts[1])
        vol = int(parts[2])
        cum_amt = float(parts[3])

        single_amt = cum_amt - prev_cum_amt
        single_vol = vol - prev_cum_vol
        o = prev_price if prev_price is not None else price
        h = max(o, price)
        l = min(o, price) if prev_price is not None else price

        bars.append({
            "时间": "{} {}:{}".format(today_str, hh, mm),
            "开盘": round(o, 2),
            "收盘": round(price, 2),
            "最高": round(h, 2),
            "最低": round(l, 2),
            "成交量": max(0, single_vol),
            "成交额": max(0, single_amt),
            "成交额_万": round(max(0, single_amt) / 10000, 0),
            "涨跌": 0,
            "风险": 0,
        })

        prev_price = price
        prev_cum_amt = cum_amt
        prev_cum_vol = vol

    return bars


def is_trade_time():
    """判断是否在交易时间"""
    now = datetime.now()
    if now.weekday() >= 5:
        return False
    t = now.hour * 60 + now.minute
    return (555 <= t <= 690) or (780 <= t <= 900)  # 9:25-11:30, 13:00-15:00


def main():
    log("实时数据服务启动")
    while True:
        if not is_trade_time():
            time.sleep(30)
            continue

        try:
            raw = fetch_tencent_minute()
            if raw:
                bars = parse_to_bars(raw)
                if bars:
                    data = {
                        "date": datetime.now().strftime("%Y-%m-%d"),
                        "bars": bars,
                        "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    }
                    with open(REALTIME_FILE, "w", encoding="utf-8") as f:
                        json.dump(data, f, ensure_ascii=False)
                    log("更新 {} 根K线".format(len(bars)))
            else:
                log("无数据")
        except Exception as e:
            log("处理异常: {}".format(e))

        time.sleep(15)


if __name__ == "__main__":
    main()
