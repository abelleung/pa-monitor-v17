"""
参数穷举优化器 — 中国平安A股盯盘系统 v16.5

对4个策略的所有参数做穷举回测，找出夏普比率最高、胜率>60%、日内收益最大化的参数组合。

用法:
    python optimizer.py --stage 1a --n-jobs 8    # 动量倒T独立优化
    python optimizer.py --stage 1b --n-jobs 8    # BOLL倒T独立优化
    python optimizer.py --stage 1c --n-jobs 8    # 冲高回落独立优化
    python optimizer.py --stage 1d --n-jobs 8    # 正T买入独立优化
    python optimizer.py --stage 2  --n-jobs 8    # 联合优化
    python optimizer.py --stage 3  --n-jobs 8    # 精细调优
    python optimizer.py --stage all --n-jobs 8     # 全流程
"""

import sys
import os
import csv
import json
import time
import argparse
import itertools
import numpy as np
import pandas as pd
from datetime import datetime
from multiprocessing import Pool, cpu_count
from functools import partial

sys.path.insert(0, '.')
from indicators import STRATEGY_CONFIG, calc_indicators, safe_float, get_time_tuple

# 导入策略函数（使用config参数）
import strategies as strat

# ============================================================
# 参数搜索范围定义
# ============================================================

PARAM_RANGES = {
    # 动量倒T
    'ZHANGDIE_THRESH': [60, 80, 100, 120, 140, 160, 180],
    'FENGXIAN_THRESH': [60, 65, 70, 75, 80, 85, 90, 95, 100],
    'BOLL_AMOUNT_THRESH_WAN': [2000, 2500, 3000, 3500, 4000, 4500, 5000],
    'BOLL_MA_ABOVE': [0.05, 0.10, 0.15, 0.20, 0.25, 0.30],
    'MACD_BAR_THRESH': [0.02, 0.04, 0.06, 0.08, 0.10, 0.12],

    # BOLL倒T（精简搜索空间）
    'BOLL_AMOUNT_THRESH_WAN': [2000, 3000, 4000],
    'BOLL_MA_ABOVE': [0.05, 0.10, 0.20],
    'BOLL_MACD_THRESH': [0.04, 0.06, 0.10],
    'BOLL_DEVIATION_THRESH': [0.20, 0.30, 0.50],
    'BOLL_TOUCH_RATIO': [0.990, 0.995, 1.000],
    'BOLL_DAY_GAIN_MAX': [1.5, 2.0, 3.0],
    'BOLL_PULLBACK_FROM_HIGH': [0.05, 0.10, 0.20],

    # 冲高回落（精简搜索空间）
    'PULLBACK_AMOUNT_THRESH_WAN': [2000, 3000, 4000],
    'PULLBACK_DAY_HIGH_DEVIATION': [0.10, 0.20, 0.30],
    'PULLBACK_PULLBACK_FROM_HIGH': [0.05, 0.10, 0.15],
    'PULLBACK_CLOSE_ABOVE_AVG': [0.10, 0.20, 0.30],
    'PULLBACK_BANDWIDTH_THRESH': [0.5, 1.0, 1.5],
    'PULLBACK_END': [(13, 30), (14, 0), (14, 30)],

    # 正T买入（精简搜索空间，加快速度）
    'ZHENGT_MA_BELOW': [0.35, 0.55, 0.80],
    'ZHENGT_RISK_THRESH': [7, 12, 20],
    'ZHENGT_AMOUNT_THRESH_WAN': [3000, 5000, 7000],
    'ZHENGT_ZD_THRESH': [-1, 0, 1],
    'ZHENGT_MIN_AMPLITUDE': [0.20, 0.40, 0.80],
    'ZHENGT_MIN_BOLL_WIDTH': [0.05, 0.10, 0.50],
    'ZHENGT_TARGET_DIFF': [0.15, 0.20, 0.25],
    'ZHENGT_STOP_LOSS_DIFF': [0.10, 0.15, 0.20],

    # 共享参数
    'COOLDOWN_BARS': [15, 20, 25, 30, 35, 40, 50, 60],
    'CRASH_DAY_DROP_MAX': [1.0, 1.5, 2.0, 2.5, 3.0, 4.0],
    'BOOM_DAY_GAIN_MAX': [1.0, 2.0, 3.0, 4.0, 5.0],
    'ZHENGT_TARGET_DIFF': [0.15, 0.20, 0.25],
    'ZHENGT_STOP_LOSS_DIFF': [0.10, 0.15, 0.20],
    'TARGET_DIFF_NORMAL': [0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50],
    'STOP_LOSS_DIFF_NORMAL': [0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50],
    'ZHENGT_LATEST_HOUR': [13, 14],
}

# 用于各阶段的默认参数（固定其他策略用）
DEFAULT_CONFIG = STRATEGY_CONFIG.copy()


# ============================================================
# 数据加载与预处理
# ============================================================

def load_and_prepare_data(csv_file='平安1-5月_回测数据_2026.csv'):
    """加载CSV，计算指标，返回准备好的DataFrame"""
    print(f"加载数据: {csv_file}")
    df = pd.read_csv(csv_file, encoding='utf-8-sig')
    # 转换数值列
    for col in ['开盘', '最高', '最低', '收盘', '成交量', '成交额']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    # 删除无法解析的行（如头部说明文字）
    df = df.dropna(subset=['收盘', '最高', '最低'])
    print(f"  清洗后行数: {len(df)}")

    # 计算技术指标
    df = calc_indicators(df)
    print(f"  指标计算完成，列: {list(df.columns)}")

    # 提取日期用于分组
    df['date'] = df['时间'].str[:10]
    df['hour'] = pd.to_numeric(df['时间'].str[11:13], errors='coerce').fillna(0).astype(int)
    df['minute'] = pd.to_numeric(df['时间'].str[14:16], errors='coerce').fillna(0).astype(int)
    # 删除时间解析失败的行（小时为0的异常行）
    df = df[df['hour'] > 0].copy()
    # 重置索引，确保日内bar索引连续
    df = df.reset_index(drop=True)

    # 预提取为numpy数组加速日内循环
    df['_close'] = df['收盘'].astype(float)
    df['_high'] = df['最高'].astype(float)
    df['_low'] = df['最低'].astype(float)
    df['_amount_wan'] = df['成交额_万'].astype(float)
    df['_avg_price'] = df['日均价'].astype(float)
    df['_zhangdie'] = df['涨跌'].astype(float)
    df['_fengxian'] = df['风险'].astype(float)
    df['_macd_bar'] = df['MACD柱'].astype(float)
    df['_boll_upper'] = df['BOLL上轨'].astype(float)
    df['_boll_width'] = df['BOLL带宽'].astype(float)

    dates = sorted(df['date'].unique())
    print(f"  交易日数: {len(dates)}, 日期范围: {dates[0]} ~ {dates[-1]}")
    return df


# ============================================================
# 交易模拟引擎
# ============================================================

def simulate_trades(df, config):
    """
    对给定参数配置运行完整交易模拟。

    返回: (trades_list, daily_pnl_dict)
    """
    trades = []
    daily_pnl = {}
    dates = sorted(df['date'].unique())

    for date in dates:
        day_df = df[df['date'] == date].reset_index(drop=True)
        if len(day_df) < 5:
            continue

        day_pnl = 0.0
        day_high = 0.0
        day_low = float(day_df['_low'].min())

        # 持仓状态
        daot_pos = None   # {bar, price, time, strategy}
        zhengt_pos = None  # {bar, price, time}

        # 冷却期追踪（用日内bar索引）
        last_daot_bar = -999
        last_zhengt_bar = -999

        # 当日开盘价和昨收（用于暴跌/暴涨保护）
        open_price = float(day_df.iloc[0]['开盘'])
        # 简化：用昨收估算（实际应从日线获取，这里用前一日收盘价近似）
        prev_close = open_price  # 简化假设

        n_bars = len(day_df)

        for i in range(n_bars):
            row = day_df.iloc[i]
            bar_idx = i

            price = row['_close']
            high = row['_high']
            low = row['_low']
            amount_wan = row['_amount_wan']
            avg_price = row['_avg_price']
            zhangdie = row['_zhangdie']
            fengxian = row['_fengxian']
            macd_bar = row['_macd_bar']
            boll_upper = row['_boll_upper']
            boll_width = row['_boll_width']

            # 更新日内最高/最低
            if high > day_high:
                day_high = high

            # ========== 倒T卖出信号检查 ==========
            cooldown_ok = (bar_idx - last_daot_bar) >= config['COOLDOWN_BARS']

            if cooldown_ok and daot_pos is None:
                # 暴跌保护
                crash_protected = False
                if prev_close > 0 and price < prev_close:
                    day_drop = (prev_close - price) / prev_close * 100
                    if day_drop > config['CRASH_DAY_DROP_MAX']:
                        crash_protected = True

                if not crash_protected:
                    # 策略1: 动量
                    mom_triggered = False
                    if config['ZHANGDIE_THRESH'] > 0:  # 参数>0才检查
                        cond1 = zhangdie > config['ZHANGDIE_THRESH']
                        cond2 = fengxian > config['FENGXIAN_THRESH']
                        cond3 = amount_wan >= config['BOLL_AMOUNT_THRESH_WAN']
                        cond4 = (price - avg_price) > config['BOLL_MA_ABOVE']
                        cond5 = abs(macd_bar) > config['MACD_BAR_THRESH']
                        mom_triggered = cond1 and cond2 and cond3 and cond4 and cond5

                    boll_triggered = False
                    if not mom_triggered and config['BOLL_TOUCH_RATIO'] > 0:
                        cond1 = high >= boll_upper * config['BOLL_TOUCH_RATIO']
                        cond2 = amount_wan >= config['BOLL_AMOUNT_THRESH_WAN']
                        cond3 = (price - avg_price) > config['BOLL_MA_ABOVE']
                        cond4 = (price - avg_price) > config['BOLL_DEVIATION_THRESH']
                        cond5 = macd_bar > config['BOLL_MACD_THRESH']
                        day_gain_pct = (price - prev_close) / prev_close * 100 if prev_close > 0 else 0
                        cond6 = day_gain_pct <= config['BOLL_DAY_GAIN_MAX']
                        cond7 = (day_high - price) > config['BOLL_PULLBACK_FROM_HIGH']
                        boll_triggered = cond1 and cond2 and cond3 and cond4 and cond5 and cond6 and cond7

                    pullback_triggered = False
                    if not mom_triggered and not boll_triggered:
                        is_low_vol = boll_width < config['PULLBACK_BANDWIDTH_THRESH']
                        if is_low_vol:
                            cond1 = (day_high - avg_price) > config['PULLBACK_DAY_HIGH_DEVIATION']
                            cond2 = (day_high - high) > config['PULLBACK_PULLBACK_FROM_HIGH']
                            cond3 = (price - avg_price) > config['PULLBACK_CLOSE_ABOVE_AVG']
                            cond4 = amount_wan >= config['PULLBACK_AMOUNT_THRESH_WAN']
                            cond5 = price < boll_upper
                            cond6 = boll_width > config['PULLBACK_BANDWIDTH_THRESH']
                            h = int(row['hour'])
                            m = int(row['minute'])
                            end_h, end_m = config['PULLBACK_END']
                            in_window = (h, m) >= (9, 40) and (h, m) <= (end_h, end_m)
                            cond7 = in_window
                            pullback_triggered = cond1 and cond2 and cond3 and cond4 and cond5 and cond6 and cond7

                    triggered = mom_triggered or boll_triggered or pullback_triggered
                    if triggered:
                        strategy = 'momentum' if mom_triggered else ('boll' if boll_triggered else 'pullback')
                        daot_pos = {
                            'bar': bar_idx,
                            'price': price,
                            'time': str(row['时间']),
                            'strategy': strategy,
                            'target_diff': config['TARGET_DIFF_NORMAL'],
                            'stop_loss_diff': config['STOP_LOSS_DIFF_NORMAL'],
                        }
                        last_daot_bar = bar_idx

            # ========== 正T买入信号检查 ==========
            zhengt_cooldown_ok = (bar_idx - last_zhengt_bar) >= config['COOLDOWN_BARS']

            if zhengt_cooldown_ok and zhengt_pos is None:
                # 暴涨保护
                boom_protected = False
                if prev_close > 0:
                    day_gain = (price - prev_close) / prev_close * 100
                    if day_gain > config['BOOM_DAY_GAIN_MAX']:
                        boom_protected = True

                # 时间约束 < 14:00
                h = int(row['hour'])
                if h >= config['ZHENGT_LATEST_HOUR']:
                    boom_protected = True

                if not boom_protected:
                    price_diff_avg = avg_price - price
                    amplitude = day_high - day_low

                    cond1 = price_diff_avg > config['ZHENGT_MA_BELOW']
                    cond2 = fengxian < config['ZHENGT_RISK_THRESH']
                    cond3 = amount_wan >= config['ZHENGT_AMOUNT_THRESH_WAN']
                    cond4 = zhangdie <= config['ZHENGT_ZD_THRESH']
                    cond5 = amplitude >= config['ZHENGT_MIN_AMPLITUDE']
                    cond6 = boll_width > config['ZHENGT_MIN_BOLL_WIDTH']

                    if cond1 and cond2 and cond3 and cond4 and cond5 and cond6:
                        zhengt_pos = {
                            'bar': bar_idx,
                            'price': price,
                            'time': str(row['时间']),
                            'target_diff': config['ZHENGT_TARGET_DIFF'],
                            'stop_loss_diff': config['ZHENGT_STOP_LOSS_DIFF'],
                        }
                        last_zhengt_bar = bar_idx

            # ========== 倒T持仓管理 ==========
            if daot_pos is not None:
                sell_price = daot_pos['price']
                trigger_bar = daot_pos['bar']
                target = daot_pos['target_diff']
                stop = daot_pos['stop_loss_diff']

                # 止损检查：最高价 >= 卖出价 + 止损差价
                if high >= sell_price + stop:
                    pnl = -stop
                    day_pnl += pnl
                    trades.append({
                        'type': 'daot',
                        'strategy': daot_pos['strategy'],
                        'date': date,
                        'buy_bar': trigger_bar,
                        'sell_bar': bar_idx,
                        'buy_time': daot_pos['time'],
                        'sell_time': str(row['时间']),
                        'buy_price': sell_price,
                        'sell_price': sell_price + stop,
                        'pnl': pnl,
                        'stop_loss': True,
                    })
                    daot_pos = None

                # 止盈检查：窗口内最低价（触发后下一根K线开始）
                elif bar_idx > trigger_bar:
                    # 评估窗口：trigger+1 到当前bar
                    eval_min = day_df.iloc[trigger_bar + 1:bar_idx + 1]['_low'].min()
                    if sell_price - eval_min >= target:
                        pnl = sell_price - eval_min
                        day_pnl += pnl
                        trades.append({
                            'type': 'daot',
                            'strategy': daot_pos['strategy'],
                            'date': date,
                            'buy_bar': trigger_bar,
                            'sell_bar': bar_idx,
                            'buy_time': daot_pos['time'],
                            'sell_time': str(row['时间']),
                            'buy_price': sell_price,
                            'sell_price': eval_min,
                            'pnl': pnl,
                            'stop_loss': False,
                        })
                        daot_pos = None

                # 收盘强制平仓
                if daot_pos is not None and bar_idx >= n_bars - 1:
                    eval_min = day_df.iloc[trigger_bar + 1:]['_low'].min()
                    if np.isnan(eval_min):
                        eval_min = low
                    pnl = sell_price - eval_min
                    day_pnl += pnl
                    trades.append({
                        'type': 'daot',
                        'strategy': daot_pos['strategy'],
                        'date': date,
                        'buy_bar': trigger_bar,
                        'sell_bar': bar_idx,
                        'buy_time': daot_pos['time'],
                        'sell_time': str(row['时间']),
                        'buy_price': sell_price,
                        'sell_price': eval_min,
                        'pnl': pnl,
                        'stop_loss': False,
                    })
                    daot_pos = None

            # ========== 正T持仓管理 ==========
            if zhengt_pos is not None:
                buy_price = zhengt_pos['price']
                trigger_bar = zhengt_pos['bar']
                target = zhengt_pos['target_diff']
                stop = zhengt_pos['stop_loss_diff']

                # 止损检查：最低价 <= 买入价 - 止损差价
                if low <= buy_price - stop:
                    pnl = -stop
                    day_pnl += pnl
                    trades.append({
                        'type': 'zhengt',
                        'date': date,
                        'buy_bar': trigger_bar,
                        'sell_bar': bar_idx,
                        'buy_time': zhengt_pos['time'],
                        'sell_time': str(row['时间']),
                        'buy_price': buy_price,
                        'sell_price': buy_price - stop,
                        'pnl': pnl,
                        'stop_loss': True,
                    })
                    zhengt_pos = None

                # 止盈检查
                elif bar_idx > trigger_bar:
                    eval_max = day_df.iloc[trigger_bar + 1:bar_idx + 1]['_high'].max()
                    if eval_max - buy_price >= target:
                        pnl = eval_max - buy_price
                        day_pnl += pnl
                        trades.append({
                            'type': 'zhengt',
                            'date': date,
                            'buy_bar': trigger_bar,
                            'sell_bar': bar_idx,
                            'buy_time': zhengt_pos['time'],
                            'sell_time': str(row['时间']),
                            'buy_price': buy_price,
                            'sell_price': eval_max,
                            'pnl': pnl,
                            'stop_loss': False,
                        })
                        zhengt_pos = None

                # 收盘强制平仓
                if zhengt_pos is not None and bar_idx >= n_bars - 1:
                    eval_max = day_df.iloc[trigger_bar + 1:]['_high'].max()
                    if np.isnan(eval_max):
                        eval_max = high
                    pnl = eval_max - buy_price
                    day_pnl += pnl
                    trades.append({
                        'type': 'zhengt',
                        'date': date,
                        'buy_bar': trigger_bar,
                        'sell_bar': bar_idx,
                        'buy_time': zhengt_pos['time'],
                        'sell_time': str(row['时间']),
                        'buy_price': buy_price,
                        'sell_price': eval_max,
                        'pnl': pnl,
                        'stop_loss': False,
                    })
                    zhengt_pos = None

        daily_pnl[date] = day_pnl

    return trades, daily_pnl


# ============================================================
# 指标计算
# ============================================================

def compute_metrics(trades, daily_pnl):
    """计算夏普比率、最大回撤、胜率等指标"""
    if not daily_pnl or not trades:
        return {
            'sharpe_ratio': 0.0,
            'max_drawdown_pct': 99.0,
            'win_rate': 0.0,
            'total_return': 0.0,
            'total_trades': 0,
            'avg_pnl': 0.0,
            'profit_factor': 0.0,
            'trades_per_day': 0.0,
            'trading_days': 0,
        }

    dates = sorted(daily_pnl.keys())
    daily_returns = [daily_pnl[d] for d in dates]

    # 夏普比率（年化）
    mean_ret = np.mean(daily_returns)
    std_ret = np.std(daily_returns, ddof=1)
    if std_ret > 0:
        sharpe = (mean_ret / std_ret) * np.sqrt(252)
    else:
        sharpe = 0.0

    # 最大回撤（基于累计P&L）
    cumulative = np.cumsum(daily_returns)
    running_max = np.maximum.accumulate(cumulative)
    drawdown = running_max - cumulative
    max_dd = drawdown.max() if len(drawdown) > 0 else 0.0

    # 最大回撤百分比：最大回撤 / 累计峰值
    peak = running_max.max() if len(running_max) > 0 else 0.0
    if peak > 0:
        max_dd_pct = (max_dd / peak) * 100
    else:
        pos_returns = [r for r in daily_returns if r > 0]
        avg_daily = np.mean(pos_returns) if pos_returns else 1.0
        max_dd_pct = (max_dd / avg_daily) * 100 if avg_daily > 0 else 0.0

    # 胜率
    wins = sum(1 for t in trades if t['pnl'] > 0)
    total_trades = len(trades)
    win_rate = (wins / total_trades * 100) if total_trades > 0 else 0

    # 总收益
    total_return = sum(daily_returns)

    # 平均盈亏
    avg_pnl = np.mean([t['pnl'] for t in trades]) if trades else 0

    # 盈亏比
    gross_profit = sum(t['pnl'] for t in trades if t['pnl'] > 0)
    gross_loss = abs(sum(t['pnl'] for t in trades if t['pnl'] < 0))
    profit_factor = gross_profit / gross_loss if gross_loss > 0 else float('inf')

    # 日均交易次数
    trading_days = len([d for d in daily_pnl if daily_pnl[d] != 0])
    trades_per_day = total_trades / trading_days if trading_days > 0 else 0

    return {
        'sharpe_ratio': sharpe,
        'max_drawdown_pct': max_dd_pct,
        'win_rate': win_rate,
        'total_return': total_return,
        'total_trades': total_trades,
        'avg_pnl': avg_pnl,
        'profit_factor': profit_factor,
        'trades_per_day': trades_per_day,
        'trading_days': trading_days,
    }


# ============================================================
# 评估单个参数组合（用于并行）
# ============================================================

# 全局变量，由worker_init初始化
_global_df = None
_global_config_base = None


def worker_init(df, config_base):
    global _global_df, _global_config_base
    _global_df = df
    _global_config_base = config_base


def evaluate_combo(params_tuple):
    """
    评估单个参数组合。
    params_tuple: (stage, param1, param2, ...) 其中stage决定哪些参数生效
    """
    global _global_df, _global_config_base

    combo = dict(params_tuple)
    config = _global_config_base.copy()
    config.update(combo)

    try:
        trades, daily_pnl = simulate_trades(_global_df, config)
        metrics = compute_metrics(trades, daily_pnl)

        # 早剪枝：交易次数太少
        if metrics['total_trades'] < 20:
            return None

        result = {'params': combo, 'metrics': metrics}
        return result
    except Exception as e:
        return None


# ============================================================
# 分阶段优化
# ============================================================

def run_stage_1a(df, n_jobs=8):
    """Stage 1A: 动量倒T独立优化"""
    print("\n" + "="*60)
    print("Stage 1A: 动量倒T独立优化")
    print("="*60)

    keys = ['ZHANGDIE_THRESH', 'FENGXIAN_THRESH', 'BOLL_AMOUNT_THRESH_WAN', 'BOLL_MA_ABOVE', 'MACD_BAR_THRESH']
    ranges = [PARAM_RANGES[k] for k in keys]

    combos = []
    for vals in itertools.product(*ranges):
        combo = {k: v for k, v in zip(keys, vals)}
        combos.append(tuple(combo.items()))

    print(f"总组合数: {len(combos):,}")
    print(f"并行进程: {n_jobs}")

    t0 = time.time()
    with Pool(processes=n_jobs, initializer=worker_init, initargs=(df, DEFAULT_CONFIG)) as pool:
        results = list(pool.imap_unordered(evaluate_combo, combos, chunksize=50))
    t1 = time.time()

    results = [r for r in results if r is not None]
    print(f"有效组合: {len(results)}, 耗时: {t1-t0:.1f}s")

    # 按夏普比率排序
    results.sort(key=lambda x: x['metrics']['sharpe_ratio'], reverse=True)
    return results


def run_stage_1b(df, top_momentum, n_jobs=8):
    """Stage 1B: BOLL倒T独立优化"""
    print("\n" + "="*60)
    print("Stage 1B: BOLL倒T独立优化")
    print("="*60)

    keys = ['BOLL_AMOUNT_THRESH_WAN', 'BOLL_MA_ABOVE', 'BOLL_MACD_THRESH',
            'BOLL_DEVIATION_THRESH', 'BOLL_TOUCH_RATIO', 'BOLL_DAY_GAIN_MAX', 'BOLL_PULLBACK_FROM_HIGH']

    combos = []
    for top_m in top_momentum[:5]:
        m_params = top_m['params']
        for vals in itertools.product(*[PARAM_RANGES[k] for k in keys]):
            combo = {k: v for k, v in zip(keys, vals)}
            combo.update(m_params)  # 叠加动量参数
            combos.append(tuple(combo.items()))

    print(f"总组合数: {len(combos):,}")

    t0 = time.time()
    with Pool(processes=n_jobs, initializer=worker_init, initargs=(df, DEFAULT_CONFIG)) as pool:
        results = list(pool.imap_unordered(evaluate_combo, combos, chunksize=50))
    t1 = time.time()

    results = [r for r in results if r is not None]
    print(f"有效组合: {len(results)}, 耗时: {t1-t0:.1f}s")

    results.sort(key=lambda x: x['metrics']['sharpe_ratio'], reverse=True)
    return results


def run_stage_1c(df, top_momentum, top_boll, n_jobs=8):
    """Stage 1C: 冲高回落独立优化"""
    print("\n" + "="*60)
    print("Stage 1C: 冲高回落独立优化")
    print("="*60)

    keys = ['PULLBACK_AMOUNT_THRESH_WAN', 'PULLBACK_DAY_HIGH_DEVIATION',
            'PULLBACK_PULLBACK_FROM_HIGH', 'PULLBACK_CLOSE_ABOVE_AVG',
            'PULLBACK_BANDWIDTH_THRESH', 'PULLBACK_END']

    combos = []
    top_m = top_momentum[:3]
    top_b = top_boll[:3]
    for top_m_params in top_m:
        for top_b_params in top_b:
            base = {**top_m_params['params'], **top_b_params['params']}
            for vals in itertools.product(*[PARAM_RANGES[k] for k in keys]):
                combo = {k: v for k, v in zip(keys, vals)}
                combo.update(base)
                combos.append(tuple(combo.items()))

    print(f"总组合数: {len(combos):,}")

    t0 = time.time()
    with Pool(processes=n_jobs, initializer=worker_init, initargs=(df, DEFAULT_CONFIG)) as pool:
        results = list(pool.imap_unordered(evaluate_combo, combos, chunksize=50))
    t1 = time.time()

    results = [r for r in results if r is not None]
    print(f"有效组合: {len(results)}, 耗时: {t1-t0:.1f}s")

    results.sort(key=lambda x: x['metrics']['sharpe_ratio'], reverse=True)
    return results


def run_stage_1d(df, n_jobs=8):
    """Stage 1D: 正T买入独立优化"""
    print("\n" + "="*60)
    print("Stage 1D: 正T买入独立优化")
    print("="*60)

    keys = ['ZHENGT_MA_BELOW', 'ZHENGT_RISK_THRESH', 'ZHENGT_AMOUNT_THRESH_WAN',
            'ZHENGT_ZD_THRESH', 'ZHENGT_MIN_AMPLITUDE', 'ZHENGT_MIN_BOLL_WIDTH',
            'ZHENGT_TARGET_DIFF', 'ZHENGT_STOP_LOSS_DIFF']

    combos = []
    for vals in itertools.product(*[PARAM_RANGES[k] for k in keys]):
        combo = {k: v for k, v in zip(keys, vals)}
        combos.append(tuple(combo.items()))

    print(f"总组合数: {len(combos):,}")

    t0 = time.time()
    with Pool(processes=n_jobs, initializer=worker_init, initargs=(df, DEFAULT_CONFIG)) as pool:
        results = list(pool.imap_unordered(evaluate_combo, combos, chunksize=50))
    t1 = time.time()

    results = [r for r in results if r is not None]
    print(f"有效组合: {len(results)}, 耗时: {t1-t0:.1f}s")

    results.sort(key=lambda x: x['metrics']['sharpe_ratio'], reverse=True)
    return results


# ============================================================
# 结果输出
# ============================================================

def print_results(results, top_n=20, title="TOP RESULTS"):
    """打印Top N结果表格"""
    print(f"\n{'='*140}")
    print(f"{title}")
    print(f"{'='*140}")

    header = f"{'Rank':<5} {'Sharpe':<8} {'Win%':<8} {'DD%':<8} {'Return':<10} {'Trades':<8} {'TPDay':<8} {'AvgPnL':<8} {'PF':<8} {'Key Params'}"
    print(header)
    print("-"*140)

    for i, r in enumerate(results[:top_n], 1):
        m = r['metrics']
        p = r['params']
        # 显示关键参数摘要
        key_parts = []
        for k in ['ZHANGDIE_THRESH', 'FENGXIAN_THRESH', 'BOLL_TOUCH_RATIO',
                   'PULLBACK_AMOUNT_THRESH_WAN', 'ZHENGT_MA_BELOW']:
            if k in p:
                key_parts.append(f"{k[:4]}={p[k]}")
        summary = " ".join(key_parts[:4])

        dd_str = f"{m['max_drawdown_pct']:.1f}" if m['max_drawdown_pct'] < 99 else "N/A"
        print(f"{i:<5} {m['sharpe_ratio']:<8.2f} {m['win_rate']:<8.1f} {dd_str:<8} "
              f"{m['total_return']:<10.2f} {m['total_trades']:<8} {m['trades_per_day']:<8.2f} "
              f"{m['avg_pnl']:<8.3f} {m['profit_factor']:<8.2f} {summary}")

    print("="*140)


def save_results(results, filename):
    """保存结果到CSV"""
    if not results:
        return
    fieldnames = ['sharpe_ratio', 'win_rate', 'max_drawdown_pct', 'total_return',
                  'total_trades', 'avg_pnl', 'profit_factor', 'trades_per_day', 'trading_days']
    all_keys = set()
    for r in results:
        all_keys.update(r['params'].keys())
    param_keys = sorted(all_keys)

    with open(filename, 'w', newline='', encoding='utf-8-sig') as f:
        writer = csv.DictWriter(f, fieldnames=fieldnames + param_keys)
        writer.writeheader()
        for r in results:
            row = {**r['metrics'], **r['params']}
            # 将tuple值转为字符串（如PULLBACK_END=(14,0)）
            for k, v in row.items():
                if isinstance(v, (tuple, list)):
                    row[k] = str(v)
            writer.writerow(row)
    print(f"\n结果已保存: {filename}")


def save_top_params(results, top_n=5, filename='optimized_config.json'):
    """保存Top N参数组合到JSON"""
    top = []
    for r in results[:top_n]:
        top.append({
            'sharpe_ratio': r['metrics']['sharpe_ratio'],
            'win_rate': r['metrics']['win_rate'],
            'max_drawdown_pct': r['metrics']['max_drawdown_pct'],
            'total_return': r['metrics']['total_return'],
            'total_trades': r['metrics']['total_trades'],
            'params': r['params'],
        })
    with open(filename, 'w', encoding='utf-8') as f:
        json.dump(top, f, indent=2, ensure_ascii=False)
    print(f"Top {top_n} 参数已保存: {filename}")


# ============================================================
# 主程序
# ============================================================

def main():
    parser = argparse.ArgumentParser(description='参数穷举优化器')
    parser.add_argument('--stage', type=str, default='all',
                        choices=['1a', '1b', '1c', '1d', '2', '3', 'all'],
                        help='优化阶段')
    parser.add_argument('--n-jobs', type=int, default=min(8, cpu_count()),
                        help='并行进程数')
    parser.add_argument('--csv', type=str, default='平安1-5月_回测数据_2026.csv',
                        help='回测数据CSV文件')
    parser.add_argument('--top-n', type=int, default=20,
                        help='显示和保存的Top N结果')
    args = parser.parse_args()

    print(f"优化器启动 — 阶段: {args.stage}, 并行: {args.n_jobs} 进程")
    print(f"数据文件: {args.csv}")

    # 加载数据
    df = load_and_prepare_data(args.csv)
    all_results = {}

    # 加载之前的Stage结果（如果文件存在）
    for stage in ['1a', '1b', '1c', '1d', '2', '3']:
        config_file = f'opt_config_{stage}.json'
        if os.path.exists(config_file):
            with open(config_file, 'r', encoding='utf-8') as f:
                all_results[stage] = json.load(f)
            print(f'已加载 {config_file}')

    # Stage 1: 独立优化（各阶段可独立运行）
    if args.stage in ('1a', 'all'):
        r = run_stage_1a(df, args.n_jobs)
        all_results['1a'] = r
        print_results(r, args.top_n, "Stage 1A: 动量倒T TOP 20")
        save_results(r, 'opt_results_1a.csv')
        save_top_params(r, 5, 'opt_config_1a.json')

    if args.stage in ('1b', 'all'):
        # 如果1a已运行则用其结果，否则用默认config
        if '1a' in all_results:
            top_momentum = all_results['1a'][:5]
        else:
            top_momentum = [{'params': DEFAULT_CONFIG.copy()} for _ in range(5)]
        r = run_stage_1b(df, top_momentum, args.n_jobs)
        all_results['1b'] = r
        print_results(r, args.top_n, "Stage 1B: BOLL倒T TOP 20")
        save_results(r, 'opt_results_1b.csv')
        save_top_params(r, 5, 'opt_config_1b.json')

    if args.stage in ('1c', 'all'):
        if '1a' in all_results:
            top_m = all_results['1a'][:3]
        else:
            top_m = [{'params': DEFAULT_CONFIG.copy()} for _ in range(3)]
        if '1b' in all_results:
            top_b = all_results['1b'][:3]
        else:
            top_b = [{'params': DEFAULT_CONFIG.copy()} for _ in range(3)]
        r = run_stage_1c(df, top_m, top_b, args.n_jobs)
        all_results['1c'] = r
        print_results(r, args.top_n, "Stage 1C: 冲高回落 TOP 20")
        save_results(r, 'opt_results_1c.csv')
        save_top_params(r, 5, 'opt_config_1c.json')

    if args.stage in ('1d', 'all'):
        r = run_stage_1d(df, args.n_jobs)
        all_results['1d'] = r
        print_results(r, args.top_n, "Stage 1D: 正T买入 TOP 20")
        save_results(r, 'opt_results_1d.csv')
        save_top_params(r, 5, 'opt_config_1d.json')

    # Stage 2: 联合优化
    if args.stage in ('2', 'all'):
        required = ['1a', '1b', '1c', '1d']
        if all(k in all_results for k in required):
            r = run_stage_2(df, all_results['1a'], all_results['1b'],
                         all_results['1c'], all_results['1d'], args.n_jobs)
            all_results['2'] = r
            print_results(r, args.top_n, "Stage 2: 联合优化 TOP 20")
            save_results(r, 'opt_results_2.csv')
            save_top_params(r, 5, 'opt_config_2.json')
        else:
            print("警告: Stage 2 需要 Stage 1 全部完成，跳过")

    # Stage 3: 精细调优
    if args.stage in ('3', 'all'):
        if '2' in all_results:
            r = run_stage_3(df, all_results['2'][:5], args.n_jobs)
            all_results['3'] = r
            print_results(r, args.top_n, "Stage 3: 精细调优 TOP 20")
            save_results(r, 'opt_results_3.csv')
            save_top_params(r, 5, 'opt_config_3.json')
        else:
            print("警告: Stage 3 需要 Stage 2 完成，跳过")
def run_stage_2(df, top_1a, top_1b, top_1c, top_1d, n_jobs=8):
    """Stage 2: 联合优化 — 用各策略Top 5，在±1步长内联合搜索"""
    print("\n" + "="*60)
    print("Stage 2: 联合优化（基于Stage 1 Top 5）")
    print("="*60)

    # 收集各策略Top 5的参数
    base_combos = []
    for a in top_1a[:5]:
        for b in top_1b[:5]:
            for c in top_1c[:5]:
                for d in top_1d[:5]:
                    base = {}
                    base.update(a['params'])
                    base.update(b['params'])
                    base.update(c['params'])
                    base.update(d['params'])
                    base_combos.append(base)

    print(f"基础组合数（5^4={len(base_combos)}")

    # 每个基础组合，在其参数±1步长内微调
    combos = []
    for base in base_combos:
        # 生成每个参数的邻居（±1步长）
        param_variants = {}
        for k, v in base.items():
            if k not in PARAM_RANGES:
                param_variants[k] = [v]
                continue
            rng = PARAM_RANGES[k]
            idx = rng.index(v) if v in rng else -1
            neighbors = []
            if idx >= 0:
                if idx > 0:
                    neighbors.append(rng[idx-1])
                neighbors.append(rng[idx])
                if idx < len(rng)-1:
                    neighbors.append(rng[idx+1])
            else:
                neighbors = [v]
            param_variants[k] = neighbors

        # 只取前6个关键参数做联合搜索（避免组合爆炸）
        key_params = ['ZHANGDIE_THRESH', 'FENGXIAN_THRESH', 'BOLL_TOUCH_RATIO',
                    'PULLBACK_AMOUNT_THRESH_WAN', 'ZHENGT_MA_BELOW', 'ZHENGT_TARGET_DIFF']
        filtered_variants = []
        for k in key_params:
            if k in param_variants:
                filtered_variants.append(param_variants[k])
            else:
                filtered_variants.append([base.get(k, 0)])

        # 生成组合
        for vals in itertools.product(*filtered_variants):
            combo = base.copy()
            for k, v in zip(key_params, vals):
                combo[k] = v
            # 将list值转为tuple（确保可哈希）
            combo_tuple = {}
            for k, v in combo.items():
                if isinstance(v, list):
                    combo_tuple[k] = tuple(v)
                else:
                    combo_tuple[k] = v
            combos.append(tuple(combo_tuple.items()))

    # 去重
    unique_combos = list(set(combos))
    print(f"联合优化组合数: {len(unique_combos):,}")

    t0 = time.time()
    with Pool(processes=n_jobs, initializer=worker_init, initargs=(df, DEFAULT_CONFIG)) as pool:
        results = list(pool.imap_unordered(evaluate_combo, unique_combos, chunksize=50))
    t1 = time.time()

    results = [r for r in results if r is not None]
    print(f"有效组合: {len(results)}, 耗时: {t1-t0:.1f}s")

    results.sort(key=lambda x: x['metrics']['sharpe_ratio'], reverse=True)
    return results

def run_stage_3(df, top_stage2, n_jobs=8):
    """Stage 3: 精细调优 — 基于Stage 2 Top 5，只对关键参数在±1步长内搜索"""
    print("\n" + "="*60)
    print("Stage 3: 精细调优（基于Stage 2 Top 5）")
    print("="*60)

    base_combos = top_stage2[:5]
    print(f"基础组合数: {len(base_combos)}")

    # 只选择关键参数做精细调优（避免组合爆炸）
    key_params = ['ZHANGDIE_THRESH', 'FENGXIAN_THRESH', 'BOLL_TOUCH_RATIO',
                'PULLBACK_AMOUNT_THRESH_WAN', 'ZHENGT_MA_BELOW', 'ZHENGT_TARGET_DIFF',
                'ZHENGT_RISK_THRESH', 'BOLL_MA_ABOVE', 'MACD_BAR_THRESH']

    combos = []
    for base in base_combos:
        base_p = base['params']
        # 只处理关键参数
        param_variants = {}
        for k in key_params:
            if k not in base_p:
                continue
            v = base_p[k]
            if k not in PARAM_RANGES:
                param_variants[k] = [v]
                continue
            rng = PARAM_RANGES[k]
            if not isinstance(v, (int, float)):
                param_variants[k] = [v]
                continue
            idx = rng.index(v) if v in rng else -1
            neighbors = []
            if idx >= 0:
                if idx > 0:
                    neighbors.append(rng[idx-1])
                neighbors.append(rng[idx])
                if idx < len(rng)-1:
                    neighbors.append(rng[idx+1])
            else:
                neighbors = [v]
            param_variants[k] = neighbors

        # 生成组合
        keys = list(param_variants.keys())
        values = [param_variants[k] for k in keys]
        for vals in itertools.product(*values):
            combo = base_p.copy()
            for k, v in zip(keys, vals):
                combo[k] = v
            # 将list值转为tuple（确保可哈希）
            combo_tuple = {}
            for k, v in combo.items():
                if isinstance(v, list):
                    combo_tuple[k] = tuple(v)
                else:
                    combo_tuple[k] = v
            combos.append(tuple(combo_tuple.items()))

    # 去重
    unique_combos = list(set(combos))
    print(f"精细调优组合数: {len(unique_combos):,}")

    t0 = time.time()
    with Pool(processes=n_jobs, initializer=worker_init, initargs=(df, DEFAULT_CONFIG)) as pool:
        results = list(pool.imap_unordered(evaluate_combo, unique_combos, chunksize=50))
    t1 = time.time()

    results = [r for r in results if r is not None]
    print(f"有效组合: {len(results)}, 耗时: {t1-t0:.1f}s")

    results.sort(key=lambda x: x['metrics']['sharpe_ratio'], reverse=True)
    return results

if __name__ == '__main__':
    main()
