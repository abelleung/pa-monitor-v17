"""
人工股感策略参数优化脚本
扫描不同的条件2阈值和评分阈值组合，找到最优设置
"""

import sys
import pandas as pd
import numpy as np
sys.path.insert(0, '.')

from indicators import calc_indicators


def run_backtest_with_params(csv_file, daot_cond2_thresh, daot_score_thresh, zhengt_score_thresh, daot_cooldown=5, zhengt_cooldown=0):
    """
    使用指定参数运行回测，返回各目标差价的赢率

    参数：
    - daot_cond2_thresh: 倒T条件2阈值（风险+涨跌必须>此值）
    - daot_score_thresh: 倒T评分阈值（总分必须>=此值）
    - zhengt_score_thresh: 正T评分阈值
    - daot_cooldown: 倒T冷却期（根数）
    - zhengt_cooldown: 正T冷却期（根数，0=无冷却）
    """
    from manual_strategy_v2 import check_manual_daot_signal_v2, check_manual_zhengT_signal_v2

    df = pd.read_csv(csv_file)
    df = calc_indicators(df)
    df = df.sort_values('时间').reset_index(drop=True)
    df['日期'] = df['时间'].str[:10]

    trade_dates = sorted(df['日期'].unique())

    # 存储信号
    daot_signals = []
    zhengt_signals = []

    # 按日期循环
    for date in trade_dates:
        day_df = df[df['日期'] == date].copy()
        day_df = day_df.sort_values('时间').reset_index(drop=True)

        last_daot_bar = -999
        last_zhengt_bar = -999

        for i in range(len(day_df)):
            row = day_df.iloc[i]
            current_time = str(row['时间'])
            hist_df = day_df.iloc[:i+1].copy()

            # 倒T检查（动态参数）
            if daot_cooldown > 0 and i - last_daot_bar < daot_cooldown:
                pass  # 冷却期
            else:
                triggered, details, score = check_manual_daot_signal_v2(
                    row, hist_df, logger=None, last_signal_bar=last_daot_bar
                )
                # 动态覆盖条件2阈值和评分阈值
                cond2_score = int(float(row.get('涨跌', 0)) + int(float(row.get('风险', 0)))
                if cond2_score > daot_cond2_thresh:  # 动态条件2
                    if score >= daot_score_thresh:  # 动态评分阈值
                        last_daot_bar = i
                        daot_signals.append({
                            'bar': i, 'price': float(row['收盘']), 'time': current_time,
                            'date': date, 'score': score
                        })

            # 正T检查（动态参数）
            if zhengt_cooldown > 0 and i - last_zhengt_bar < zhengt_cooldown:
                pass  # 冷却期
            else:
                triggered, details, score = check_manual_zhengT_signal_v2(
                    row, hist_df, logger=None, last_signal_bar=last_zhengt_bar
                )
                # 动态覆盖条件2阈值和评分阈值
                cond2_score = int(float(row.get('涨跌', 0)) + int(float(row.get('风险', 0)))
                if cond2_score < (10 - daot_cond2_thresh + 10):  # 简化：正T条件2<10
                    if score >= zhengt_score_thresh:  # 动态评分阈值
                        last_zhengt_bar = i
                        zhengt_signals.append({
                            'bar': i, 'price': float(row['收盘']), 'time': current_time,
                            'date': date, 'score': score
                        })

    # 评估（触发后~15:00最大价差）
    targets = [0.2, 0.3, 0.4, 0.5]

    # 倒T赢率
    daot_results = []
    for signal in daot_signals:
        sell_date = signal['date']
        sell_time = signal['time']
        sell_price = signal['price']
        sell_idx = df[df['时间'] == sell_time].index[0]

        window_rows = df[(df['日期'] == sell_date) & (df.index > sell_idx)]
        day_15 = window_rows[window_rows['时间'].apply(
            lambda x: int(str(x)[11:13]) < 15 or (int(str(x)[11:13]) == 15 and int(str(x)[14:16]) == 0)
        )]

        if len(day_15) > 0:
            min_price = day_15['最低'].min()
            max_spread = sell_price - min_price
        else:
            max_spread = 0

        daot_results.append({'spread': max_spread})

    # 正T赢率
    zhengt_results = []
    for signal in zhengt_signals:
        buy_date = signal['date']
        buy_time = signal['time']
        buy_price = signal['price']
        buy_idx = df[df['时间'] == buy_time].index[0]

        window_rows = df[(df['日期'] == buy_date) & (df.index > buy_idx)]
        day_15 = window_rows[window_rows['时间'].apply(
            lambda x: int(str(x)[11:13]) < 15 or (int(str(x)[11:13]) == 15 and int(str(x)[14:16]) == 0)
        )]

        if len(day_15) > 0:
            max_price = day_15['最高'].max()
            max_spread = max_price - buy_price
        else:
            max_spread = 0

        zhengt_results.append({'spread': max_spread})

    # 计算赢率
    daot_win_rates = {}
    for t in targets:
        wins = sum(1 for r in daot_results if r['spread'] >= t)
        rate = wins / len(daot_results) * 100 if daot_results else 0
        daot_win_rates[t] = rate

    zhengt_win_rates = {}
    for t in targets:
        wins = sum(1 for r in zhengt_results if r['spread'] >= t)
        rate = wins / len(zhengt_results) * 100 if zhengt_results else 0
        zhengt_win_rates[t] = rate

    return {
        'daot_count': len(daot_signals),
        'zhengt_count': len(zhengt_signals),
        'daot_win': daot_win_rates,
        'zhengt_win': zhengt_win_rates,
    }


if __name__ == '__main__':
    csv_file = '601318_2026-05_06.csv'

    # 参数组合
    daot_cond2_thresholds = [175, 180, 184, 190, 195]
    daot_score_thresholds = [3, 5, 7, 10]
    zhengt_score_thresholds = [3, 5, 7, 10]

    print('=' * 100)
    print('人工股感策略参数优化扫描')
    print(f'数据：{csv_file}（17个交易日）')
    print('=' * 100)
    print()

    results = []

    # 扫描倒T条件2阈值
    for cond2 in daot_cond2_thresholds:
        for score in daot_score_thresholds:
            result = run_backtest_with_params(csv_file, cond2, score, 5, daot_cooldown=5, zhengt_cooldown=0)
            results.append({
                'cond2': cond2,
                'score_thresh': score,
                'daot_count': result['daot_count'],
                'zhengt_count': result['zhengt_count'],
                'daot_0.2': result['daot_win'][0.2],
                'daot_0.3': result['daot_win'][0.3],
                'daot_0.4': result['daot_win'][0.4],
                'daot_0.5': result['daot_win'][0.5],
            })
            print(f'倒T: cond2>{cond2}, score>={score} → {result["daot_count"]}次, '
                  f'@0.2={result["daot_win"][0.2]:.1f}%, @0.3={result["daot_win"][0.3]:.1f}%')

    # 扫描正T评分阈值
    print()
    print('-' * 100)
    print('正T评分阈值扫描（条件2<10固定）')
    print('-' * 100)

    for score in zhengt_score_thresholds:
        result = run_backtest_with_params(csv_file, 184, 5, score, daot_cooldown=5, zhengt_cooldown=0)
        print(f'正T: score>={score} → {result["zhengt_count"]}次, '
              f'@0.2={result["zhengt_win"][0.2]:.1f}%, @0.3={result["zhengt_win"][0.3]:.1f}%')

    print()
    print('=' * 100)
    print('扫描完成')
    print('=' * 100)
