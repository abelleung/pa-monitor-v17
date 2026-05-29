"""
查看倒T卖出后当天走势（15:00收盘评估）
"""
import sys
sys.path.insert(0, '.')

from pa_monitor import PAMonitor, estimate_daily_amount_and_amplitude
from indicators import STRATEGY_CONFIG
from strategies import check_momentum_sell_signal, check_boll_sell_signal, check_pullback_sell_signal

def analyze_daot_movement(csv_file='平安1-5月_回测数据_2026.csv'):
    monitor = PAMonitor(simulate=True, simulate_csv=csv_file, simulate_speed=10000)
    df = monitor.simulate_df

    sell_signals = []

    # 找出所有倒T卖出信号
    monitor2 = PAMonitor(simulate=True, simulate_csv=csv_file, simulate_speed=10000)
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
                        'time': str(completed['时间']),
                        'target': current_target,
                    })
                    monitor2.last_signal_bar = total_bars - 1

    # 分析卖出后的走势
    print('=' * 70)
    print('倒T卖出后当天走势分析（94个交易日）')
    print('=' * 70)
    print()
    print(f"{'时间':20s} {'卖出价':8s} {'目标买回':8s} {'15:00价':8s} {'差值':8s} {'是否成功':10s}")
    print('-' * 70)

    success_count = 0
    for signal in sell_signals[:20]:  # 只看前20个
        sell_bar = signal['bar']
        sell_price = signal['price']
        sell_time = signal['time']
        target = signal['target']
        target_buy = sell_price - target

        # 找到当天15:00的收盘价
        signal_date = sell_time[:10]
        day_rows = df[df['时间'].str.startswith(signal_date)]
        if len(day_rows) == 0:
            continue

        # 15:00的价格（取最后一根K线）
        close_15 = day_rows.iloc[-1]['收盘']

        # 判断成功：15:00价格 <= 目标买回价
        success = close_15 <= target_buy
        if success:
            success_count += 1

        print(f"{sell_time:20s} {sell_price:8.2f} {target_buy:8.2f} {close_15:8.2f} {close_15 - target_buy:8.2f} {'是' if success else '否':10s}")

    print('-' * 70)
    print(f"前20次：成功{success_count}次，胜率{success_count/20*100:.1f}%")
    print('=' * 70)

if __name__ == '__main__':
    analyze_daot_movement()
