"""
策略判断函数（从 pa_monitor.py 解耦）
包含：BOLL上轨、动量、冲高回落、正T买入 四个策略
"""
import numpy as np
from indicators import safe_float, get_time_tuple, STRATEGY_CONFIG


def check_boll_sell_signal(row, logger, day_high=0, config=None):
    """
    【v14.0补充策略】BOLL上轨倒T卖出信号（v17.0更新）

    v17.0改动：新增当日涨幅≤2.0%防追高 + 从当日最高回落>0.10元

    条件（全部满足才触发）：
    1. 最高价 ≥ BOLL上轨 × 0.995（触碰上轨）
    2. 成交额 ≥ 3000万
    3. 收盘价 > 日均价 + 0.10元
    4. 偏离日均价 > 0.30元
    5. MACD柱 > 0.06
    6. 当日涨幅 ≤ 2.0%（防追高）
    7. 从当日最高回落 > 0.10元

    返回: (是否触发, 详情dict)
    """
    if config is None:
        config = STRATEGY_CONFIG
    price = safe_float(row['收盘'])
    high = safe_float(row['最高'])
    amount_wan = safe_float(row.get('成交额_万'), 0)
    avg_price = safe_float(row['日均价'])
    macd_bar = safe_float(row['MACD柱'])
    boll_upper = safe_float(row['BOLL上轨'])
    boll_width = safe_float(row['BOLL带宽'])

    price_diff = price - avg_price  # 偏离日均价

    # 当日涨幅（收盘价vs昨收）
    prev_close = safe_float(row.get('prev_close', 0))
    day_gain_pct = (price - prev_close) / prev_close * 100 if prev_close > 0 else 0

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
        '当日涨幅%': round(day_gain_pct, 2),
        '从最高回落': round(day_high - price, 3) if day_high > 0 else 0,
    }

    # BOLL v17.0 卖出条件（7条件）
    cond1 = high >= boll_upper * config['BOLL_TOUCH_RATIO']  # 触碰BOLL上轨
    cond2 = amount_wan >= config['BOLL_AMOUNT_THRESH_WAN']    # 成交额≥3000万
    cond3 = price_diff > config['BOLL_MA_ABOVE']              # 股价>日均价+0.1
    cond4 = price_diff > config['BOLL_DEVIATION_THRESH']      # 偏离日均价>0.3元
    cond5 = macd_bar > config['BOLL_MACD_THRESH']             # MACD柱>0.06
    cond6 = day_gain_pct <= config['BOLL_DAY_GAIN_MAX']    # 当日涨幅≤2.0%（防追高）
    cond7 = (day_high - price) > config['BOLL_PULLBACK_FROM_HIGH']  # 从最高回落>0.10元

    details['满足条件'] = {
        '触碰上轨': cond1,
        '成交额≥3000万': cond2,
        '股价>均价+0.1': cond3,
        '偏离均价>0.3': cond4,
        'MACD柱>0.06': cond5,
        f'当日涨幅≤{config["BOLL_DAY_GAIN_MAX"]}%': cond6,
        f'从最高回落>{config["BOLL_PULLBACK_FROM_HIGH"]}元': cond7,
    }
    details['全部满足'] = all([cond1, cond2, cond3, cond4, cond5, cond6, cond7])

    return details['全部满足'], details


def check_momentum_sell_signal(row, logger, config=None):
    """
    【v14.0主力策略】动量倒T卖出信号（恢复v10.2逻辑）
    回测基础：2026-01-05至2026-04-03，59天，62信号，80.6%胜率（0.25元目标）

    条件（全部满足才触发）：
    1. 涨跌 > 100
    2. 风险 > 85
    3. 成交额 ≥ 3000万
    4. 股价 > 日均价 + 0.10元
    5. |MACD柱| > 0.06

    返回: (是否触发, 详情dict)
    """
    if config is None:
        config = STRATEGY_CONFIG
    price = safe_float(row['收盘'])
    zhangdie = safe_float(row['涨跌'])
    fengxian = safe_float(row['风险'])
    amount_wan = safe_float(row.get('成交额_万'), 0)
    avg_price = safe_float(row['日均价'])
    macd_bar = safe_float(row['MACD柱'])
    macd_abs = abs(macd_bar)
    price_diff = price - avg_price  # 偏离日均价

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
    cond1 = zhangdie > config['ZHANGDIE_THRESH']
    cond2 = fengxian > config['FENGXIAN_THRESH']
    cond3 = amount_wan >= config['AMOUNT_THRESH_WAN']
    cond4 = price_diff > config['MA_ABOVE']
    cond5 = macd_abs > config['MACD_BAR_THRESH']

    details['满足条件'] = {
        f'涨跌>{config["ZHANGDIE_THRESH"]}': cond1,
        f'风险>{config["FENGXIAN_THRESH"]}': cond2,
        f'成交额≥{config["AMOUNT_THRESH_WAN"]}万': cond3,
        f'股价>均价+{config["MA_ABOVE"]}': cond4,
        f'|MACD柱|>{config["MACD_BAR_THRESH"]}': cond5,
    }
    details['全部满足'] = all([cond1, cond2, cond3, cond4, cond5])

    return details['全部满足'], details

def check_zhengT_buy_signal(row, logger, amplitude=0, boll_width_pct=0, config=None):
    """
    检查单根K线是否满足正T买入条件（v17.0 极低位高胜率组合）

    条件（全部满足）：
    1. 均价 - 股价 > 0.55元（v17.0收紧，原0.40元）
    2. 风险 < 12（v17.0调整，原10）
    3. 成交额 ≥ 5000万（强筛选器）
    4. 涨跌 ≤ -1（v17.0收紧，原0）
    5. 日振幅 ≥ 0.40元（v17.0收紧，原0.80元）
    6. BOLL带宽 > 0.1元（防极窄震荡）
    7. 当前时间 < 14:00（v15.1新增，14点后胜率仅36%）
    8. 连跌天数 ≤ 2天（v15.1新增，连跌>2天胜率骤降）

    参数: boll_width_pct = BOLL带宽/收盘价 × 100%（百分比，不是元）
    返回: (是否触发, 详情dict)
    """
    if config is None:
        config = STRATEGY_CONFIG
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
        'BOLL带宽%': round(boll_width_pct, 2),
    }

    # v17.0 极低位高胜率组合（6条件 + 2硬约束）
    cond1 = price_diff > config['ZHENGT_MA_BELOW']           # 偏离均价 > 0.55元（深度超卖）
    cond2 = fengxian < config['ZHENGT_RISK_THRESH']           # 风险 < 12（超卖确认）
    cond3 = amount_wan >= config['ZHENGT_AMOUNT_THRESH_WAN']   # 成交额 ≥ 5000万（活跃资金）
    cond4 = zhangdie <= config['ZHENGT_ZD_THRESH']              # 涨跌 ≤ -1（仍在下跌或平盘）
    cond5 = amplitude >= config['ZHENGT_MIN_AMPLITUDE']         # 日振幅 ≥ 0.40元（有反弹空间）
    cond6 = boll_width_pct > config['ZHENGT_MIN_BOLL_WIDTH']   # BOLL带宽 > 0.1元（防极窄震荡）

    details['满足条件'] = [cond1, cond2, cond3, cond4, cond5, cond6]
    details['全部满足'] = all([cond1, cond2, cond3, cond4, cond5, cond6])

    return details['全部满足'], details


def check_pullback_sell_signal(df, current_idx, logger, day_high=0, config=None):
    """
    【低波动日备用策略】冲高回落卖出信号检测（v17.0更新）

    v17.0改动：
    - 成交额阈值从3000万→4000万
    - 回落阈值从0.20元→0.15元（收紧提升胜率）
    - 时间窗口从9:40-13:30→9:40-14:00（延长）
    - 新增BOLL带宽>1.5元（防窄幅震荡）

    触发条件（全部满足，7个条件）：
    1. 盘中最高点偏离均价 > 0.20元（确认是冲高，不是随机波动）
    2. 从盘中最高回落 > 0.15元（v17.0收紧）
    3. 收盘价偏离均价 > 0.20元（价格确实在均线上方，过滤假冲高）
    4. 成交额 ≥ 4000万（v17.0提升）
    5. 收盘价 < BOLL上轨（已从上轨回落）
    6. BOLL带宽 > 1.5元（防窄幅震荡）
    7. 时间在 9:40 ~ 14:00（v17.0延长）

    参数：
    - day_high: 当天从开盘到当前的盘中最高价（由主循环传入）

    返回: (是否触发, 详情dict)
    """
    if config is None:
        config = STRATEGY_CONFIG
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
    h, m = get_time_tuple(time_str)
    in_time_window = (config['PULLBACK_START'] <= (h, m) <= config['PULLBACK_END'])

    # v17.0 冲高回落条件（7个条件）
    cond1 = high_diff_from_avg > config['PULLBACK_DAY_HIGH_DEVIATION']  # 盘中最高偏离均价>0.20元
    cond2 = pullback_from_high > config['PULLBACK_PULLBACK_FROM_HIGH']   # 从最高回落>0.15元(v17.0收紧)
    cond3 = close_diff > config['PULLBACK_CLOSE_ABOVE_AVG']              # 收盘偏离均价>0.20元
    cond4 = amount_wan >= config['PULLBACK_AMOUNT_THRESH_WAN']           # 成交额≥4000万(v17.0提升)
    cond5 = price < boll_upper                                  # 已从BOLL上轨回落
    cond6 = boll_width > config['PULLBACK_BANDWIDTH_THRESH']         # BOLL带宽>1.5元（防窄幅震荡）
    cond7 = in_time_window                                      # 时间窗口9:40-14:00(v17.0延长)

    details['满足条件'] = {
        f'盘中最高偏离均价>{config["PULLBACK_DAY_HIGH_DEVIATION"]}({high_diff_from_avg:+.3f})': cond1,
        f'从高点回落>{config["PULLBACK_PULLBACK_FROM_HIGH"]}({pullback_from_high:+.3f})': cond2,
        f'收盘偏离均价>{config["PULLBACK_CLOSE_ABOVE_AVG"]}({close_diff:+.3f})': cond3,
        f'成交额≥{config["PULLBACK_AMOUNT_THRESH_WAN"]}万({amount_wan:.0f})': cond4,
        '收盘价<BOLL上轨': cond5,
        f'BOLL带宽>{config["PULLBACK_BANDWIDTH_THRESH"]}元({boll_width:.2f})': cond6,
        f'在时间窗口{config["PULLBACK_START"][0]}:{config["PULLBACK_START"][1]:02d}-{config["PULLBACK_END"][0]}:{config["PULLBACK_END"][1]:02d}': cond7,
    }
    details['满足数量'] = sum([cond1, cond2, cond3, cond4, cond5, cond6, cond7])
    details['全部满足'] = all([cond1, cond2, cond3, cond4, cond5, cond6, cond7])

    return details['全部满足'], details

# ==================== 人工股感策略（同花顺公式版）====================
# 基于abelleung的股感：成交额+风险涨跌+九转+VWAP+BOLL触碰

def check_manual_daot_signal(row, df, logger, config=None):
    """
    【人工股感】倒T卖出信号（基于同花顺公式）
    
    五条件（必须2个 + 加分3个）：
    1. 【必须】成交额 ≥ 3000万（相对前序放大N倍 → +N分）
    2. 【必须】风险+涨跌合计 > 184（越高分越高）
    3. 【加分】上涨九转第9根（高9）→ +10分
    4. 【必须】价格 > 均价（VWAP）
    5. 【加分】收盘价 ≥ BOLL上轨（触碰顶线）→ +5分
    
    返回: (是否触发, 详情dict, 总分)
    """
    if config is None:
        config = STRATEGY_CONFIG
    
    price = float(row['收盘'])
    amount_wan = float(row.get('成交额_万', 0))
    avg_price = float(row['日均价'])
    boll_upper = float(row['BOLL上轨'])
    zhangdie = float(row.get('涨跌', 0))
    fengxian = float(row.get('风险', 0))
    up_cnt = int(row.get('上涨九转', 0))
    
    # 计算成交额相对放大倍数（与前5根K线平均成交额比较）
    df_copy = df.copy()
    idx = len(df_copy) - 1  # 当前是最后一根
    if idx >= 5:
        prev_5_avg = df_copy.iloc[max(0, idx-5):idx]['成交额_万'].mean()
    else:
        prev_5_avg = amount_wan  # 不足5根时用当前值
    amount_ratio = amount_wan / prev_5_avg if prev_5_avg > 0 else 1
    
    # ===== 条件评分 =====
    score = 0
    details = {
        '时间': str(row['时间']),
        '价格': round(price, 2),
        '成交额万': round(amount_wan, 0),
        '成交额放大倍数': round(amount_ratio, 1),
        '涨跌': round(zhangdie, 1),
        '风险': round(fengxian, 0),
        '涨跌+风险': round(zhangdie + fengxian, 0),
        '均价': round(avg_price, 2),
        '价格vs均价': '上方' if price > avg_price else '下方',
        'BOLL上轨': round(boll_upper, 3),
        'BOLL触碰': price >= boll_upper,
        '上涨九转计数': up_cnt,
    }
    
    # 条件1: 成交额 ≥ 3000万（必须）
    cond1 = amount_wan >= 3000
    if cond1:
        score += min(int(amount_ratio), 10)  # 加分：放大倍数（最高+10分）
        details['成交额✅'] = f'≥3000万, 放大{amount_ratio:.1f}倍'
    else:
        details['成交额❌'] = '成交额<3000万'
        return False, details, score  # 不满足条件1，直接返回
    
    # 条件2: 风险+涨跌合计 > 184（必须）
    cond2_score = int((0 if np.isnan(zhangdie) else zhangdie) + (0 if np.isnan(fengxian) else fengxian))
    score += max(0, int((cond2_score - 184) / 10))  # 每超10分+1分
    details['涨跌+风险'] = cond2_score
    details['条件2✅'] = f'合计={cond2_score} > 184' if cond2_score > 184 else f'合计={cond2_score} ≤ 184'
    
    if cond2_score <= 184:
        details['条件2❌'] = '合计≤184，不触发'
        return False, details, score  # 不满足条件2，直接返回
    
    # 条件3: 上涨九转第9根（加分）
    cond3 = (up_cnt == 9)
    if cond3:
        score += 10
        details['九转✅'] = '上涨九转第9根（高9）'
    else:
        details['九转'] = f'上涨九转第{up_cnt}根（未到第9根）'
    
    # 条件4: 价格 > 均价（必须）
    cond4 = price > avg_price
    if not cond4:
        details['条件4❌'] = f'价格在均价下方（{price:.2f} < {avg_price:.2f}）'
        return False, details, score  # 不满足条件4，直接返回
    else:
        details['条件4✅'] = f'价格在均线上方（{price:.2f} > {avg_price:.2f}）'
    
    # 条件5: BOLL触碰（加分）
    cond5 = price >= boll_upper
    if cond5:
        score += 5
        details['BOLL✅'] = '触碰BOLL顶线'
    else:
        details['BOLL'] = '未触碰BOLL顶线'
    
    # 是否触发：总分 ≥ 2分（条件1+2 + 条件4）
    triggered = score >= 2
    
    details['总分'] = score
    details['触发'] = triggered
    
    return triggered, details, score


def check_manual_zhengT_signal(row, df, logger, config=None):
    """
    【人工股感】正T买入信号（基于同花顺公式）
    
    五条件（必须2个 + 加分3个）：
    1. 【必须】成交额 ≥ 3000万（相对前序放大N倍 → +N分）
    2. 【必须】风险+涨跌合计 < 10（越低分越高）
    3. 【加分】下跌九转第9根（低9）→ +10分
    4. 【必须】价格 < 均价（VWAP）
    5. 【加分】收盘价 ≤ BOLL下轨（触碰底线）→ +5分
    
    返回: (是否触发, 详情dict, 总分)
    """
    if config is None:
        config = STRATEGY_CONFIG
    
    price = float(row['收盘'])
    amount_wan = float(row.get('成交额_万', 0))
    avg_price = float(row['日均价'])
    boll_lower = float(row['BOLL下轨'])
    zhangdie = float(row.get('涨跌', 0))
    fengxian = float(row.get('风险', 0))
    down_cnt = int(row.get('下跌九转', 0))
    
    # 计算成交额相对放大倍数
    df_copy = df.copy()
    idx = len(df_copy) - 1
    if idx >= 5:
        prev_5_avg = df_copy.iloc[max(0, idx-5):idx]['成交额_万'].mean()
    else:
        prev_5_avg = amount_wan
    amount_ratio = amount_wan / prev_5_avg if prev_5_avg > 0 else 1
    
    # ===== 条件评分 =====
    score = 0
    details = {
        '时间': str(row['时间']),
        '价格': round(price, 2),
        '成交额万': round(amount_wan, 0),
        '成交额放大倍数': round(amount_ratio, 1),
        '涨跌': round(zhangdie, 1),
        '风险': round(fengxian, 0),
        '涨跌+风险': round(zhangdie + fengxian, 0),
        '均价': round(avg_price, 2),
        '价格vs均价': '上方' if price > avg_price else '下方',
        'BOLL下轨': round(boll_lower, 3),
        'BOLL触碰': price <= boll_lower,
        '下跌九转计数': down_cnt,
    }
    
    # 条件1: 成交额 ≥ 3000万（必须）
    cond1 = amount_wan >= 3000
    if cond1:
        score += min(int(amount_ratio), 10)
        details['成交额✅'] = f'≥3000万, 放大{amount_ratio:.1f}倍'
    else:
        details['成交额❌'] = '成交额<3000万'
        return False, details, score
    
    # 条件2: 风险+涨跌合计 < 10（必须）
    cond2_score = int((0 if np.isnan(zhangdie) else zhangdie) + (0 if np.isnan(fengxian) else fengxian))
    score += max(0, int((10 - cond2_score) / 2))  # 越低分越高（最高+5分）
    details['涨跌+风险'] = cond2_score
    details['条件2✅'] = f'合计={cond2_score} < 10' if cond2_score < 10 else f'合计={cond2_score} ≥ 10'
    
    if cond2_score >= 10:
        details['条件2❌'] = '合计≥10，不触发'
        return False, details, score
    
    # 条件3: 下跌九转第9根（加分）
    cond3 = (down_cnt == 9)
    if cond3:
        score += 10
        details['九转✅'] = '下跌九转第9根（低9）'
    else:
        details['九转'] = f'下跌九转第{down_cnt}根（未到第9根）'
    
    # 条件4: 价格 < 均价（必须）
    cond4 = price < avg_price
    if not cond4:
        details['条件4❌'] = f'价格在均线上方（{price:.2f} > {avg_price:.2f}）'
        return False, details, score
    else:
        details['条件4✅'] = f'价格在均价下方（{price:.2f} < {avg_price:.2f}）'
    
    # 条件5: BOLL触碰（加分）
    cond5 = price <= boll_lower
    if cond5:
        score += 5
        details['BOLL✅'] = '触碰BOLL底线'
    else:
        details['BOLL'] = '未触碰BOLL底线'
    
    # 是否触发：总分 ≥ 2分（条件1+2 + 条件4）
    triggered = score >= 2
    
    details['总分'] = score
    details['触发'] = triggered
    
    return triggered, details, score


# =================== 人工股感策略 v3（方案A+九转硬约束）====================
def check_manual_daot_signal_v3(row, df, zhangdie=None, fengxian=None, up_cnt=None, logger=None, config=None, last_signal_bar=-999):
    """
    【人工股感】倒T卖出信号（直接用同花顺值）

    参数：
    - zhangdie: 同花顺涨跌值（直接传入）
    - fengxian: 同花顺风险值（直接传入）
    - up_cnt: 同花顺上涨九转计数（直接传入）
    - last_signal_bar: 上次信号时的bar索引（用于冷却期检查，默认-999表示无冷却）
    """
    if config is None:
        config = STRATEGY_CONFIG

    # 正T冷却期：5分钟 = 5根1分钟K线
    COOLDOWN_BARS = 5
    current_bar = len(df) - 1
    if current_bar - last_signal_bar < COOLDOWN_BARS:
        return False, {'冷却期': f'距离上次信号仅{current_bar - last_signal_bar}根K线，需等待{COOLDOWN_BARS}根'}, 0
    
    price = float(row['收盘'])
    amount_wan = float(row.get('成交额_万', 0))
    avg_price = float(row['日均价'])
    boll_upper = float(row['BOLL上轨'])
    
    # 用传入的同花顺值（如果提供）
    if zhangdie is not None:
        zhangdie = zhangdie
    else:
        zhangdie = float(row.get('涨跌', 0))
    if fengxian is not None:
        fengxian = fengxian
    else:
        fengxian = float(row.get('风险', 0))
    if up_cnt is not None:
        up_cnt = up_cnt
    else:
        up_cnt = int(row.get('上涨九转', 0))
    
    # 计算成交额相对放大倍数
    df_copy = df.copy()
    idx = len(df_copy) - 1
    if idx >= 5:
        prev_5_avg = df_copy.iloc[max(0, idx-5):idx]['成交额_万'].mean()
    else:
        prev_5_avg = amount_wan
    amount_ratio = amount_wan / prev_5_avg if prev_5_avg > 0 else 1
    
    # ===== 条件评分 =====
    score = 0
    details = {
        '时间': str(row['时间']),
        '价格': round(price, 2),
        '成交额万': round(amount_wan, 0),
        '成交额放大倍数': round(amount_ratio, 1),
        '涨跌': round(zhangdie, 1),
        '风险': round(fengxian, 0),
        '涨跌+风险': round(zhangdie + fengxian, 0),
        '均价': round(avg_price, 2),
        '价格vs均价': '上方' if price > avg_price else '下方',
        'BOLL上轨': round(boll_upper, 3),
        'BOLL触碰': price >= boll_upper,
        '上涨九转计数': up_cnt,
    }
    
    # 条件1: 成交额 ≥ 3000万（必须）
    cond1 = amount_wan >= 3000
    if cond1:
        # 加分：基础1分 + 每超过3000万1倍+1分（最高10分）
        bonus = min(int(amount_wan / 3000), 10)  # 3000万=1分，6000万=2分...3亿=10分
        score += bonus
        details['成交额✅'] = f'≥3000万, {amount_wan:.0f}万={bonus}分'
    else:
        details['成交额❌'] = '成交额<3000万'
        return False, details, score
    
    # 条件2: 风险+涨跌合计 > 184（必须）
    cond2_score = int((0 if np.isnan(zhangdie) else zhangdie) + (0 if np.isnan(fengxian) else fengxian))
    score += max(0, int((cond2_score - 184) / 10))  # 每超10分+1分
    details['涨跌+风险'] = cond2_score
    details['条件2✅'] = f'合计={cond2_score} > 190' if cond2_score > 190 else f'合计={cond2_score} ≤ 190'
    
    if cond2_score <= 184:
        details['条件2❌'] = '合计≤184，不触发'
        return False, details, score
    
    # 条件3: 上涨九转第9根（加分）
    cond3 = (up_cnt == 9)
    if cond3:
        score += 10
        details['九转✅'] = '上涨九转第9根（高9）'
    else:
        details['九转'] = f'上涨九转第{up_cnt}根（未到第9根）'
    
    # 条件4: 价格 > 均价（必须）
    cond4 = price > avg_price
    if not cond4:
        details['条件4❌'] = f'价格在均价下方（{price:.2f} < {avg_price:.2f}）'
        return False, details, score
    else:
        details['条件4✅'] = f'价格在均线上方（{price:.2f} > {avg_price:.2f}）'
    
    # 条件5: BOLL触碰（加分）
    cond5 = price >= boll_upper
    if cond5:
        score += 5
        details['BOLL✅'] = '触碰BOLL顶线'
    else:
        details['BOLL'] = '未触碰BOLL顶线'
    
    # 是否触发：总分 ≥ 2分（条件1+2 + 条件4）
    triggered = score >= 5
    
    details['总分'] = score
    details['触发'] = triggered
    
    return triggered, details, score



def check_manual_zhengT_signal_v3(row, df, zhangdie=None, fengxian=None, down_cnt=None, logger=None, config=None, last_signal_bar=-999):
    """
    【人工股感】正T买入信号（直接用同花顺值）

    参数：
    - last_signal_bar: 上次信号时的bar索引（用于冷却期检查，默认-999表示无冷却）
    """
    if config is None:
        config = STRATEGY_CONFIG

    # 正T冷却期：5分钟 = 5根1分钟K线
    COOLDOWN_BARS = 5
    current_bar = len(df) - 1
    if current_bar - last_signal_bar < COOLDOWN_BARS:
        return False, {'冷却期': f'距离上次信号仅{current_bar - last_signal_bar}根K线，需等待{COOLDOWN_BARS}根'}, 0
    
    price = float(row['收盘'])
    amount_wan = float(row.get('成交额_万', 0))
    avg_price = float(row['日均价'])
    boll_lower = float(row['BOLL下轨'])
    
    # 用传入的同花顺值
    if zhangdie is not None:
        zhangdie = zhangdie
    else:
        zhangdie = float(row.get('涨跌', 0))
    if fengxian is not None:
        fengxian = fengxian
    else:
        fengxian = float(row.get('风险', 0))
    if down_cnt is not None:
        down_cnt = down_cnt
    else:
        down_cnt = int(row.get('下跌九转', 0))
    
    # 成交额放大倍数
    df_copy = df.copy()
    idx = len(df_copy) - 1
    if idx >= 5:
        prev_5_avg = df_copy.iloc[max(0, idx-5):idx]['成交额_万'].mean()
    else:
        prev_5_avg = amount_wan
    amount_ratio = amount_wan / prev_5_avg if prev_5_avg > 0 else 1
    
    # ===== 条件评分 =====
    score = 0
    details = {
        '时间': str(row['时间']),
        '价格': round(price, 2),
        '成交额万': round(amount_wan, 0),
        '成交额放大倍数': round(amount_ratio, 1),
        '涨跌': round(zhangdie, 1),
        '风险': round(fengxian, 0),
        '涨跌+风险': round(zhangdie + fengxian, 0),
        '均价': round(avg_price, 2),
        '价格vs均价': '上方' if price > avg_price else '下方',
        'BOLL下轨': round(boll_lower, 3),
        'BOLL触碰': price <= boll_lower,
        '下跌九转计数': down_cnt,
    }
    
    # 条件1: 成交额 ≥ 3000万（必须）
    cond1 = amount_wan >= 3000
    if cond1:
        score += min(int(amount_ratio), 10)
        details['成交额✅'] = f'≥3000万, 放大{amount_ratio:.1f}倍'
    else:
        details['成交额❌'] = '成交额<3000万'
        return False, details, score
    
    # 条件2: 风险+涨跌合计 < 10（必须）
    cond2_score = int((0 if np.isnan(zhangdie) else zhangdie) + (0 if np.isnan(fengxian) else fengxian))
    score += max(0, int((10 - cond2_score) / 2))  # 越低分越高
    details['涨跌+风险'] = cond2_score
    details['条件2✅'] = f'合计={cond2_score} < 10' if cond2_score < 10 else f'合计={cond2_score} ≥ 10'
    
    if cond2_score >= 10:
        details['条件2❌'] = '合计≥10，不触发'
        return False, details, score
    
    # 条件3: 下跌九转第9根（必须）
    cond3 = (down_cnt == 9)
    if not cond3:
        details['九转❌'] = f'下跌九转第{down_cnt}根（未到第9根），不触发'
        return False, details, score
    else:
        score += 10
        details['九转✅'] = '下跌九转第9根（低9）'
    
    # 条件4: 价格 < 均价（必须）
    cond4 = price < avg_price
    if not cond4:
        details['条件4❌'] = f'价格在均线上方（{price:.2f} > {avg_price:.2f}）'
        return False, details, score
    else:
        details['条件4✅'] = f'价格在均价下方（{price:.2f} < {avg_price:.2f}）'
    
    # 条件5: BOLL触碰（必须）
    cond5 = price <= boll_lower
    if not cond5:
        details["BOLL❌"] = f"价格{price:.2f} > BOLL底线{boll_lower:.3f}，不触发"
        return False, details, score
    else:
        score += 5
        details["BOLL✅"] = "触碰BOLL底线"
    # 是否触发：总分 ≥ 2分
    triggered = score >= 5
    
    details['总分'] = score
    details['触发'] = triggered
    
    return triggered, details, score

