"""
v16.5 倒T不同价差理论胜率测试（简化版）
直接统计：卖出后90分钟内，最低价是否 <= 卖出价 - 目标差价
"""
import sys
sys.path.insert(0, '.')

from pa_monitor import PAMonitor, estimate_daily_amount_and_amplitude
from indicators import STRATEGY_CONFIG
from strategies import check_momentum_sell_signal, check_boll_sell_signal, check_pullback_sell_signal

def test_daot_theoretical(csv_file='平安1-5月_回测数据_2026.csv', speed=10000):
    monitor = PAMonitor(simulate=True, simulate_csv=csv_file, simulate_speed=speed)
    df = monitor.simulate_df

    targets = [0.25, 0.30, 0.35, 0.40]
    results = {t: {'sell': 0, 'success': 0} for t in targets}

    sell_signals = []  # 记录每次卖出：(bar_index, sell_price, current_target)

    # 第一遍：找出所有倒T卖出信号
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

    # 第二遍：对每次卖出，检查90分钟内最低价
    for signal in sell_signals:
        sell_bar = signal['bar']
        sell_price = signal['price']
        for t in targets:
            results[t]['sell'] += 1
            # 检查90分钟内最低价
            start_bar = sell_bar + 1
            end_bar = sell_bar + 90
            if end_bar > len(df):
                end_bar = len(df)
            if start_bar >= end_bar:
                continue
            window = df.iloc[start_bar:end_bar]
            window_min = window['最低'].min()
            if window_min <= sell_price - t:
                results[t]['success'] += 1

    print('=' * 70)
    print('倒T不同价差理论胜率测试（94个交易日，90分钟窗口内最低价）')
    print('=' * 70)
    print()
    print(f"{'目标差价':12s} {'卖出次数':10s} {'理论成功':10s} {'胜率':10s} {'均最低价':10s}")
    print('-' * 70)
    for t in targets:
        r = results[t]
        win_rate = r['success'] / r['sell'] * 100 if r['sell'] > 0 else 0
        print(f"{t:12.2f} {r['sell']:10d} {r['success']:10d} {win_rate:9.1f}%")
    print('=' * 70)

if __name__ == '__main__':
    test_daot_theoretical()
