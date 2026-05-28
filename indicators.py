"""
指标计算函数（从 pa_monitor.py 解耦）
包含：safe_float, calc_indicators, _interpolate_cum_ratio, estimate_daily_amount_and_amplitude
以及辅助函数：get_time_tuple, is_trade_time
"""
import numpy as np
import pandas as pd
from pa_monitor import STRATEGY_CONFIG

# CUM_RATIO_TABLE (moved from pa_monitor.py)
CUM_RATIO_TABLE = {
    10:  0.137,   # ~09:40 开盘活跃期
    20:  0.199,   # ~09:50
    30:  0.261,   # ~10:00
    60:  0.400,   # ~10:30
    90:  0.494,   # ~11:00
    120: 0.578,   # ~11:30 (上午收盘)
    150: 0.677,   # ~13:30 (下午开盘30min)
    180: 0.767,   # ~14:00
    210: 0.859,   # ~14:30
    240: 1.000,   # ~15:00 (收盘)
}


def safe_float(value, default=0.0):
    """安全转换为float，NaN/None/异常返回默认值"""
    try:
        v = float(value)
        return v if not np.isnan(v) else default
    except (ValueError, TypeError):
        return default


# ==================== 辅助函数 ====================

def get_time_tuple(time_str):
    """从时间字符串提取 (hour, minute)"""
    parts = str(time_str).split(' ')
    if len(parts) < 2:
        return (99, 99)
    hm = parts[1].split(':')
    return (int(hm[0]), int(hm[1]))


def is_trade_time(time_str):
    """判断是否在交易窗口内 (09:40 ~ 14:30)"""
    h, m = get_time_tuple(time_str)
    return (h, m) >= STRATEGY_CONFIG['TRADE_START'] and (h, m) <= STRATEGY_CONFIG['TRDE_END']


# ==================== 技术指标计算 ====================

def llv(arr, period):
    """最低值（向量化）"""
    n = len(arr)
    result = np.full(n, np.nan)
    for i in range(period - 1, n):
        result[i] = np.min(arr[max(0, i - period + 1):i + 1])
    return result


def hhv(arr, period):
    """最高值（向量化）"""
    n = len(arr)
    result = np.full(n, np.nan)
    for i in range(period - 1, n):
        result[i] = np.max(arr[max(0, i - period + 1):i + 1])
    return result


def sma_wilder(arr, period, weight):
    """Wilders 平滑（通达信标准）"""
    n = len(arr)
    result = np.full(n, np.nan)
    if n >= period:
        result[period - 1] = np.mean(arr[:period])
        for i in range(period, n):
            result[i] = (result[i - 1] * (period - weight) + arr[i] * weight) / period
    return result


def ma_simple(arr, period, weight):
    """简单移动平均（SMA）"""
    n = len(arr)
    result = np.full(n, np.nan)
    for i in range(period - 1, n):
        result[i] = np.mean(arr[max(0, i - period + 1):i + 1])
    return result


def ema(arr, period):
    """指数移动平均（EMA）"""
    n = len(arr)
    result = np.full(n, np.nan)
    if n >= period:
        result[period - 1] = np.mean(arr[:period])
        alpha = 2.0 / (period + 1)
        for i in range(period, n):
            result[i] = arr[i] * alpha + result[i - 1] * (1 - alpha)
    return result


def calc_indicators(df):
    """
    计算所有 v14.0 策略所需指标（动量+BOLL+冲高回落）
    输入: DataFrame（需含列: 收盘, 最高, 最低, 成交额, 成交量, 时间）
    输出: DataFrame（新增列: 涨跌, 风险, 日均价, MACD, 成交额_万, BOLL上轨, BOLL带宽等）
    """
    c = df['收盘'].values.astype(float)
    h = df['最高'].values.astype(float)
    l = df['最低'].values.astype(float)
    n = len(c)

    # === 涨跌指标 ===
    llv27 = llv(l, 27); hv27 = hhv(h, 27)
    raw27 = np.full(n, np.nan)
    for i in range(n):
        denom = hv27[i] - llv27[i]
        if denom > 0: raw27[i] = (c[i] - llv27[i]) / denom * 100
    fast27 = sma_wilder(raw27, 5, 1); slow27 = sma_wilder(fast27, 5, 1)
    diff27 = fast27 * 3 - slow27 * 2
    zhangdie = ma_simple(sma_wilder(diff27, 3, 1), 5)

    # === 风险指标（v11.0: 加max(0,...)保护，防止负数） ===
    llv21 = llv(l, 21); hv21 = hhv(h, 21)
    var8 = np.full(n, np.nan)
    for i in range(n):
        denom = hv21[i] - llv21[i]
        if denom > 0: var8[i] = (c[i] - llv21[i]) / denom * 100
    rs = sma_wilder(var8, 13, 8); rs_slow = sma_wilder(rs, 13, 8)
    var9 = rs * 3 - rs_slow * 2
    fengxian_raw = sma_wilder(var9, 13, 8)
    fengxian = np.ceil(np.maximum(fengxian_raw, 0))  # v11.0: 防止负数

    # === MACD (12,26,9) ===
    ema_fast = ema(c, 12)
    ema_slow = ema(c, 26)
    dif = ema_fast - ema_slow
    dea = ema(dif, 9)
    macd_bar = 2 * (dif - dea)

    # === BOLL(20,2) 同花顺标准：收盘价 + ddof=0 ===
    boll_mid = np.full(n, np.nan)
    boll_up = np.full(n, np.nan)
    boll_dn = np.full(n, np.nan)
    for i in range(19, n):
        window = c[i-19:i+1]
        boll_mid[i] = np.mean(window)
        std = np.std(window, ddof=0)
        boll_up[i] = boll_mid[i] + 2 * std
        boll_dn[i] = boll_mid[i] - 2 * std
    boll_width = boll_up - boll_dn

    # === 买卖力道（通达信标准公式） ===
    llv24 = llv(l, 24)
    hv24 = hhv(h, 24)
    var2 = np.full(n, np.nan)
    for i in range(n):
        denom = hv24[i] - llv24[i]
        if denom > 0:
            var2[i] = (c[i] - llv24[i]) / denom * 2000
    maimai = sma_wilder(var2, 3, 1)

    # === 日均价 ===
    df = df.copy()
    df['日期'] = df['时间'].str[:10]
    df['累计成交额'] = df.groupby('日期')['成交额'].cumsum()
    df['累计成交量'] = df.groupby('日期')['成交量'].cumsum()
    df['日均价'] = df['累计成交额'] / df['累计成交量']

    # 成交额（万元）
    df['成交额_万'] = df['成交额'] / 10000

    # 写入指标
    df['涨跌'] = zhangdie
    df['风险'] = fengxian
    df['DIF'] = dif
    df['DEA'] = dea
    df['MACD柱'] = macd_bar
    df['BOLL中轨'] = boll_mid
    df['BOLL上轨'] = boll_up
    df['BOLL下轨'] = boll_dn
    df['BOLL带宽'] = boll_width
    df['买卖力道'] = maimai

    df.drop(columns=['日期', '累计成交额', '累计成交量'], inplace=True)
    return df


# ==================== 成交额预测 & 振幅预估 ====================

def _interpolate_cum_ratio(elapsed_min):
    """
    根据已过交易分钟数，线性插值计算累计额占全天比例。

    基于CUM_RATIO_TABLE（32个交易日1分钟线统计），
    在已知节点间线性插值。

    Args:
        elapsed_min: 已过交易分钟数（排除午休，10~240）
    Returns:
        累计额占全天比例 (0~1)
    """
    if elapsed_min <= 10:
        return CUM_RATIO_TABLE[10]
    if elapsed_min >= 240:
        return 1.0

    # 找到左右两个节点
    keys = sorted(CUM_RATIO_TABLE.keys())
    for i in range(len(keys) - 1):
        if keys[i] <= elapsed_min <= keys[i + 1]:
            # 线性插值
            left_key, right_key = keys[i], keys[i + 1]
            left_val = CUM_RATIO_TABLE[left_key]
            right_val = CUM_RATIO_TABLE[right_key]
            ratio = (elapsed_min - left_key) / (right_key - left_key)
            return left_val + ratio * (right_val - left_val)

    return 0.5  # 兜底


def estimate_daily_amount_and_amplitude(df, prev_close=0, open_price=0):
    """
    根据已交易分钟数据预估全天成交额和振幅。

    输入: DataFrame（已通过calc_indicators，含当天K线）
          prev_close: 昨收价，用于计算振幅百分比（为0时仍返回元值）
          open_price: 开盘价，用于跳空修正（为0时不修正）
    返回: dict {
        'elapsed_min': 已交易分钟数,
        'cumulative_amount_wan': 累计成交额(万),
        'per_min_amount_wan': 每分钟均成交额(万),
        'estimated_daily_yi': 预估全天成交额(亿元),
        'estimated_amplitude': 预估振幅(元，盘中高-低),
        'estimated_amplitude_pct': 预估振幅百分比(%，含跳空修正),
        'gap_amount': 跳空缺口(元，开盘价-昨收价，正值=跳高)，
        'raw_amplitude_pct': 未修正振幅百分比(%，仅盘中高-低),
        'is_am': 当前是否上午,
        'correction_used': 使用的修正系数,
        'is_volume_low': 是否缩量(<72亿),
        'is_extreme_low': 是否极端缩量(<30亿),
        'suggested_target': 建议目标差价,
    }
    """
    # 筛选今日K线
    today = datetime.now().strftime("%Y-%m-%d")
    today_df = df[df['时间'].astype(str).str.startswith(today)]

    if len(today_df) < 5:
        return None  # 数据太少，不预估

    # 计算已过分钟数（排除午休）
    elapsed = len(today_df)

    # 累计成交额（万元）
    amount_col = '成交额' if '成交额' in today_df.columns else 'amount'
    cum_amount_wan = float(today_df[amount_col].sum()) / 10000

    # 每分钟均成交额（万元）
    per_min_wan = cum_amount_wan / elapsed if elapsed > 0 else 0

    # 判断上午/下午
    latest_time = str(today_df.iloc[-1]['时间'])
    h, _ = get_time_tuple(latest_time)
    is_am = h < 12

    # ============================================================
    # v15.2 累计占比法（替代上午占比法+下午线性外推）
    # 
    # 核心改进：
    #   - 旧算法：上午用占比法/下午用均额线性外推 → 13:30跳变严重
    #     例：11:20心跳34.9亿 → 13:30心跳24.3亿（下午均额偏低导致低估）
    #   - 新算法：全天 = 累计额 / 该时刻累计占比（线性插值）
    #   - 自然反映下午量能衰减、尾盘放量
    #   - 无需区分上午/下午，无跳变
    #
    # 精度对比（32天回测，|误差|均值%）：
    #   09:40: 75.88%→24.66%  10:30: 29.53%→17.83%
    #   11:30: 11.16%→10.57%  13:30: 7.20%→7.09%
    #   14:30: 4.79%→3.63%    14:50: 1.78%→1.21%
    # ============================================================

    # 计算已过交易分钟数（排除午休：11:30-13:00不算）
    # 上午: 09:30-11:30 = 120分钟
    # 下午: 13:00-15:00 = 120分钟
    # 总计: 240分钟
    if is_am:
        adjusted_elapsed = elapsed
    else:
        # 下午：上午120分钟 + 下午已过分钟
        pm_bars = today_df[today_df['时间'].astype(str).str[11:13].astype(int) >= 12]
        adjusted_elapsed = 120 + len(pm_bars)

    # 累计占比插值
    elapsed_clamped = max(10, min(adjusted_elapsed, 240))  # 至少10分钟才开始预估
    cum_ratio = _interpolate_cum_ratio(elapsed_clamped)

    if cum_ratio > 0:
        estimated_daily_wan = cum_amount_wan / cum_ratio
        correction = cum_ratio  # 用于日志显示
    else:
        # 兜底：不应发生
        estimated_daily_wan = cum_amount_wan / 0.5
        correction = 0.5

    estimated_daily_yi = estimated_daily_wan / 10000  # 转亿元

    # 计算实际已发生振幅（当前最高价-最低价）
    actual_high = safe_float(today_df['最高'].max())
    actual_low = safe_float(today_df['最低'].min(), 99999)
    actual_amplitude = actual_high - actual_low if actual_high > 0 and actual_low < 99999 else 0

    # 振幅预估（基于成交额）
    estimated_amplitude_from_volume = STRATEGY_CONFIG['AMP_SLOPE'] * estimated_daily_yi + STRATEGY_CONFIG['AMP_INTERCEPT']

    # 跳空修正：跳空缺口 = 开盘价 - 昨收价
    gap_amount = 0
    if open_price > 0 and prev_close > 0:
        gap_amount = round(open_price - prev_close, 2)

    # 预估振幅取较大值：基于成交额的预估 vs 实际已发生振幅
    # 逻辑：如果实际振幅已经超过预估，说明预估偏低，应以实际为准
    estimated_amplitude = max(estimated_amplitude_from_volume, actual_amplitude)

    # 振幅百分比（含跳空修正）
    if prev_close > 0:
        raw_amplitude_pct = estimated_amplitude_from_volume / prev_close * 100
        # 修正后振幅 = (预估振幅 + |跳空缺口|) / 昨收价 × 100%
        corrected_amplitude = estimated_amplitude + abs(gap_amount)
        estimated_amplitude_pct = corrected_amplitude / prev_close * 100
        # 实际振幅百分比
        actual_amplitude_pct = actual_amplitude / prev_close * 100
    else:
        raw_amplitude_pct = 0
        estimated_amplitude_pct = 0
        actual_amplitude_pct = 0

    # 缩量判断（用预估全天成交额，更准确）
    estimated_daily_yi_val = estimated_daily_yi  # 预估全天成交额（亿元）
    is_volume_low = estimated_daily_yi_val < 72  # 全天<72亿为缩量
    is_extreme_low = estimated_daily_yi_val < 30  # 全天<30亿为极端缩量

    suggested_target = STRATEGY_CONFIG['EXTREME_LOW_TARGET'] if is_extreme_low else STRATEGY_CONFIG['TARGET_DIFF_LOW_VOLUME']

    # 每分钟均额（用预估全天/240分钟，更合理的"等效均额"）
    equiv_per_min_wan = estimated_daily_wan / 240 if estimated_daily_wan > 0 else per_min_wan

    return {
        'elapsed_min': adjusted_elapsed,
        'cumulative_amount_wan': cum_amount_wan,
        'per_min_amount_wan': per_min_wan,
        'adjusted_per_min_wan': equiv_per_min_wan,  # 等效每分钟均额（基于预估全天）
        'estimated_daily_yi': estimated_daily_yi,
        'estimated_amplitude': round(estimated_amplitude, 2),
        'estimated_amplitude_pct': round(estimated_amplitude_pct, 2),
        'actual_amplitude': round(actual_amplitude, 2),  # 实际已发生振幅（元）
        'actual_amplitude_pct': round(actual_amplitude_pct, 2),  # 实际振幅百分比
        'actual_high': round(actual_high, 2),  # 当前最高价
        'actual_low': round(actual_low, 2),  # 当前最低价
        'gap_amount': gap_amount,
        'raw_amplitude_pct': round(raw_amplitude_pct, 2),
        'is_am': is_am,
        'correction_used': correction,
        'is_volume_low': is_volume_low,
        'is_extreme_low': is_extreme_low,
        'suggested_target': suggested_target,
    }
