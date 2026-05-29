"""
v16.5 正T不同价差胜率测试
测试四种目标差价：0.2, 0.3, 0.4, 0.5元
统计成功交易闭环的胜率
说明：90分钟仅评估，不影响状态；30分钟冷却期自然过期
"""
import sys
sys.path.insert(0, '.')

from pa_monitor import PAMonitor
from indicators import STRATEGY_CONFIG
import time

def test_zhengT_with_target(csv_file='平安1-5月_回测数据_2026.csv', speed=10000, target_diff=0.2, stop_loss_diff=0.15):
    monitor = PAMonitor(simulate=True, simulate_csv=csv_file, simulate_speed=speed)

    monitor.running = True
    monitor._reset_daily_stats()
    monitor.zhengt_buy_active = False
    monitor.zhengt_sell_notified = False
    monitor.last_zhengt_signal_bar = -31
    monitor.zhengt_stop_loss_triggered = False
    monitor.zhengt_signal_bar = 0
    monitor.zhengt_eval_notified = False

    buy_count = 0
    sell_success = 0
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

        # 正T买入检查（仅用 last_zhengt_signal_bar 控制30分钟冷静期）
        zhengt_triggered, zhengt_details = monitor._check_zhengt_signals(df, completed, total_bars)
        if zhengt_triggered:
            buy_count += 1
            monitor.zhengt_buy_price = completed['收盘']
            monitor.zhengt_buy_time = latest_time
            monitor.zhengt_target_sell_price = round(completed['收盘'] + target_diff, 2)
            monitor.zhengt_stop_loss_price = round(completed['收盘'] - stop_loss_diff, 2)
            monitor.zhengt_window_max_price = completed['收盘']
            monitor.zhengt_sell_notified = False
            monitor.zhengt_stop_loss_triggered = False
            monitor.zhengt_signal_bar = total_bars - 1
            monitor.zhengt_eval_notified = False

        # 正T卖出追踪 + 90分钟窗口评估（与 pa_monitor.py 一致）
        # 说明：90分钟仅评估推送，不影响任何状态；30分钟冷却期自然过期
        current_price = completed['收盘']
        # 更新窗口内最高价
        if monitor.zhengt_signal_bar > 0:
            if monitor.zhengt_window_max_price is None or current_price > monitor.zhengt_window_max_price:
                monitor.zhengt_window_max_price = current_price

        # 到达目标卖出价（推送提醒，不影响状态）
        if not monitor.zhengt_sell_notified and monitor.zhengt_target_sell_price > 0 and current_price >= monitor.zhengt_target_sell_price:
            sell_success += 1
            profit = current_price - monitor.zhengt_buy_price
            total_profit += profit
            monitor.zhengt_sell_notified = True

        # 止损触发（推送提醒，不影响状态）
        if not monitor.zhengt_stop_loss_triggered and monitor.zhengt_stop_loss_price > 0 and current_price < monitor.zhengt_stop_loss_price:
            monitor.zhengt_stop_loss_triggered = True

        # 90分钟窗口评估（仅推送结果，不影响任何状态）
        if monitor.zhengt_stop_loss_triggered and not monitor.zhengt_eval_notified and monitor.zhengt_signal_bar > 0:
            elapsed = total_bars - monitor.zhengt_signal_bar
            if elapsed >= STRATEGY_CONFIG['EVAL_WINDOW_BARS']:
                monitor.zhengt_eval_notified = True
                window_max = monitor.zhengt_window_max_price if monitor.zhengt_window_max_price is not None else current_price
                if window_max >= monitor.zhengt_buy_price + 0.20:
                    monitor.logger.info(f"正T90分钟窗口评估：成功（窗口最高{window_max:.2f} >= {monitor.zhengt_buy_price + 0.20:.2f}）")
                else:
                    monitor.logger.info(f"正T90分钟窗口评估：失败（窗口最高{window_max:.2f} < {monitor.zhengt_buy_price + 0.20:.2f}）")

        time.sleep(0.001)

    win_rate = sell_success / buy_count * 100 if buy_count > 0 else 0
    avg_profit = total_profit / sell_success if sell_success > 0 else 0

    return {
        'target': target_diff,
        'buy': buy_count,
        'sell': sell_success,
        'win_rate': win_rate,
        'avg_profit': avg_profit,
        'total_profit': total_profit,
    }


if __name__ == '__main__':
    targets = [
        (0.2, 0.15),  # v16.5默认
        (0.3, 0.20),  # 正常
        (0.4, 0.30),  # 高目标
        (0.5, 0.35),  # 很高目标
    ]

    print('=' * 60)
    print('正T不同价差胜率测试（94个交易日）')
    print('=' * 60)
    print()
    print(f"{'目标差价':12s} {'买入':6s} {'成功卖出':8s} {'胜率':8s} {'均利润':8s}")
    print('-' * 60)

    for target_diff, stop_loss in targets:
        result = test_zhengT_with_target(target_diff=target_diff, stop_loss_diff=stop_loss)
        print(f"{result['target']:12.2f} {result['buy']:6d} {result['sell']:8d} {result['win_rate']:7.1f}% {result['avg_profit']:7.2f}元")

    print('=' * 60)
