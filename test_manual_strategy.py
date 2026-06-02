"""
人工股感策略回测脚本（与实盘一致）
架构参考 test_v17_0.py，使用 manual_strategy_v2.py 中的策略函数
支持任意CSV文件（任意日期范围）

用法：
  python3 test_manual_strategy.py [CSV文件]
  python3 test_manual_strategy.py 601318_2026-06.csv
  python3 test_manual_strategy.py 平安1-5月_回测数据_2026.csv
"""

import sys
import time
import numpy as np
sys.path.insert(0, '.')

from indicators import calc_indicators
from manual_strategy_v2 import check_manual_daot_signal_v2, check_manual_zhengT_signal_v2


def run_manual_backtest(csv_file):
    """
    人工股感策略回测（与实盘一致）
    - 使用 calc_indicators 计算指标（与实盘一致）
    - 使用 check_manual_daot_signal_v2 / check_manual_zhengT_signal_v2（与实盘一致）
    - 支持任意日期范围（通过CSV文件）
    """
    import pandas as pd

    print('=' * 90)
    print(f'人工股感策略回测（与实盘一致）')
    print(f'数据文件: {csv_file}')
    print('=' * 90)

    # 读取CSV并计算指标（与实盘一致）
    print('正在读取数据并计算指标...')
    df = pd.read_csv(csv_file)
    df = calc_indicators(df)
    df = df.sort_values('时间').reset_index(drop=True)
    df['日期'] = df['时间'].str[:10]

    trade_dates = sorted(df['日期'].unique())
    print(f'交易日数: {len(trade_dates)}')
    print(f'总K线数: {len(df)}')
    print()

    # 存储信号
    daot_signals = []
    zhengt_signals = []

    # 按日期循环（与实盘一致：每天独立计算）
    for date in trade_dates:
        day_df = df[df['日期'] == date].copy()
        day_df = day_df.sort_values('时间').reset_index(drop=True)

        print(f'【{date}】共 {len(day_df)} 根K线')

        daot_count = 0
        zhengt_count = 0
        last_daot_bar = -999  # 倒T冷却期跟踪
        last_zhengt_bar = -999  # 正T冷却期跟踪

        # 遍历当天的每一根K线
        for i in range(len(day_df)):
            row = day_df.iloc[i]
            current_time = str(row['时间'])

            # 获取当前及之前的数据（与实盘一致：只用当前及历史数据）
            hist_df = day_df.iloc[:i+1].copy()

            # ===== 倒T信号检查 =====
            triggered, details, score = check_manual_daot_signal_v2(
                row, hist_df,
                logger=None,
                last_signal_bar=last_daot_bar
            )

            if triggered:
                last_daot_bar = i  # 更新冷却期
                daot_count += 1
                daot_signals.append({
                    'bar': i,
                    'price': float(row['收盘']),
                    'time': current_time,
                    'date': date,
                    'score': score,
                    'details': details,
                })
                print(f'  倒T: {current_time}: 价格={float(row["收盘"]):.2f}, 总分={score}')

            # ===== 正T信号检查 =====
            triggered2, details2, score2 = check_manual_zhengT_signal_v2(
                row, hist_df,
                logger=None,
                last_signal_bar=last_zhengt_bar
            )

            if triggered2:
                last_zhengt_bar = i  # 更新冷却期
                zhengt_count += 1
                zhengt_signals.append({
                    'bar': i,
                    'price': float(row['收盘']),
                    'time': current_time,
                    'date': date,
                    'score': score2,
                    'details': details2,
                })
                print(f'  正T: {current_time}: 价格={float(row["收盘"]):.2f}, 总分={score2}')

        print(f'  -> 倒T {daot_count}次, 正T {zhengt_count}次')
        print()

    # ===== 评估：触发后下一根K线 ~ 15:00 最大价差 =====
    print('=' * 90)
    print('信号评估（触发后下一根K线 ~ 15:00 最大价差）')
    print('=' * 90)

    # 倒T评估：卖出价 - 窗口内最低价
    daot_results = []
    for signal in daot_signals:
        sell_bar = signal['bar']
        sell_price = signal['price']
        sell_date = signal['date']
        sell_time = signal['time']

        # 找到该信号在df中的真实index
        sell_idx = df[df['时间'] == sell_time].index[0]

        # 窗口：触发后下一根K线开始 ~ 15:00
        window_rows = df[(df['日期'] == sell_date) & (df.index > sell_idx)]
        day_15 = window_rows[window_rows['时间'].apply(
            lambda x: int(str(x)[11:13]) < 15 or (int(str(x)[11:13]) == 15 and int(str(x)[14:16]) == 0)
        )]

        if len(day_15) > 0:
            min_price = day_15['最低'].min()
            max_spread = sell_price - min_price
            min_row = day_15[day_15['最低'] == min_price]
            min_time = str(min_row.iloc[-1]['时间'])[11:19] if len(min_row) > 0 else 'N/A'
        else:
            min_price = sell_price
            max_spread = 0
            min_time = 'N/A'

        daot_results.append({
            'sell_date': sell_date,
            'sell_time': sell_time[11:19],
            'sell_price': sell_price,
            'min_price': min_price,
            'min_time': min_time,
            'max_spread': max_spread,
            'score': signal['score'],
        })

    # 正T评估：窗口内最高价 - 买入价
    zhengt_results = []
    for signal in zhengt_signals:
        buy_bar = signal['bar']
        buy_price = signal['price']
        buy_date = signal['date']
        buy_time = signal['time']

        buy_idx = df[df['时间'] == buy_time].index[0]

        window_rows = df[(df['日期'] == buy_date) & (df.index > buy_idx)]
        day_15 = window_rows[window_rows['时间'].apply(
            lambda x: int(str(x)[11:13]) < 15 or (int(str(x)[11:13]) == 15 and int(str(x)[14:16]) == 0)
        )]

        if len(day_15) > 0:
            max_price = day_15['最高'].max()
            max_spread = max_price - buy_price
            max_row = day_15[day_15['最高'] == max_price]
            max_time = str(max_row.iloc[-1]['时间'])[11:19] if len(max_row) > 0 else 'N/A'
        else:
            max_price = buy_price
            max_spread = 0
            max_time = 'N/A'

        zhengt_results.append({
            'buy_date': buy_date,
            'buy_time': buy_time[11:19],
            'buy_price': buy_price,
            'max_price': max_price,
            'max_time': max_time,
            'max_spread': max_spread,
            'score': signal['score'],
        })

    # ===== 输出明细 =====
    print()
    print('【倒T逐笔明细】')
    print(f'{"#":>3s} {"卖出时间":8s} {"卖出价":8s} {"最低价":8s} {"最低价时间":8s} {"最大价差":8s} {"总分":4s}')
    print('-' * 90)
    for i, r in enumerate(daot_results, 1):
        print(f'{i:>3d} {r["sell_time"]} {r["sell_price"]:8.2f} {r["min_price"]:8.2f} {r["min_time"]} {r["max_spread"]:8.2f} {r["score"]:4d}')

    print()
    print('【正T逐笔明细】')
    print(f'{"#":>3s} {"买入时间":8s} {"买入价":8s} {"最高价":8s} {"最高价时间":8s} {"最大价差":8s} {"总分":4s}')
    print('-' * 90)
    for i, r in enumerate(zhengt_results, 1):
        print(f'{i:>3d} {r["buy_time"]} {r["buy_price"]:8.2f} {r["max_price"]:8.2f} {r["max_time"]} {r["max_spread"]:8.2f} {r["score"]:4d}')

    # ===== 胜率统计（不同目标差价）=====
    print()
    print('=' * 70)
    print('胜率统计（触发后至15:00最大价差）')
    print('=' * 70)

    # 倒T胜率
    daot_targets = [0.2, 0.3, 0.4, 0.5]
    print()
    print('【倒T策略】卖出次数 & 最大价差胜率')
    print(f'{"目标差价":12s} {"卖出次数":10s} {"成功次数":10s} {"胜率":10s} {"均价差":10s}')
    print('-' * 70)
    for t in daot_targets:
        sells = len(daot_results)
        success = sum(1 for r in daot_results if r['max_spread'] >= t)
        win_rate = success / sells * 100 if sells > 0 else 0
        avg_spread = np.mean([r['max_spread'] for r in daot_results]) if daot_results else 0
        print(f'{t:12.2f} {sells:10d} {success:10d} {win_rate:9.1f}% {avg_spread:9.2f}')

    # 正T胜率
    zhengt_targets = [0.2, 0.3, 0.4, 0.5]
    print()
    print('【正T策略】买入次数 & 最大价差胜率')
    print(f'{"目标差价":12s} {"买入次数":10s} {"成功次数":10s} {"胜率":10s} {"均价差":10s}')
    print('-' * 70)
    for t in zhengt_targets:
        buys = len(zhengt_results)
        success = sum(1 for r in zhengt_results if r['max_spread'] >= t)
        win_rate = success / buys * 100 if buys > 0 else 0
        avg_spread = np.mean([r['max_spread'] for r in zhengt_results]) if zhengt_results else 0
        print(f'{t:12.2f} {buys:10d} {success:10d} {win_rate:9.1f}% {avg_spread:9.2f}')

    # ===== 汇总 =====
    print()
    print('=' * 70)
    print(f'汇总：{len(trade_dates)}个交易日，倒T {len(daot_signals)}次，正T {len(zhengt_signals)}次')
    print('=' * 70)


if __name__ == '__main__':
    if len(sys.argv) > 1:
        csv_file = sys.argv[1]
    else:
        csv_file = '601318_2026-06.csv'  # 默认6月数据

    run_manual_backtest(csv_file)
