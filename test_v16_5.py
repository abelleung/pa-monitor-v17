"""
v17.0 四种策略测试脚本（当天15:00收盘评估，遍历多种目标差价）
必须与实际代码（strategies.py + pa_monitor.py）保持一致
"""
import sys
sys.path.insert(0, '.')

from pa_monitor import PAMonitor
from indicators import STRATEGY_CONFIG
import time

# 正T目标差价列表
ZHENGT_TARGETS = [0.20, 0.30, 0.40, 0.50]
# 倒T目标差价列表
DAOT_TARGETS = [0.25, 0.30, 0.35, 0.40]


def run_test_for_targets(csv_file='平安1-5月_回测数据_2026.csv', speed=10000):
    """对每种正T/倒T目标差价跑一遍回测，用15:00最大价差评估"""

    from strategies import check_momentum_sell_signal, check_boll_sell_signal, check_pullback_sell_signal

    # 结果存储
    zhengt_results = {t: {'buy': 0, 'success': 0} for t in ZHENGT_TARGETS}
    daot_results = {t: {'sell': 0, 'success': 0} for t in DAOT_TARGETS}

    # 先找出所有正T买入信号和倒T卖出信号（与目标差价无关）
    monitor = PAMonitor(simulate=True, simulate_csv=csv_file, simulate_speed=speed)
    df = monitor.simulate_df

    zhengt_signals = []  # (bar_index, buy_price, buy_time)
    daot_signals = []    # (bar_index, sell_price, sell_time)

    monitor2 = PAMonitor(simulate=True, simulate_csv=csv_file, simulate_speed=speed)
    monitor2.running = True
    monitor2._reset_daily_stats()
    monitor2.signal_count_today = 0
    monitor2.last_signal_bar = -31
    monitor2.zhengt_signal_count_today = 0
    monitor2.last_zhengt_signal_bar = -31

    for i in range(20141):
        df2 = monitor2._get_simulated_bars(count=600)
        if df2 is None:
            break

        completed = df2.iloc[-1]
        total_bars = len(df2)
        latest_time = str(completed['时间'])

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

        # ===== 倒T信号检查 =====
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
                    boll_triggered, _ = check_boll_sell_signal(
                        completed, monitor2.logger, day_high=monitor2.daily_stats.get('high_price', 0))
                current_bandwidth = float(completed['BOLL带宽'])
                is_low_volatility = current_bandwidth < STRATEGY_CONFIG['PULLBACK_BANDWIDTH_THRESH']
                pullback_triggered = False
                if not momentum_triggered and not boll_triggered and is_low_volatility:
                    pullback_triggered, _ = check_pullback_sell_signal(
                        df2, total_bars - 2, monitor2.logger, day_high=monitor2.daily_stats['high_price'])

                triggered = momentum_triggered or boll_triggered or pullback_triggered
                if triggered:
                    daot_signals.append({
                        'bar': total_bars - 1,
                        'price': completed['收盘'],
                        'time': latest_time,
                    })
                    monitor2.last_signal_bar = total_bars - 1

        # ===== 正T买入检查 =====
        zhengt_triggered, _ = monitor2._check_zhengt_signals(df2, completed, total_bars)
        if zhengt_triggered:
            zhengt_signals.append({
                'bar': total_bars - 1,
                'price': completed['收盘'],
                'time': latest_time,
            })
            monitor2.last_zhengt_signal_bar = total_bars - 1

        time.sleep(0.001)

    # ===== 对每种目标差价，计算15:00最大价差胜率 =====
    # 评估窗口：触发后下一根K线 ~ 当天15:00（不含触发那根K线本身）

    # 正T：最大价差 = 触发后最高价 - 买入价
    for signal in zhengt_signals:
        buy_bar = signal['bar']
        buy_price = signal['price']
        buy_time = signal['time']
        buy_date = buy_time[:10]

        for t in ZHENGT_TARGETS:
            zhengt_results[t]['buy'] += 1
            # 窗口：触发后下一根K线开始
            window_rows = df[(df['时间'].str.startswith(buy_date)) & (df.index > buy_bar)]
            if len(window_rows) == 0:
                continue
            day_15 = window_rows[window_rows['时间'].apply(
                lambda x: int(str(x)[11:13]) < 15 or (int(str(x)[11:13]) == 15 and int(str(x)[14:16]) == 0)
            )]
            if len(day_15) == 0:
                continue
            max_price = day_15['最高'].max()
            max_spread = max_price - buy_price
            if max_spread >= t:
                zhengt_results[t]['success'] += 1

    # 倒T：最大价差 = 卖出价 - 触发后最低价
    for signal in daot_signals:
        sell_bar = signal['bar']
        sell_price = signal['price']
        sell_time = signal['time']
        sell_date = sell_time[:10]

        for t in DAOT_TARGETS:
            daot_results[t]['sell'] += 1
            # 窗口：触发后下一根K线开始
            window_rows = df[(df['时间'].str.startswith(sell_date)) & (df.index > sell_bar)]
            if len(window_rows) == 0:
                continue
            day_15 = window_rows[window_rows['时间'].apply(
                lambda x: int(str(x)[11:13]) < 15 or (int(str(x)[11:13]) == 15 and int(str(x)[14:16]) == 0)
            )]
            if len(day_15) == 0:
                continue
            min_price = day_15['最低'].min()
            max_spread = sell_price - min_price
            if max_spread >= t:
                daot_results[t]['success'] += 1

    # ===== 正T逐笔明细 =====
    print('=' * 90)
    print('正T逐笔明细（19次买入信号）')
    print('=' * 90)
    print(f"{'#':>3s} {'日期':10s} {'买入时间':8s} {'买入价':8s} {'最高价':8s} {'最高价时间':8s} {'最大价差':8s}")
    print('-' * 90)

    zhengt_details = []
    for signal in zhengt_signals:
        buy_date = signal['time'][:10]
        buy_time = signal['time'][11:19]
        buy_price = signal['price']
        buy_bar = signal['bar']
        # 窗口：触发后下一根K线开始
        window_rows = df[(df['时间'].str.startswith(buy_date)) & (df.index > buy_bar)]
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
        zhengt_details.append({
            'buy_date': buy_date,
            'buy_time': buy_time,
            'buy_price': buy_price,
            'max_price': max_price,
            'max_time': max_time,
            'max_spread': max_spread,
        })

    for i, d in enumerate(zhengt_details, 1):
        print(f"{i:>3d} {d['buy_date']} {d['buy_time']} {d['buy_price']:8.2f} {d['max_price']:8.2f} {d['max_time']} {d['max_spread']:8.2f}")

    # ===== 输出结果 =====
    print()
    print('=' * 70)
    print('v17.0 回测结果（94个交易日，当天15:00收盘评估，最大价差）')
    print('=' * 70)

    print()
    print('【正T策略】买入次数 & 最大价差胜率')
    print(f"{'目标差价':12s} {'买入次数':10s} {'成功次数':10s} {'胜率':10s}")
    print('-' * 70)
    for t in ZHENGT_TARGETS:
        r = zhengt_results[t]
        win_rate = r['success'] / r['buy'] * 100 if r['buy'] > 0 else 0
        print(f"{t:12.2f} {r['buy']:10d} {r['success']:10d} {win_rate:9.1f}%")
    print(f"正T总触发次数: {len(zhengt_signals)}")

    print()
    print('【倒T策略】卖出次数 & 最大价差胜率')
    print(f"{'目标差价':12s} {'卖出次数':10s} {'成功次数':10s} {'胜率':10s}")
    print('-' * 70)
    for t in DAOT_TARGETS:
        r = daot_results[t]
        win_rate = r['success'] / r['sell'] * 100 if r['sell'] > 0 else 0
        print(f"{t:12.2f} {r['sell']:10d} {r['success']:10d} {win_rate:9.1f}%")
    print(f"倒T总触发次数: {len(daot_signals)}")

    print('=' * 70)


if __name__ == '__main__':
    run_test_for_targets()
