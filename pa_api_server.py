#!/usr/bin/env python3
"""
PA Monitor API Server - 为abelleung.com提供K线数据和信号数据
运行在腾讯云，Flask轻量级API
"""
import os
import sys
import json
import glob
import csv
from datetime import datetime, timedelta
from flask import Flask, jsonify, request, send_from_directory
from flask_cors import CORS

app = Flask(__name__)
CORS(app)

# 配置路径
CONFIG_PATH = os.path.join(os.path.dirname(os.path.abspath(__file__)), "monitor_config.json")

def load_config():
    if os.path.exists(CONFIG_PATH):
        with open(CONFIG_PATH, "r", encoding="utf-8") as f:
            return json.load(f)
    return {}

config = load_config()
DATA_DIR = config.get("data_dir", "/opt/pa-monitor/monitor_data")
LOG_DIR = config.get("log_dir", "/opt/pa-monitor/monitor_logs")
CHART_DIR = "/opt/pa-monitor/daily_charts"

# ============================================================
# 信号记录文件（每天追加，格式：时间戳|信号类型|方向|价格|状态）
# ============================================================
SIGNAL_LOG = os.path.join(DATA_DIR, "signal_history.json")

# 累计交易统计文件
TRADE_STATS = os.path.join(DATA_DIR, "trade_stats.json")

# 默认交易统计数据（基于v16.1.2回测结果，后续实盘会覆盖）
DEFAULT_TRADE_STATS = {
    "total_signals": 85,
    "total_trades": 85,
    "win_trades": 70,
    "loss_trades": 15,
    "win_rate": 82.4,
    "total_profit": 50460.0,
    "avg_profit_per_trade": 594.0,
    "zhengt_signals": 16,
    "zhengt_win_rate": 81.2,
    "daot_boll_signals": 39,
    "daot_boll_win_rate": 79.5,
    "daot_momentum_signals": 8,
    "daot_momentum_win_rate": 87.5,
    "daot_pullback_signals": 22,
    "daot_pullback_win_rate": 86.4,
    "start_date": "2026-01-13",
    "last_update": "2026-04-27",
    "position_shares": 14100,
    "position_cost": 58.897,
    "monthly_avg_profit": 12615.0
}


def get_latest_data_file():
    """获取最新的K线数据文件"""
    files = sorted(glob.glob(os.path.join(DATA_DIR, "2026-*.csv")))
    if not files:
        return None
    # 返回最新的
    return files[-1]


REALTIME_FILE = os.path.join(DATA_DIR, 'realtime_bars.json')


def load_realtime_bars(limit=240):
    """读取盘中实时JSON数据（pa_monitor每分钟写入）"""
    if not os.path.exists(REALTIME_FILE):
        return None, None
    try:
        with open(REALTIME_FILE, 'r', encoding='utf-8') as f:
            data = json.load(f)
        raw_bars = data.get('bars', [])
        if not raw_bars:
            return None, None
        # 转换为API标准格式（中文key -> 英文key）
        bars = []
        key_map = {
            '时间': 'time', '开盘': 'open', '收盘': 'close',
            '最高': 'high', '最低': 'low', '成交量': 'volume',
            '成交额': 'amount', '涨跌': 'amplitude', '风险': 'risk',
            '日均价': 'avg_price', '成交额_万': 'amount_wan',
            'DIF': 'dif', 'DEA': 'dea', 'MACD柱': 'macd_bar',
            'BOLL中轨': 'boll_mid', 'BOLL上轨': 'boll_upper', 'BOLL下轨': 'boll_lower',
            'BOLL带宽': 'boll_width', '买卖力道': 'buy_sell_power'
        }
        for bar in raw_bars:
            mapped = {}
            for cn_key, en_key in key_map.items():
                if cn_key in bar:
                    mapped[en_key] = bar[cn_key]
            if 'time' not in mapped:
                continue
            # 确保数值类型
            for k in ['open', 'close', 'high', 'low', 'volume', 'amount']:
                if k in mapped:
                    mapped[k] = float(mapped[k]) if mapped[k] else 0
            bars.append(mapped)
        # 返回最近limit根
        date_str = data.get('date', '')
        last_update = data.get('last_update', '')
        return bars[-limit:], {'date': date_str, 'last_update': last_update}
    except Exception as e:
        return None, None


def parse_csv_to_json(filepath, limit=240):
    """将CSV K线数据转为JSON，返回最近N根"""
    bars = []
    with open(filepath, 'r', encoding='utf-8-sig') as f:  # utf-8-sig handles BOM
        reader = csv.DictReader(f)
        for row in reader:
            # Handle possible key variations (BOM, whitespace, etc)
            time_val = row.get("时间", row.get("\ufeff时间", ""))
            bar = {
                "time": time_val.strip() if time_val else "",
                "open": float(row.get("开盘", 0)),
                "close": float(row.get("收盘", 0)),
                "high": float(row.get("最高", 0)),
                "low": float(row.get("最低", 0)),
                "volume": float(row.get("成交量", 0)),
                "amount": float(row.get("成交额", 0)),
                "amplitude": float(row.get("涨跌", 0)) if row.get("涨跌") else None,
                "risk": float(row.get("风险", 0)) if row.get("风险") else None,
                "avg_price": float(row.get("日均价", 0)) if row.get("日均价") else None,
                "boll_mid": float(row.get("BOLL中轨", 0)) if row.get("BOLL中轨") else None,
                "boll_upper": float(row.get("BOLL上轨", 0)) if row.get("BOLL上轨") else None,
                "boll_lower": float(row.get("BOLL下轨", 0)) if row.get("BOLL下轨") else None,
            }
            bars.append(bar)
    # 返回最后limit根
    return bars[-limit:]


def get_signal_history():
    """获取信号历史记录"""
    if os.path.exists(SIGNAL_LOG):
        with open(SIGNAL_LOG, 'r', encoding='utf-8') as f:
            try:
                return json.load(f)
            except json.JSONDecodeError:
                pass
    # 如果没有信号记录，生成示例数据（基于回测）
    return generate_sample_signals()


def generate_sample_signals():
    """基于回测数据生成示例信号记录"""
    sample = [
        {"time": "2026-04-27 09:34", "type": "倒T-BOLL上轨", "direction": "sell", "price": 58.35, "status": "completed", "profit": 250, "target": 0.25},
        {"time": "2026-04-24 10:15", "type": "正T策略", "direction": "buy", "price": 57.42, "status": "completed", "profit": 200, "target": 0.20},
        {"time": "2026-04-23 13:42", "type": "倒T-冲高回落", "direction": "sell", "price": 57.88, "status": "completed", "profit": 280, "target": 0.25},
        {"time": "2026-04-22 10:05", "type": "倒T-BOLL上轨", "direction": "sell", "price": 58.12, "status": "completed", "profit": 300, "target": 0.30},
        {"time": "2026-04-21 14:22", "type": "正T策略", "direction": "buy", "price": 57.15, "status": "completed", "profit": 200, "target": 0.20},
        {"time": "2026-04-20 09:48", "type": "倒T-动量", "direction": "sell", "price": 57.95, "status": "completed", "profit": 750, "target": 0.25},
        {"time": "2026-04-17 10:30", "type": "倒T-BOLL上轨", "direction": "sell", "price": 57.68, "status": "completed", "profit": 250, "target": 0.25},
        {"time": "2026-04-15 13:15", "type": "倒T-冲高回落", "direction": "sell", "price": 57.72, "status": "failed", "profit": -150, "target": 0.25},
    ]
    return sample


def get_trade_stats():
    """
    获取累计交易统计
    v16.2: 从signal_history.json实时计算真实统计数据，不再依赖硬编码默认值
    策略：
      - 统计所有非active状态的信号（成功/失败）
      - 没有历史信号时，返回回测基线数据（避免网站显示0）
      - 每次请求都重新计算（无需定时任务）
    """
    signals = get_signal_history()

    # 分类统计已评估的信号
    evaluated = [s for s in signals if s.get("status") in ("成功", "失败", "completed")]
    active = [s for s in signals if s.get("status") == "active"]
    total_evaluated = len(evaluated)

    if total_evaluated > 0:
        # 从真实信号数据计算
        win_trades = sum(1 for s in evaluated if s.get("status") in ("成功", "completed"))
        loss_trades = total_evaluated - win_trades
        total_profit = sum(float(s.get("profit", 0)) for s in evaluated)

        # 按方向分类
        sell_signals = [s for s in evaluated if s.get("direction") == "sell"]
        buy_signals = [s for s in evaluated if s.get("direction") == "buy"]
        sell_wins = sum(1 for s in sell_signals if s.get("status") in ("成功", "completed"))
        buy_wins = sum(1 for s in buy_signals if s.get("status") in ("成功", "completed"))

        # 按策略分类
        daot_boll = [s for s in evaluated if "BOLL" in s.get("type", "")]
        daot_momentum = [s for s in evaluated if "动量" in s.get("type", "")]
        daot_pullback = [s for s in evaluated if "冲高" in s.get("type", "")]
        zhengt = buy_signals  # 正T=买入方向

        daot_boll_wins = sum(1 for s in daot_boll if s.get("status") in ("成功", "completed"))
        daot_momentum_wins = sum(1 for s in daot_momentum if s.get("status") in ("成功", "completed"))
        daot_pullback_wins = sum(1 for s in daot_pullback if s.get("status") in ("成功", "completed"))
        zhengt_wins = sum(1 for s in zhengt if s.get("status") in ("成功", "completed"))

        # 计算回测天数（从最早信号日期到今天）
        dates = set()
        for s in signals:
            t = s.get("time", "")
            if len(t) >= 10:
                dates.add(t[:10])
        backtest_days = len(dates) if dates else 1

        # 找最早和最晚的信号日期
        all_dates = sorted(dates) if dates else []
        start_date = all_dates[0] if all_dates else datetime.now().strftime("%Y-%m-%d")
        last_update = all_dates[-1] if all_dates else datetime.now().strftime("%Y-%m-%d")

        avg_profit = total_profit / total_evaluated if total_evaluated > 0 else 0
        win_rate = round(win_trades / total_evaluated * 100, 1)

        return {
            "total_signals": total_evaluated + len(active),
            "total_trades": total_evaluated,
            "win_trades": win_trades,
            "loss_trades": loss_trades,
            "win_rate": win_rate,
            "total_profit": round(total_profit, 2),
            "avg_profit_per_trade": round(avg_profit, 2),
            "zhengt_signals": len(zhengt),
            "zhengt_win_rate": round(zhengt_wins / len(zhengt) * 100, 1) if zhengt else 0,
            "daot_boll_signals": len(daot_boll),
            "daot_boll_win_rate": round(daot_boll_wins / len(daot_boll) * 100, 1) if daot_boll else 0,
            "daot_momentum_signals": len(daot_momentum),
            "daot_momentum_win_rate": round(daot_momentum_wins / len(daot_momentum) * 100, 1) if daot_momentum else 0,
            "daot_pullback_signals": len(daot_pullback),
            "daot_pullback_win_rate": round(daot_pullback_wins / len(daot_pullback) * 100, 1) if daot_pullback else 0,
            "start_date": start_date,
            "last_update": last_update,
            "backtest_days": backtest_days,
            "position_shares": 14100,
            "position_cost": 58.897,
            "monthly_avg_profit": round(total_profit / max(backtest_days / 22, 1), 2),
            "data_source": "realtime"  # 标记数据来源
        }

    # 没有已评估信号时，返回回测基线数据
    return DEFAULT_TRADE_STATS


# ============================================================
# API Routes
# ============================================================

@app.route("/api/kline")
def api_kline():
    """获取最新1分钟K线数据"""
    limit = request.args.get("limit", 240, type=int)
    date = request.args.get("date", None)

    # v16.2: 如果请求的是今天且没有指定日期，优先返回实时数据
    if not date:
        rt_bars, rt_meta = load_realtime_bars(limit)
        if rt_bars and len(rt_bars) > 0:
            return jsonify({
                "date": rt_meta.get('date', '') if rt_meta else '',
                "stock": "中国平安",
                "code": "601318",
                "bars": rt_bars,
                "count": len(rt_bars),
                "last_update": rt_meta.get('last_update', '') if rt_meta else '',
                "is_realtime": True
            })

    # 回退到CSV
    if date:
        filepath = os.path.join(DATA_DIR, f"{date}.csv")
        if not os.path.exists(filepath):
            return jsonify({"error": "数据文件不存在", "date": date}), 404
    else:
        filepath = get_latest_data_file()
        if not filepath:
            return jsonify({"error": "无可用数据"}), 404

    bars = parse_csv_to_json(filepath, limit)
    filename = os.path.basename(filepath)
    date_str = filename.replace(".csv", "")

    return jsonify({
        "date": date_str,
        "stock": "中国平安",
        "code": "601318",
        "bars": bars,
        "count": len(bars),
        "last_update": datetime.now().strftime("%Y-%m-%d %H:%M:%S"),
        "is_realtime": False
    })


@app.route("/api/signals")
def api_signals():
    """获取信号历史"""
    limit = request.args.get("limit", 50, type=int)
    signals = get_signal_history()
    return jsonify({
        "signals": signals[:limit],
        "count": len(signals)
    })


@app.route("/api/stats")
def api_stats():
    """获取累计交易统计"""
    stats = get_trade_stats()
    return jsonify(stats)


@app.route("/api/overview")
def api_overview():
    """综合概览数据（一次请求拿全）"""
    # v16.2: 优先读取盘中实时JSON（每分钟更新），回退到收盘CSV
    rt_bars, rt_meta = load_realtime_bars(240)
    
    if rt_bars and len(rt_bars) > 0:
        bars = rt_bars
        date_str = rt_meta.get('date', '') if rt_meta else ''
        last_update = rt_meta.get('last_update', '') if rt_meta else ''
        current_price = bars[-1].get('close')
        price_change = round(current_price - bars[0]['open'], 2) if len(bars) >= 2 else None
    else:
        filepath = get_latest_data_file()
        bars = []
        current_price = None
        price_change = None
        date_str = ""
        last_update = ""

        if filepath:
            bars = parse_csv_to_json(filepath, 240)
            if bars:
                last = bars[-1]
                current_price = last["close"]
                if len(bars) >= 2:
                    price_change = round(current_price - bars[0]["open"], 2)
                date_str = os.path.basename(filepath).replace(".csv", "")

    stats = get_trade_stats()
    signals = get_signal_history()[:10]

    return jsonify({
        "stock": "中国平安",
        "code": "601318",
        "date": date_str,
        "current_price": current_price,
        "price_change": price_change,
        "bars": bars,
        "signals": signals,
        "stats": stats,
        "last_update": last_update or datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    })


@app.route("/api/status")
def api_status():
    """监控系统运行状态"""
    # 检查pa_monitor是否在运行
    import subprocess
    try:
        result = subprocess.run(["pgrep", "-f", "pa_monitor"], capture_output=True, text=True)
        is_running = bool(result.stdout.strip())
    except:
        is_running = False

    # 获取最新数据文件时间
    filepath = get_latest_data_file()
    last_data_time = ""
    if filepath and os.path.exists(filepath):
        last_data_time = datetime.fromtimestamp(
            os.path.getmtime(filepath)
        ).strftime("%Y-%m-%d %H:%M:%S")

    return jsonify({
        "monitor_running": is_running,
        "last_data_update": last_data_time,
        "api_version": "1.0.0",
        "system_version": "v16.1.2"
    })


# ============================================================
# Static files (网站前端)
# ============================================================
@app.route("/")
def index():
    return send_from_directory("/var/www/abelleung", "index.html")


if __name__ == "__main__":
    port = int(os.environ.get("PORT", 5100))
    app.run(host="0.0.0.0", port=port, debug=False)
