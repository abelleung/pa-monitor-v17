"""
策略判断函数（从 pa_monitor.py 解耦）
包含：BOLL上轨、动量、冲高回落、正T买入 四个策略
"""
import numpy as np
from indicators import safe_float, get_time_tuple, STRATEGY_CONFIG


def check_boll_sell_signal(row, logger):
    """
    【v14.0补充策略】BOLL上轨倒T卖出信号（去掉带宽条件）

    v14.0改动：移除BOLL带宽条件（59天穷举证明1分钟线上带宽无筛选价值）
    条件（全部满足才触发）：
    1. 最高价 ≥ BOLL上轨 × 0.995（触碰上轨）
    2. 成交额 ≥ 3000万
    3. 收盘价 > 日均价 + 0.1元
    4. 偏离日均价 > 0.3元
    5. MACD柱 > 0.06

    返回: (是否触发, 详情dict)
    """
    price = safe_float(row['收盘'])
    high = safe_float(row['最高'])
    amount_wan = safe_float(row.get('成交额_万'), 0)
    avg_price = safe_float(row['日均价'])
    macd_bar = safe_float(row['MACD柱'])
    boll_upper = safe_float(row['BOLL上轨'])
    boll_width = safe_float(row['BOLL带宽'])

    price_diff = price - avg_price  # 偏离日均价

    details = {
        '时间': str(row['时间']),
        '价格': round(price, 2),
        '最高': round(high, 2),
        '成交额万': round(amount_wan, 0),
        '日均价': round(avg_price, 2),
        '股价差': round(price_diff, 3),
        'MACD柱': round(macd_bar, 4),
        'BOLL上轨': round(boll_upper, 3),
        'BOLL带宽': round(boll_width, 2),
    }

    # BOLL v14.0 卖出条件（5条件，移除带宽）
    cond1 = high >= boll_upper * STRATEGY_CONFIG['BOLL_TOUCH_RATIO']  # 触碰BOLL上轨
    cond2 = amount_wan >= STRATEGY_CONFIG['BOLL_AMOUNT_THRESH_WAN']    # 成交额≥3000万
    cond3 = price_diff > STRATEGY_CONFIG['BOLL_MA_ABOVE']              # 股价>日均价+0.1
    cond4 = price_diff > STRATEGY_CONFIG['BOLL_DEVIATION_THRESH']      # 偏离日均价>0.3元
    cond5 = macd_bar > STRATEGY_CONFIG['BOLL_MACD_THRESH']             # MACD柱>0.06

    details['满足条件'] = {
        '触碰上轨': cond1,
        '成交额≥3000万': cond2,
        '股价>均价+0.1': cond3,
        '偏离均价>0.3': cond4,
        'MACD柱>0.06': cond5,
    }
    details['全部满足'] = all([cond1, cond2, cond3, cond4, cond5])

    return details['全部满足'], details


def check_momentum_sell_signal(row, logger):
    """
    【v14.0主力策略】动量倒T卖出信号（恢复v10.2逻辑）
    回测基础：2026-01-05至2026-04-03，59天，62信号，80.6%胜率（0.25元目标）

    条件（全部满足才触发）：
    1. 涨跌 > 100
    2. 风险 > 85
    3. 成交额 ≥ 3000万
    4. 股价 > 日均价 + 0.1元
    5. |MACD柱| > 0.06

    返回: (是否触发, 详情dict)
    """
    price = safe_float(row['收盘'])
    zhangdie = safe_float(row['涨跌'])
    fengxian = safe_float(row['风险'])
    amount_wan = safe_float(row.get('成交额_万'), 0)
    avg_price = safe_float(row['日均价'])
    macd_bar = safe_float(row['MACD柱'])
    price_diff = price - avg_price
    macd_abs = abs(macd_bar)

    details = {
        '时间': str(row['时间']),
        '价格': round(price, 2),
        '涨跌': round(zhangdie, 1),
        '风险': round(fengxian, 1),
        '成交额万': round(amount_wan, 0),
        '日均价': round(avg_price, 2),
        '股价差': round(price_diff, 3),
        'MACD柱': round(macd_bar, 4),
        'MACD柱绝对': round(macd_abs, 4),
    }

    # v14.0 动量策略条件（主力）
    cond1 = zhangdie > STRATEGY_CONFIG['ZHANGDIE_THRESH']
    cond2 = fengxian > STRATEGY_CONFIG['FENGXIAN_THRESH']
    cond3 = amount_wan >= STRATEGY_CONFIG['AMOUNT_THRESH_WAN']
    cond4 = price_diff > STRATEGY_CONFIG['MA_ABOVE']
    cond5 = macd_abs > STRATEGY_CONFIG['MACD_BAR_THRESH']

    details['满足条件'] = {
        f'涨跌>{STRATEGY_CONFIG["ZHANGDIE_THRESH"]}': cond1,
        f'风险>{STRATEGY_CONFIG["FENGXIAN_THRESH"]}': cond2,
        f'成交额≥{STRATEGY_CONFIG["AMOUNT_THRESH_WAN"]}万': cond3,
        f'股价>均价+{STRATEGY_CONFIG["MA_ABOVE"]}': cond4,
        f'|MACD柱|>{STRATEGY_CONFIG["MACD_BAR_THRESH"]}': cond5,
    }
    details['全部满足'] = all([cond1, cond2, cond3, cond4, cond5])

    return details['全部满足'], details


def check_zhengT_buy_signal(row, logger, amplitude=0, boll_width=0):
    """
    检查单根K线是否满足正T买入条件（v16.1 极低位高胜率组合 + BOLL带宽约束）
    条件：低于均价0.40元 + 风险<10 + 成交额≥5000万 + 涨跌≤0 + 日振幅≥0.80元 + BOLL带宽>1%
    v16.1回测（59天/156→88信号）：胜率从72%→83%@0.20目标，均反弹0.435→0.546元
    BOLL>1%是最大胜率提升器（+10pp），过滤极窄带宽日的无效信号
    返回: (是否触发, 详情dict)
    """
    price = safe_float(row['收盘'])
    zhangdie = safe_float(row['涨跌'])
    fengxian = safe_float(row['风险'])
    amount_wan = safe_float(row.get('成交额_万'), 0)
    avg_price = safe_float(row['日均价'])
    price_diff = avg_price - price  # 正T：均价 - 股价（要求低于均价越多越好）

    details = {
        '时间': str(row['时间']),
        '价格': round(price, 2),
        '涨跌': round(zhangdie, 1),
        '风险': round(fengxian, 1),
        '成交额万': round(amount_wan, 0),
        '日均价': round(avg_price, 2),
        '偏离均价': round(price_diff, 3),
        '日振幅': round(amplitude, 2),
        'BOLL带宽': round(boll_width, 2),
    }

    # v16.1 极低位高胜率组合（4条件 + 2硬约束）
    cond1 = price_diff > STRATEGY_CONFIG['ZHENGT_MA_BELOW']           # 偏离均价 > 0.40元（深度超卖）
    cond2 = fengxian < STRATEGY_CONFIG['ZHENGT_RISK_THRESH']           # 风险 < 10（超卖确认）
    cond3 = amount_wan >= STRATEGY_CONFIG['ZHENGT_AMOUNT_THRESH_WAN']   # 成交额 ≥ 5000万（活跃资金）
    cond4 = zhangdie <= STRATEGY_CONFIG['ZHENGT_ZD_THRESH']              # 涨跌 ≤ 0（仍在下跌或平盘）
    cond5 = amplitude >= STRATEGY_CONFIG['ZHENGT_MIN_AMPLITUDE']         # 日振幅 ≥ 0.80元（有反弹空间）
    cond6 = boll_width > STRATEGY_CONFIG['ZHENGT_MIN_BOLL_WIDTH']       # BOLL带宽 > 1.0%（市场有弹性，非萎缩态）

    details['满足条件'] = [cond1, cond2, cond3, cond4, cond5, cond6]
    details['全部满足'] = all([cond1, cond2, cond3, cond4, cond5, cond6])

    return details['全部满足'], details


def check_pullback_sell_signal(df, current_idx, logger, day_high=0):
    """
    【低波动日备用策略】冲高回落卖出信号检测（v16.0重构）

    v16.0重构（基于3/24-4/27缩量震荡期24天回测，72天全量回测优化）：
    - 去掉"高点逐根递减"→改为"从盘中最高点回落>0.20元"
    - 去掉"偏离均价>0.35"→改为"盘中最高点偏离均价>0.20元"
    - 去掉"量能萎缩"（与冲高互斥——冲高时往往放量）
    - 新增"收盘价偏离均价>0.20元"（过滤假冲高，价格确实在均线上方）
    - 条件从8个减为6个
    - 时间窗口从9:40-11:00扩展为9:40-13:30
    - 新增盘中最高点跟踪（从当天第一根K线到当前K线）

    全量回测结果（72天）：36信号/83.3%@0.25/86.1%@0.20/均差价0.763元

    触发条件（全部满足，6个条件）：
    1. 盘中最高点偏离日均价 > 0.20元（确认是冲高，不是随机波动）
    2. 当前最高价 < 盘中最高点 - 0.20元（从最高点回落超过0.20元）
    3. 收盘价偏离日均价 > 0.20元（价格确实在均线上方，过滤假冲高）
    4. 成交额 ≥ 3000万（过滤低量冲高）
    5. 当前收盘价 < BOLL上轨（已从上轨回落）
    6. 时间在 9:40 ~ 13:30

    参数：
    - day_high: 当天从开盘到当前的盘中最高价（由主循环传入）

    返回: (是否触发, 详情dict)
    """
    if current_idx < 2:
        return False, {'原因': '数据不足，需要至少2根K线'}

    current = df.iloc[current_idx]

    price = safe_float(current['收盘'])
    high = safe_float(current['最高'])
    amount_wan = safe_float(current.get('成交额_万'), 0)
    avg_price = safe_float(current['日均价'])
    boll_upper = safe_float(current['BOLL上轨'])
    boll_width = safe_float(current['BOLL带宽'])
    time_str = str(current['时间'])

    # 使用主循环传入的盘中最高价
    if day_high is None or day_high <= 0:
        return False, {'原因': f'盘中最高价无效({day_high})'}

    high_diff_from_avg = day_high - avg_price  # 盘中最高点偏离均价
    pullback_from_high = day_high - high        # 从最高点回落的幅度
    close_diff = price - avg_price              # 收盘价偏离均价

    details = {
        '策略': '冲高回落（低波动日备用）',
        '时间': time_str,
        '价格': round(price, 2),
        '最高': round(high, 2),
        '盘中最高': round(day_high, 2),
        '成交额万': round(amount_wan, 0),
        '日均价': round(avg_price, 2),
        '盘中最高偏离均价': round(high_diff_from_avg, 3),
        '从高点回落': round(pullback_from_high, 3),
        '收盘偏离均价': round(close_diff, 3),
        'BOLL上轨': round(boll_upper, 3),
        'BOLL带宽': round(boll_width, 2),
    }

    # 时间检查
    from pa_monitor import get_time_tuple
    h, m = get_time_tuple(time_str)
    in_time_window = (STRATEGY_CONFIG['PULLBACK_START'] <= (h, m) <= STRATEGY_CONFIG['PULLBACK_END'])

    # v16.0 冲高回落条件（6个条件，精简重构）
    cond1 = high_diff_from_avg > STRATEGY_CONFIG['PULLBACK_DAY_HIGH_DEVIATION']  # 盘中最高点偏离均价>0.20元
    cond2 = pullback_from_high > STRATEGY_CONFIG['PULLBACK_PULLBACK_FROM_HIGH']   # 从最高点回落>0.20元
    cond3 = close_diff > STRATEGY_CONFIG['PULLBACK_CLOSE_ABOVE_AVG']              # 收盘价偏离均价>0.20元
    cond4 = amount_wan >= STRATEGY_CONFIG['PULLBACK_AMOUNT_THRESH_WAN']           # 成交额≥3000万
    cond5 = price < boll_upper                                  # 已从BOLL上轨回落
    cond6 = in_time_window                                      # 时间窗口9:40-13:30

    details['满足条件'] = {
        f'盘中最高偏离均价>{STRATEGY_CONFIG["PULLBACK_DAY_HIGH_DEVIATION"]}({high_diff_from_avg:+.3f})': cond1,
        f'从高点回落>{STRATEGY_CONFIG["PULLBACK_PULLBACK_FROM_HIGH"]}({pullback_from_high:+.3f})': cond2,
        f'收盘偏离均价>{STRATEGY_CONFIG["PULLBACK_CLOSE_ABOVE_AVG"]}({close_diff:+.3f})': cond3,
        f'成交额≥{STRATEGY_CONFIG["PULLBACK_AMOUNT_THRESH_WAN"]}万({amount_wan:.0f})': cond4,
        '已从上轨回落': cond5,
        f'在时间窗口{STRATEGY_CONFIG["PULLBACK_START"][0]}:{STRATEGY_CONFIG["PULLBACK_START"][1]:02d}-{STRATEGY_CONFIG["PULLBACK_END"][0]}:{STRATEGY_CONFIG["PULLBACK_END"][1]:02d}': cond6,
    }
    details['全部满足'] = all([cond1, cond2, cond3, cond4, cond5, cond6])
    details['满足数量'] = sum([cond1, cond2, cond3, cond4, cond5, cond6])

    return details['全部满足'], details
