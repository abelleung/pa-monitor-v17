import numpy as np
from indicators import STRATEGY_CONFIG
# 人工股感策略（v2：直接用同花顺值）

def check_manual_daot_signal_v2(row, df, zhangdie=None, fengxian=None, up_cnt=None, logger=None, config=None, last_signal_bar=-999):
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
    # 安全计算 cond2_score（处理 None / nan）
    _zd = 0 if (zhangdie is None or (isinstance(zhangdie, float) and np.isnan(zhangdie)) else zhangdie
    _fx = 0 if (fengxian is None or (isinstance(fengxian, float) and np.isnan(fengxian)) else fengxian)
    cond2_score = int(_zd) + int(_fx)
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


def check_manual_zhengT_signal_v2(row, df, zhangdie=None, fengxian=None, down_cnt=None, logger=None, config=None, last_signal_bar=-999):
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
    # 安全计算 cond2_score（处理 None / nan）
    _zd = 0 if (zhangdie is None or (isinstance(zhangdie, float) and np.isnan(zhangdie)) else zhangdie
    _fx = 0 if (fengxian is None or (isinstance(fengxian, float) and np.isnan(fengxian)) else fengxian)
    cond2_score = int(_zd) + int(_fx)
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

