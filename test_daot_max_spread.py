"""
v16.5 倒T不同价差胜率测试（15:00收盘评估，用最大价差）
测试四种目标差价：0.25, 0.30, 0.35, 0.40元
统计当天15:00前，卖出价 - 最低价 >= 目标差价（理论胜率）
说明：评估在当天15:00收盘时进行，不跨天
"""
import sys
sys.path.insert(0, '.')

from pa_monitor import PAMonitor, estimate_daily_amount_and_amplitude
from indicators import STRATEGY_CONFIG
from strategies import check_momentum_sell_signal, check_boll_sell_signal, check_pullback_sell_signal

def test_daot_max_spread(csv_file='平安1-5月_回测数据_2026.csv', speed=10000):
    monitor = PAMonitor(simulate=True, simulate_csv=csv_file, simulate_speed=speed)
    df = monitor.simulate_df

    targets = [0.25, 0.30, 0.35, 0.40]
    results = {t: {'sell': 0, 'success': 0} for t in targets}

    sell_signals = []  # (bar_index, sell_price, target)

    # 找出所有倒T卖出信号
    monitor2 = PAMonitor(simulate=True, simulate_csv=csv_file, simulate_speed=speed)
    monitor2.running = True
    monitor2._reset_daily_stats()
    monitor2.last_signal_bar = -STRATEGY_CONFIG['COOLDOWN_BARS'] - 1

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

        # 预估量能
        est = estimate_daily_amount_and_amplitude(df2, monitor2.daily_stats.get('prev_close', 0), monitor2.daily_stats.get('open_price') or 0)
        if est:
            if est['is_extreme_low']:
                current_target = STRATEGY_CONFIG['EXTREME_LOW_TARGET']
            elif est['is_volume_low']:
                current_target = STRATEGY_CONFIG['TARGET_DIFF_LOW_VOLUME']
            else:
                current_target = STRATEGY_CONFIG['TARGET_DIFF_NORMAL']
        else:
            current_target = 0.25

        # 检查倒T信号
        in_cooldown = (total_bars - 1 - monitor2.last_signal_bar) < STRATEGY_CONFIG['COOLDOWN_BARS']

        if not in_cooldown:
            prev_close = monitor2.daily_stats.get('prev_close', 0)
            if prev_close > 0 and completed['收盘'] < prev_close:
                day_drop_pct = (prev_close - completed['收盘']) / prev_close * 100
                if day_drop_pct > STRATEGY_CONFIG['CRASH_DAY_DROP_MAX']:
                    in_cooldown = True

            if not in_cooldown:
                momentum_triggered, _ = check_momentum_sell_signal(completed, monitor2.logger)
                boll_triggered = False
                if not momentum_triggered:
                    boll_triggered, _ = check_boll_sell_signal(completed, monitor2.logger, day_high=monitor2.daily_stats.get('high_price', 0))
                current_bandwidth = float(completed['BOLL带宽'])
                is_low_volatility = current_bandwidth < STRATEGY_CONFIG['PULLBACK_BANDWIDTH_THRESH']
                pullback_triggered = False
                if not momentum_triggered and not boll_triggered and is_low_volatility:
                    pullback_triggered, _ = check_pullback_sell_signal(df2, total_bars - 2, monitor2.logger, day_high=monitor2.daily_stats['high_price'])

                triggered = momentum_triggered or boll_triggered or pullback_triggered
                if triggered:
                    sell_signals.append({
                        'bar': total_bars - 1,
                        'price': completed['收盘'],
                        'target': current_target,
                    })
                    monitor2.last_signal_bar = total_bars - 1

    # 对每个卖出信号，计算当天15:00前的最大价差
    for signal in sell_signals:
        sell_bar = signal['bar']
        sell_price = signal['price']
        sell_time = signal['time'] if 'time' in signal else None
        if sell_bar < len(df):
            sell_date = str(df.iloc[sell_bar]['时间'])[:10]
        else:
            sell_date = None

        for t in targets:
            results[t]['sell'] += 1
            if not sell_date:
                continue
            # 找到当天15:00前的数据
            day_rows = df[df['时间'].str.startswith(sell_date)]
            if len(day_rows) == 0:
                continue
            # 只取到15:00的数据
            day_15 = day_rows[day_rows['时间'].apply(
                lambda x: int(str(x)[11:13]) < 15 or (int(str(x)[11:13]) == 15 and int(str(x)[14:16]) == 0)
            )]
            if len(day_15) == 0:
                continue
            min_price = day_15['最低'].min()
            max_spread = sell_price - min_price  # 倒T最大价差 = 卖出价 - 最低价
            if max_spread >= t:
                results[t]['success'] += 1

    print('=' * 70)
    print('倒T不同价差理论胜率测试（94个交易日，当天15:00前最大价差）')
    print('=' * 70)
    print()
    print(f"{'目标差价':12s} {'卖出次数':10s} {'理论成功':10s} {'胜率':10s} {'均最大价差':12s}")
    print('-' * 70)
    for t in targets:
        r = results[t]
        win_rate = r['success'] / r['sell'] * 100 if r['sell'] > 0 else 0
        print(f"{t:12.2f} {r['sell']:10d} {r['success']:10d} {win_rate:9.1f}%")
    print('=' * 70)


if __name__ == '__main__':
    test_daot_max_spread()
