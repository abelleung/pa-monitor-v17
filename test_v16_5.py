"""
v16.5 四种策略测试脚本
必须与实际代码（strategies.py + pa_monitor.py）保持一致
"""
import sys
sys.path.insert(0, '.')

from pa_monitor import PAMonitor
from strategies import (
    check_momentum_sell_signal,
    check_boll_sell_signal,
    check_pullback_sell_signal,
    check_zhengT_buy_signal,
)
from indicators import STRATEGY_CONFIG
import time

def run_full_test(csv_file='平安1-5月_回测数据_2026.csv', speed=10000):
    monitor = PAMonitor(simulate=True, simulate_csv=csv_file, simulate_speed=speed)

    monitor.running = True
    monitor._reset_daily_stats()
    monitor.signal_count_today = 0
    monitor.sell_active = False
    monitor.last_signal_bar = -31
    monitor.buyback_notified = False
    monitor.sell_stop_loss_triggered = False
    monitor.sell_signal_bar = 0
    monitor.sell_eval_notified = False
    monitor.zhengt_signal_count_today = 0
    monitor.zhengt_buy_active = False
    monitor.zhengt_sell_notified = False
    monitor.last_zhengt_signal_bar = -31
    monitor.zhengt_stop_loss_triggered = False
    monitor.zhengt_signal_bar = 0
    monitor.zhengt_eval_notified = False

    print('=' * 60)
    print('v16.5 四种策略完整测试')
    print('=' * 60)

    counts = {
        '动量策略': 0,
        'BOLL补充': 0,
        '冲高回落': 0,
        '正T买入': 0,
        '正T卖出': 0,
    }
    examples = {
        '动量策略': [],
        'BOLL补充': [],
        '冲高回落': [],
        '正T买入': [],
        '正T卖出': [],
    }

    for i in range(20141):
        df = monitor._get_simulated_bars(count=600)
        if df is None:
            break

        completed = df.iloc[-1]
        total_bars = len(df)
        latest_time = str(completed['时间'])

        if total_bars < 5:
            continue

        # 更新 daily_stats（模拟 run() 主循环）
        current_high = float(completed['最高'])
        current_low = float(completed['最低'])
        if monitor.daily_stats['high_price'] is None:
            monitor.daily_stats['high_price'] = current_high
            monitor.daily_stats['low_price'] = current_low
        else:
            monitor.daily_stats['high_price'] = max(monitor.daily_stats['high_price'], current_high)
            monitor.daily_stats['low_price'] = min(monitor.daily_stats['low_price'], current_low)

        # ===== 倒T信号检查 =====
        # 冷却期检查
        in_cooldown = (total_bars - 1 - monitor.last_signal_bar) < STRATEGY_CONFIG['COOLDOWN_BARS']

        if not in_cooldown:
            # 暴跌保护：日内跌幅>2.0%跳过倒T
            prev_close = monitor.daily_stats.get('prev_close', 0)
            if prev_close > 0 and completed['收盘'] < prev_close:
                day_drop_pct = (prev_close - completed['收盘']) / prev_close * 100
                if day_drop_pct > STRATEGY_CONFIG['CRASH_DAY_DROP_MAX']:
                    monitor.logger.info(f"⚠️ 暴跌保护：日内跌幅{day_drop_pct:.2f}% > {STRATEGY_CONFIG['CRASH_DAY_DROP_MAX']}%，跳过倒T信号")
                    in_cooldown = True  # 跳过本次

            if not in_cooldown:
                # 策略1: 动量
                momentum_triggered, momentum_details = check_momentum_sell_signal(completed, monitor.logger)

                # 策略2: BOLL（动量未触发时检查）
                boll_triggered = False
                boll_details = None
                if not momentum_triggered and not monitor.sell_active:
                    boll_triggered, boll_details = check_boll_sell_signal(
                        completed, monitor.logger, day_high=monitor.daily_stats.get('high_price', 0))

                # 策略3: 冲高回落（前两个都未触发时检查）
                current_bandwidth = float(completed['BOLL带宽'])
                is_low_volatility = current_bandwidth < STRATEGY_CONFIG['PULLBACK_BANDWIDTH_THRESH']

                pullback_triggered = False
                pullback_details = None
                if not momentum_triggered and not boll_triggered and is_low_volatility and not monitor.sell_active:
                    pullback_triggered, pullback_details = check_pullback_sell_signal(
                        df, total_bars - 2, monitor.logger, day_high=monitor.daily_stats['high_price'])

                # 确定触发策略
                triggered = momentum_triggered or boll_triggered or pullback_triggered
                if triggered:
                    if momentum_triggered:
                        strategy = '动量策略'
                        details = momentum_details
                    elif boll_triggered:
                        strategy = 'BOLL补充'
                        details = boll_details
                    else:
                        strategy = '冲高回落'
                        details = pullback_details

                    counts[strategy] += 1
                    if len(examples[strategy]) < 3:
                        examples[strategy].append(f"{latest_time} 收盘={completed['收盘']:.2f}")
                    monitor.sell_active = True
                    monitor.sell_price = completed['收盘']
                    monitor.sell_signal_bar = total_bars - 1
                    monitor.signal_count_today += 1
                    monitor.target_buy_price = completed['收盘'] - STRATEGY_CONFIG['TARGET_DIFF']
                    monitor.stop_loss_price = completed['收盘'] + STRATEGY_CONFIG['STOP_LOSS_DIFF']

        # ===== 正T买入检查 =====
        zhengt_triggered, zhengt_details = monitor._check_zhengt_signals(df, completed, total_bars)
        if zhengt_triggered:
            counts['正T买入'] += 1
            if len(examples['正T买入']) < 3:
                examples['正T买入'].append(f"{latest_time} 收盘={completed['收盘']:.2f}")
            monitor.zhengt_buy_active = True
            monitor.zhengt_buy_price = completed['收盘']
            monitor.zhengt_buy_time = latest_time
            monitor.zhengt_signal_count_today += 1
            monitor.zhengt_target_sell_price = STRATEGY_CONFIG['ZHENGT_TARGET_DIFF']
            monitor.zhengt_stop_loss_price = STRATEGY_CONFIG['ZHENGT_STOP_LOSS_DIFF']
            monitor.zhengt_window_max_price = None

        # 正T卖出追踪
        if monitor.zhengt_buy_active:
            current_price = completed['收盘']
            if not monitor.zhengt_sell_notified and current_price >= monitor.zhengt_target_sell_price:
                counts['正T卖出'] += 1
                monitor.zhengt_sell_notified = True
                monitor.zhengt_buy_active = False
                monitor.last_zhengt_signal_bar = total_bars - 1 - 30
                if len(examples['正T卖出']) < 3:
                    examples['正T卖出'].append(f"{latest_time} 卖出={current_price:.2f}")

        time.sleep(0.001)

    print()
    print('=' * 60)
    print('v16.5 测试结果（94个交易日）:')
    print('=' * 60)
    for strategy, count in counts.items():
        print(f'{strategy}: {count} 次')
        for ex in examples[strategy]:
            print(f'  - {ex}')
        if count > 3 and len(examples[strategy]) >= 3:
            print(f'  ... (共{count}次)')
    print('=' * 60)
    print(f'倒T合计: {counts["动量策略"] + counts["BOLL补充"] + counts["冲高回落"]} 次')
    print(f'正T合计: {counts["正T买入"]} 次买入, {counts["正T卖出"]} 次卖出')
    print('=' * 60)

if __name__ == '__main__':
    run_full_test()
