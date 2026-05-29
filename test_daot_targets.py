"""
v16.5 倒T不同价差理论胜率测试
测试四种目标差价：0.25, 0.30, 0.35, 0.40元
统计90分钟窗口内，最低价是否 <= 卖出价-目标差价（理论胜率）
说明：90分钟仅评估，不影响状态；30分钟冷却期自然过期
"""
import sys
sys.path.insert(0, '.')

from pa_monitor import PAMonitor, estimate_daily_amount_and_amplitude
from indicators import STRATEGY_CONFIG
from strategies import check_momentum_sell_signal, check_boll_sell_signal, check_pullback_sell_signal
import time

def test_daot_with_target(csv_file='平安1-5月_回测数据_2026.csv', speed=10000, target_diff=0.25, stop_loss_diff=0.20):
    monitor = PAMonitor(simulate=True, simulate_csv=csv_file, simulate_speed=speed)

    monitor.running = True
    monitor._reset_daily_stats()
    monitor.sell_active = False
    monitor.buyback_notified = False
    monitor.last_signal_bar = -STRATEGY_CONFIG['COOLDOWN_BARS'] - 1
    monitor.sell_stop_loss_triggered = False
    monitor.sell_signal_bar = 0
    monitor.sell_eval_notified = False
    monitor.signal_count_today = 0

    sell_count = 0
    window_success = 0  # 90分钟窗口内，最低价 <= 卖出价-目标差价
    total_profit = 0.0

    for i in range(20141):
        df = monitor._get_simulated_bars(count=600)
        if df is None:
            break

        completed = df.iloc[-1]
        total_bars = len(df)
        latest_time = str(completed['时间'])

        if total_bars < 5:
            continue

        # 更新 daily_stats
        current_high = float(completed['最高'])
        current_low = float(completed['最低'])
        if monitor.daily_stats['high_price'] is None:
            monitor.daily_stats['high_price'] = current_high
            monitor.daily_stats['low_price'] = current_low
        else:
            monitor.daily_stats['high_price'] = max(monitor.daily_stats['high_price'], current_high)
            monitor.daily_stats['low_price'] = min(monitor.daily_stats['low_price'], current_low)

        # 预估全天成交额（用于动态目标差价）
        est = estimate_daily_amount_and_amplitude(df, monitor.daily_stats.get('prev_close', 0), monitor.daily_stats.get('open_price') or 0)
        if est:
            if est['is_extreme_low']:
                current_target = STRATEGY_CONFIG['EXTREME_LOW_TARGET']
            elif est['is_volume_low']:
                current_target = STRATEGY_CONFIG['TARGET_DIFF_LOW_VOLUME']
            else:
                current_target = STRATEGY_CONFIG['TARGET_DIFF_NORMAL']
        else:
            current_target = target_diff

        # ===== 倒T卖出信号检查 =====
        in_cooldown = (total_bars - 1 - monitor.last_signal_bar) < STRATEGY_CONFIG['COOLDOWN_BARS']

        if not in_cooldown:
            # 暴跌保护
            prev_close = monitor.daily_stats.get('prev_close', 0)
            if prev_close > 0 and completed['收盘'] < prev_close:
                day_drop_pct = (prev_close - completed['收盘']) / prev_close * 100
                if day_drop_pct > STRATEGY_CONFIG['CRASH_DAY_DROP_MAX']:
                    in_cooldown = True

            if not in_cooldown:
                # 策略1: 动量
                momentum_triggered, momentum_details = check_momentum_sell_signal(completed, monitor.logger)

                # 策略2: BOLL
                boll_triggered = False
                boll_details = None
                if not momentum_triggered and not monitor.sell_active:
                    boll_triggered, boll_details = check_boll_sell_signal(
                        completed, monitor.logger, day_high=monitor.daily_stats.get('high_price', 0))

                # 策略3: 冲高回落
                current_bandwidth = float(completed['BOLL带宽'])
                is_low_volatility = current_bandwidth < STRATEGY_CONFIG['PULLBACK_BANDWIDTH_THRESH']

                pullback_triggered = False
                pullback_details = None
                if not momentum_triggered and not boll_triggered and is_low_volatility and not monitor.sell_active:
                    pullback_triggered, pullback_details = check_pullback_sell_signal(
                        df, total_bars - 2, monitor.logger, day_high=monitor.daily_stats['high_price'])

                triggered = momentum_triggered or boll_triggered or pullback_triggered
                if triggered:
                    sell_count += 1
                    monitor.sell_active = True
                    monitor.sell_price = completed['收盘']
                    monitor.sell_signal_bar = total_bars - 1
                    monitor.signal_count_today += 1
                    monitor.target_buy_price = round(completed['收盘'] - current_target, 2)
                    monitor.stop_loss_price = round(completed['收盘'] + stop_loss_diff, 2)
                    monitor.sell_eval_notified = False
                    monitor.sell_stop_loss_triggered = False
                    monitor.window_min_price = completed['收盘']

        # 倒T回买追踪 + 90分钟窗口评估
        current_price = completed['收盘']
        # 更新窗口内最低价
        if monitor.sell_signal_bar > 0:
            if monitor.window_min_price is None or current_price < monitor.window_min_price:
                monitor.window_min_price = current_price

        # 到达目标回买价（记录成功，不影响状态）
        if not monitor.buyback_notified and monitor.target_buy_price > 0 and current_price <= monitor.target_buy_price:
            window_success += 1
            profit = monitor.sell_price - current_price
            total_profit += profit
            monitor.buyback_notified = True

        # 止损触发（记录，不影响状态）
        if not monitor.sell_stop_loss_triggered and monitor.stop_loss_price > 0 and current_price > monitor.stop_loss_price:
            monitor.sell_stop_loss_triggered = True

        # 90分钟窗口评估（记录结果，不影响任何状态）
        if monitor.sell_stop_loss_triggered and not monitor.sell_eval_notified and monitor.sell_signal_bar > 0:
            elapsed = total_bars - monitor.sell_signal_bar
            if elapsed >= STRATEGY_CONFIG['EVAL_WINDOW_BARS']:
                monitor.sell_eval_notified = True
                window_min = monitor.window_min_price if monitor.window_min_price is not None else current_price
                # 理论成功：窗口最低价 <= 卖出价 - 目标差价
                theoretical_success = window_min <= monitor.sell_price - current_target
                if theoretical_success:
                    monitor.logger.info(f"倒T90分钟窗口评估：成功（窗口最低{window_min:.2f} <= {monitor.sell_price - current_target:.2f}）")
                else:
                    monitor.logger.info(f"倒T90分钟窗口评估：失败（窗口最低{window_min:.2f} > {monitor.sell_price - current_target:.2f}）")

        time.sleep(0.001)

    # 计算理论胜率（用90分钟窗口内的理论成功）
    # 重新统计：90分钟窗口内最低价 <= 卖出价 - 目标差价
    win_rate = window_success / sell_count * 100 if sell_count > 0 else 0
    avg_profit = total_profit / window_success if window_success > 0 else 0

    return {
        'target': target_diff,
        'sell': sell_count,
        'success': window_success,
        'win_rate': win_rate,
        'avg_profit': avg_profit,
        'total_profit': total_profit,
    }


if __name__ == '__main__':
    targets = [
        (0.25, 0.20),  # v16.5默认
        (0.30, 0.25),  # 正常
        (0.35, 0.30),  # 高目标
        (0.40, 0.35),  # 很高目标
    ]

    print('=' * 60)
    print('倒T不同价差理论胜率测试（94个交易日，90分钟窗口）')
    print('=' * 60)
    print()
    print(f"{'目标差价':12s} {'卖出':6s} {'理论成功':10s} {'胜率':8s} {'均利润':8s}")
    print('-' * 60)

    for target_diff, stop_loss in targets:
        result = test_daot_with_target(target_diff=target_diff, stop_loss_diff=stop_loss)
        print(f"{result['target']:12.2f} {result['sell']:6d} {result['success']:10d} {result['win_rate']:7.1f}% {result['avg_profit']:7.2f}元")

    print('=' * 60)
