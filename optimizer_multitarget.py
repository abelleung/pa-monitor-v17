"""
多目标差价优化器 — 中国平安A股盯盘系统 v16.5

针对不同的目标差价（0.2/0.3/0.4/0.5元），分别优化策略参数，
使得各目标差价下的赢率都 >60%（0.2元要求 >70%）。

用法:
    python optimizer_multitarget.py --target 0.2 --type zhengT --n-jobs 8
    python optimizer_multitarget.py --target 0.5 --type zhengT --n-jobs 8
    python optimizer_multitarget.py --target 0.2 --type daot --n-jobs 8
    python optimizer_multitarget.py --target 0.5 --type daot --n-jobs 8
    python optimizer_multitarget.py --all --n-jobs 8  # 全部跑
"""

import sys, os, json, time, itertools
import numpy as np
import pandas as pd
from multiprocessing import Pool
from functools import partial

sys.path.insert(0, '.')
from indicators import STRATEGY_CONFIG, calc_indicators, safe_float, get_time_tuple
import strategies as strat

# ============================================================
# 参数搜索范围
# ============================================================

# 正T策略参数范围（买入）
ZHENGT_PARAM_RANGES = {
    'ZHENGT_MA_BELOW': [0.35, 0.45, 0.55, 0.65, 0.75, 0.85],
    'ZHENGT_RISK_THRESH': [5, 8, 10, 12, 15, 18, 20],
    'ZHENGT_AMOUNT_THRESH_WAN': [3000, 4000, 5000, 6000, 7000, 8000],
    'ZHENGT_ZD_THRESH': [-3, -2, -1, 0],
    'ZHENGT_MIN_AMPLITUDE': [0.3, 0.4, 0.5, 0.6, 0.7, 0.8],
    'ZHENGT_MIN_BOLL_WIDTH': [0.05, 0.10, 0.15, 0.20, 0.30],
    'ZHENGT_TARGET_DIFF': [0.15, 0.20, 0.25, 0.30, 0.35, 0.40, 0.45, 0.50],
    'ZHENGT_STOP_LOSS_DIFF': [0.10, 0.15, 0.20, 0.25, 0.30],
}

# 倒T策略参数范围（卖出）
DAOT_PARAM_RANGES = {
    'ZHANGDIE_THRESH': [60, 80, 100, 120, 140],
    'FENGXIAN_THRESH': [70, 80, 90, 100, 110, 120],
    'AMOUNT_THRESH_WAN': [2000, 2500, 3000, 3500, 4000],
    'MA_ABOVE': [0.05, 0.10, 0.15, 0.20, 0.25],
    'MACD_BAR_THRESH': [0.02, 0.04, 0.06, 0.08, 0.10],
    'BOLL_AMOUNT_THRESH_WAN': [2000, 2500, 3000, 3500, 4000],
    'BOLL_MA_ABOVE': [0.05, 0.10, 0.15, 0.20],
    'BOLL_MACD_THRESH': [0.02, 0.04, 0.06, 0.08],
    'BOLL_DEVIATION_THRESH': [0.2, 0.3, 0.4, 0.5],
    'BOLL_TOUCH_RATIO': [0.985, 0.990, 0.995, 1.0],
    'BOLL_DAY_GAIN_MAX': [1.5, 2.0, 2.5, 3.0],
    'BOLL_PULLBACK_FROM_HIGH': [0.05, 0.10, 0.15, 0.20],
    'PULLBACK_AMOUNT_THRESH_WAN': [2000, 3000, 4000, 5000],
    'PULLBACK_DAY_HIGH_DEVIATION': [0.10, 0.15, 0.20, 0.25, 0.30],
    'PULLBACK_PULLBACK_FROM_HIGH': [0.05, 0.10, 0.15, 0.20],
    'PULLBACK_CLOSE_ABOVE_AVG': [0.10, 0.15, 0.20, 0.25, 0.30],
    'PULLBACK_BANDWIDTH_THRESH': [0.5, 1.0, 1.5, 2.0],
}

DEFAULT_CONFIG = STRATEGY_CONFIG.copy()

# ============================================================
# 数据加载
# ============================================================

def load_and_prepare_data(csv_file='平安1-5月_回测数据_2026.csv'):
    print(f"加载数据: {csv_file}")
    df = pd.read_csv(csv_file, encoding='utf-8-sig')
    for col in ['开盘', '最高', '最低', '收盘', '成交量', '成交额']:
        df[col] = pd.to_numeric(df[col], errors='coerce')
    df = df.dropna(subset=['收盘', '最高', '最低'])
    print(f"  清洗后行数: {len(df)}")
    df = calc_indicators(df)
    print(f"  指标计算完成")
    df['date'] = df['时间'].str[:10]
    df['hour'] = pd.to_numeric(df['时间'].str[11:13], errors='coerce').fillna(0).astype(int)
    df['minute'] = pd.to_numeric(df['时间'].str[14:16], errors='coerce').fillna(0).astype(int)
    df = df[df['hour'] > 0].copy()
    df = df.reset_index(drop=True)
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
    print(f"  交易日数: {len(dates)}, 范围: {dates[0]} ~ {dates[-1]}")
    return df

# ============================================================
# 交易模拟（指定目标差价）
# ============================================================

def simulate_with_target(df, config, target_diff, trade_type):
    """
    对给定参数和目标差价运行交易模拟。
    trade_type: 'zhengT' 或 'daot'
    返回: (trades_list, daily_pnl_dict, win_rate, total_trades)
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
        pos = None
        last_bar = -999
        open_price = float(day_df.iloc[0]['开盘'])
        prev_close = open_price
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

            if high > day_high:
                day_high = high

            # 检查持仓平仓
            if pos is not None:
                if trade_type == 'zhengT':
                    if high >= pos['price'] + target_diff:
                        pnl = target_diff
                        day_pnl += pnl
                        trades.append({'type': 'zhengT', 'pnl': pnl, 'date': date, 'target': target_diff})
                        pos = None
                    elif low <= pos['price'] - pos['stop_loss_diff']:
                        pnl = -pos['stop_loss_diff']
                        day_pnl += pnl
                        trades.append({'type': 'zhengT', 'pnl': pnl, 'date': date, 'target': target_diff})
                        pos = None
                else:
                    if low <= pos['price'] - target_diff:
                        pnl = target_diff
                        day_pnl += pnl
                        trades.append({'type': 'daot', 'pnl': pnl, 'date': date, 'target': target_diff})
                        pos = None
                    elif high >= pos['price'] + pos['stop_loss_diff']:
                        pnl = -pos['stop_loss_diff']
                        day_pnl += pnl
                        trades.append({'type': 'daot', 'pnl': pnl, 'date': date, 'target': target_diff})
                        pos = None

                # 15:00强制平仓
                if pos is not None and i == n_bars - 1:
                    if trade_type == 'zhengT':
                        max_gain = day_high - pos['price']
                    else:
                        max_gain = pos['price'] - day_low
                    pnl = max_gain
                    day_pnl += pnl
                    trades.append({'type': trade_type, 'pnl': pnl, 'date': date, 'target': target_diff})
                    pos = None

            # 检查新信号
            if pos is None and (bar_idx - last_bar) >= config['COOLDOWN_BARS']:
                if trade_type == 'zhengT':
                    price_diff_avg = avg_price - price
                    amplitude = day_high - day_low

                    cond1 = price_diff_avg > config['ZHENGT_MA_BELOW']
                    cond2 = fengxian < config['ZHENGT_RISK_THRESH']
                    cond3 = amount_wan >= config['ZHENGT_AMOUNT_THRESH_WAN']
                    cond4 = zhangdie <= config['ZHENGT_ZD_THRESH']
                    cond5 = amplitude >= config['ZHENGT_MIN_AMPLITUDE']
                    cond6 = boll_width > config['ZHENGT_MIN_BOLL_WIDTH']

                    if cond1 and cond2 and cond3 and cond4 and cond5 and cond6:
                        pos = {
                            'bar': bar_idx,
                            'price': price,
                            'time': str(row['时间']),
                            'target_diff': target_diff,
                            'stop_loss_diff': config['ZHENGT_STOP_LOSS_DIFF'],
                        }
                        last_bar = bar_idx
                else:
                    crash_protected = False
                    if prev_close > 0 and price < prev_close:
                        day_drop = (prev_close - price) / prev_close * 100
                        if day_drop > config['CRASH_DAY_DROP_MAX']:
                            crash_protected = True

                    if not crash_protected:
                        mom_triggered = False
                        if config['ZHANGDIE_THRESH'] > 0:
                            cond1 = zhangdie > config['ZHANGDIE_THRESH']
                            cond2 = fengxian > config['FENGXIAN_THRESH']
                            cond3 = amount_wan >= config['AMOUNT_THRESH_WAN']
                            cond4 = (price - avg_price) > config['MA_ABOVE']
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
                            pos = {
                                'bar': bar_idx,
                                'price': price,
                                'time': str(row['时间']),
                                'target_diff': target_diff,
                                'stop_loss_diff': config['STOP_LOSS_DIFF'],
                            }
                            last_bar = bar_idx

        if day_pnl != 0:
            daily_pnl[date] = day_pnl

    # 计算赢率
    if trades:
        wins = sum(1 for t in trades if t['pnl'] > 0)
        win_rate = wins / len(trades) * 100
    else:
        win_rate = 0.0

    return trades, daily_pnl, win_rate, len(trades)

# ============================================================
# 评估函数
# ============================================================

def evaluate_combo_for_target(combo_tuple, df, target_diff, trade_type):
    """评估单个参数组合在指定目标差价下的表现"""
    try:
        combo = dict(combo_tuple)
        config = DEFAULT_CONFIG.copy()
        config.update(combo)

        trades, daily_pnl, win_rate, total_trades = simulate_with_target(
            df, config, target_diff, trade_type
        )

        if total_trades < 10:
            return None

        return {
            'params': combo,
            'win_rate': win_rate,
            'total_trades': total_trades,
            'target_diff': target_diff,
            'trade_type': trade_type,
        }
    except Exception as e:
        return None

# ============================================================
# 主优化函数
# ============================================================

def optimize_for_target(df, target_diff, trade_type, n_jobs=8):
    """针对特定目标差价和交易类型做优化"""
    print("\n" + "="*60)
    print(f"优化目标: {'正T' if trade_type=='zhengT' else '倒T'} @ {target_diff}元")
    print("="*60)

    param_ranges = ZHENGT_PARAM_RANGES if trade_type == 'zhengT' else DAOT_PARAM_RANGES

    # 生成所有组合
    keys = list(param_ranges.keys())
    values = [param_ranges[k] for k in keys]
    combos = []
    for vals in itertools.product(*values):
        combo = dict(zip(keys, vals))
        combo_tuple = tuple(combo.items())
        combos.append(combo_tuple)

    print(f"总组合数: {len(combos):,}")

    t0 = time.time()
    with Pool(processes=n_jobs) as pool:
        results = list(pool.imap_unordered(
            partial(evaluate_combo_for_target, df=df, target_diff=target_diff, trade_type=trade_type),
            combos,
            chunksize=50
        ))
    t1 = time.time()

    results = [r for r in results if r is not None]
    results.sort(key=lambda x: (x['win_rate'], x['total_trades']), reverse=True)

    print(f"有效组合: {len(results)}, 耗时: {t1-t0:.1f}s")
    print(f"\nTop 10 (赢率 >60%):")
    print(f"{'Rank':<6}{'Win%':<10}{'Trades':<10}{'Target':<10}")
    print("-"*46)
    for i, r in enumerate(results[:10]):
        if r['win_rate'] >= 60:
            print(f"{i+1:<6}{r['win_rate']:<10.1f}{r['total_trades']:<10}{r['target_diff']:<10.2f}")

    return results

# ============================================================
# 主入口
# ============================================================

if __name__ == '__main__':
    import argparse
    parser = argparse.ArgumentParser(description='多目标差价优化器')
    parser.add_argument('--target', type=float, choices=[0.2, 0.3, 0.4, 0.5], help='目标差价')
    parser.add_argument('--type', type=str, choices=['zhengT', 'daot'], help='交易类型')
    parser.add_argument('--all', action='store_true', help='运行全部优化')
    parser.add_argument('--n-jobs', type=int, default=8, help='并行进程数')
    args = parser.parse_args()

    df = load_and_prepare_data()

    targets = [0.2, 0.3, 0.4, 0.5]
    types = ['zhengT', 'daot']

    if args.all:
        for target in targets:
            for ttype in types:
                results = optimize_for_target(df, target, ttype, args.n_jobs)
                with open(f'opt_target_{ttype}_{target:.1f}.json', 'w', encoding='utf-8') as f:
                    json.dump(results[:20], f, indent=2, ensure_ascii=False)
                print(f"✅ 结果已保存: opt_target_{ttype}_{target:.1f}.json")
    elif args.target and args.type:
        results = optimize_for_target(df, args.target, args.type, args.n_jobs)
        with open(f'opt_target_{args.type}_{args.target:.1f}.json', 'w', encoding='utf-8') as f:
            json.dump(results[:20], f, indent=2, ensure_ascii=False)
        print(f"\n✅ 结果已保存: opt_target_{args.type}_{args.target:.1f}.json")
    else:
        print("请指定 --target 和 --type，或使用 --all 运行全部")
        print("示例:")
        print("  python optimizer_multitarget.py --target 0.5 --type zhengT --n-jobs 8")
        print("  python optimizer_multitarget.py --all --n-jobs 8")
