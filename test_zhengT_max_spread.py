"""
v16.5 正T不同价差胜率测试（15:00收盘评估，用最大价差）
测试四种目标差价：0.2, 0.3, 0.4, 0.5元
统计当天15:00前，最高价 - 买入价 >= 目标差价（理论胜率）
说明：评估在当天15:00收盘时进行，不跨天
"""
import sys
sys.path.insert(0, '.')

from pa_monitor import PAMonitor
from indicators import STRATEGY_CONFIG
import time

def test_zhengT_with_target(csv_file='平安1-5月_回测数据_2026.csv', speed=10000, target_diff=0.2, stop_loss_diff=0.15):
    monitor = PAMonitor(simulate=True, simulate_csv=csv_file, simulate_speed=speed)
    df = monitor.simulate_df

    targets = [0.2, 0.3, 0.4, 0.5]
    results = {t: {'buy': 0, 'success': 0} for t in targets}

    buy_signals = []  # (bar_index, buy_price, buy_time)

    # 找出所有正T买入信号
    monitor2 = PAMonitor(simulate=True, simulate_csv=csv_file, simulate_speed=speed)
    monitor2.running = True
    monitor2._reset_daily_stats()
    monitor2.last_zhengt_signal_bar = -31

    for i in range(20141):
        df2 = monitor2._get_simulated_bars(count=600)
        if df2 is None:
            break

        completed = df2.iloc[-1]
        total_bars = len(df2)

        if total_bars < 5:
            continue

        # 更新 daily_stats
        current_high = float(completed['最高'])
        current_low = float(completed['最低'])
        if monitor2.daily_stats['high_price'] is None:
            monitor2.daily_stats['high_price'] = current_high
            monitor2.daily_stats['low_price'] = current_low
        else:
            monitor2.daily_stats['high_price'] = max(monitor2.daily_stats['high_price'], current_high)
            monitor2.daily_stats['low_price'] = min(monitor2.daily_stats['low_price'], current_low)

        # 检查正T信号
        zhengt_triggered, _ = monitor2._check_zhengt_signals(df2, completed, total_bars)
        if zhengt_triggered:
            buy_signals.append({
                'bar': total_bars - 1,
                'price': completed['收盘'],
                'time': str(completed['时间']),
            })
            monitor2.last_zhengt_signal_bar = total_bars - 1

    # 对每个买入信号，计算当天15:00前的最大价差
    for signal in buy_signals:
        buy_bar = signal['bar']
        buy_price = signal['price']
        buy_time = signal['time']
        buy_date = buy_time[:10]

        for t in targets:
            results[t]['buy'] += 1
            # 找到当天15:00前的数据
            day_rows = df[df['时间'].str.startswith(buy_date)]
            if len(day_rows) == 0:
                continue
            # 只取到15:00的数据
            day_15 = day_rows[day_rows['时间'].apply(
                lambda x: int(str(x)[11:13]) < 15 or (int(str(x)[11:13]) == 15 and int(str(x)[14:16]) == 0)
            )]
            if len(day_15) == 0:
                continue
            max_price = day_15['最高'].max()
            max_spread = max_price - buy_price  # 正T最大价差 = 最高 - 买入价
            if max_spread >= t:
                results[t]['success'] += 1

    print('=' * 70)
    print('正T不同价差理论胜率测试（94个交易日，当天15:00前最大价差）')
    print('=' * 70)
    print()
    print(f"{'目标差价':12s} {'买入次数':10s} {'理论成功':10s} {'胜率':10s} {'均最大价差':12s}")
    print('-' * 70)
    for t in targets:
        r = results[t]
        win_rate = r['success'] / r['buy'] * 100 if r['buy'] > 0 else 0
        print(f"{t:12.2f} {r['buy']:10d} {r['success']:10d} {win_rate:9.1f}%")
    print('=' * 70)


if __name__ == '__main__':
    test_zhengT_with_target()
