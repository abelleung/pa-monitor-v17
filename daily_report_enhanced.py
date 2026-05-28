"""
每日复盘报告增强模块 — 自动生成图表和详细分析

功能：
1. 收盘后自动生成四图分析报告（价格/BOLL带宽/MACD/成交额）
2. v15.1.2三策略条件满足度分析（动量/BOLL/冲高回落）
3. 正T策略条件分析（v15.0极低位高胜率组合）
4. 明日交易建议
5. 推送到Bark（带图片）

版本：v3.0  2026-04-23
  - 正T策略条件同步为v15.0（极低位高胜率组合）：
    涨跌<0 + 风险<10 + 额≥5000万 + 偏离均价>0.40元 + 日振幅≥0.80元
    去掉MACD柱条件（极低位MACD已极度负值，无筛选价值）
  - BOLL带宽显示去掉%号（实际单位为元）
  - 策略条件参数与pa_monitor.py保持完全一致
"""

import os
import json
import pandas as pd
import matplotlib.pyplot as plt
import matplotlib.dates as mdates
from datetime import datetime
from pathlib import Path

# 路径管理：基于脚本位置动态计算，避免硬编码
PROJECT_DIR = Path(__file__).parent

# 设置中文字体
plt.rcParams['font.sans-serif'] = ['WenQuanYi Micro Hei', 'SimHei', 'Heiti TC', 'Arial Unicode MS', 'DejaVu Sans']
plt.rcParams['axes.unicode_minus'] = False

# ============================================================
# v15.1.2 策略参数（与pa_monitor.py保持完全一致）
# ============================================================

# 动量卖出策略
MOM_ZD_THRESH = 100           # 涨跌 > 100
MOM_RISK_THRESH = 85          # 风险 > 85
MOM_AMOUNT_THRESH_WAN = 3000  # 成交额 ≥ 3000万
MOM_MA_ABOVE = 0.10           # 股价 > 日均价 + 0.1元
MOM_MACD_THRESH = 0.06        # |MACD柱| > 0.06

# BOLL上轨补充策略（v14.0去掉带宽条件）
BOLL_AMOUNT_THRESH_WAN = 3000  # 成交额 ≥ 3000万
BOLL_MA_ABOVE = 0.10           # 股价 > 日均价 + 0.1元
BOLL_MACD_THRESH = 0.06        # MACD柱 > 0.06
BOLL_DEVIATION_THRESH = 0.3    # 偏离日均价 > 0.3元
BOLL_TOUCH_RATIO = 0.995       # 触碰上轨：最高价 ≥ BOLL上轨 × 0.995

# 冲高回落策略
PULLBACK_AMOUNT_THRESH_WAN = 3000  # 成交额 ≥ 3000万
PULLBACK_MA_ABOVE = 0.10          # 最高价 > 日均价 + 0.1元

# 正T买入策略（v15.0极低位高胜率组合，90min窗口回测91%胜率@0.20目标）
ZHENGT_ZD_THRESH = 0              # 涨跌 < 0（当天仍在下跌）
ZHENGT_RISK_THRESH = 10           # 风险 < 10（超卖确认）
ZHENGT_MA_BELOW = 0.40            # 偏离均价 > 0.40元（深度超卖，注意是price_diff > 0.40）
ZHENGT_AMOUNT_THRESH_WAN = 5000   # 成交额 ≥ 5000万（活跃资金筛选器）
ZHENGT_MIN_AMPLITUDE = 0.80       # 日振幅 ≥ 0.80元（有反弹空间）
# v15.0已去掉MACD柱条件（极低位时MACD柱已极度负值，无筛选附加价值）

# ===== 90分钟窗口回测参数 =====
EVAL_WINDOW = 90       # 评估窗口（分钟/K线数）
DAO_T_THRESH = 0.30    # 倒T达标阈值：窗口内最低价低于卖价0.30元
ZHENG_T_THRESH = 0.20  # 正T达标阈值：窗口内最高价高于买价+0.20元


def evaluate_signals_90min(df: pd.DataFrame, signal_count: int = 0, zhengt_count: int = 0) -> list:
    """
    90分钟窗口回测评估：对当天所有触发信号，评估触发后90分钟窗口内的盈亏。
    
    核心逻辑（恩洪定义）：
    - 回测盈亏 = 触发后90分钟窗口内，最低价是否低于卖出价0.30元（倒T）
    - 止损/冷却期只影响下次触发 + 风险提示，不构成回测盈亏依据
    
    Args:
        df: 当天K线数据（已计算指标）
        signal_count: 倒T信号次数（用于验证）
        zhengt_count: 正T信号次数（用于验证）
    
    Returns:
        信号评估列表
    """
    df = df.copy()
    if not pd.api.types.is_datetime64_any_dtype(df['时间']):
        df['时间'] = pd.to_datetime(df['时间'])
    
    evaluated_signals = []
    sell_active = False
    last_signal_bar = -100
    last_zhengt_bar = -100
    cooldown_bars = 30  # 与pa_monitor一致
    
    for i in range(len(df)):
        row = df.iloc[i]
        price = float(row['收盘'])
        high = float(row['最高'])
        low = float(row['最低'])
        amount_wan = float(row['成交额_万'])
        zhangdie = float(row['涨跌'])
        fengxian = float(row['风险'])
        ma = float(row['日均价'])
        macd_zhu = float(row['MACD柱'])
        boll_upper = float(row['BOLL上轨'])
        price_deviation = price - ma
        
        dt = pd.to_datetime(row['时间'])
        h, m = dt.hour, dt.minute
        # 交易时段检查
        if (h, m) < (9, 25) or (h, m) > (14, 57):
            continue
        if h == 11 and m > 30:
            continue
        if h == 12:
            continue
        if h < 13 and (h, m) > (11, 30):
            continue
        
        # 如果有活跃持仓，追踪止损/止盈（但不影响回测盈亏）
        # 只更新sell_active状态和冷却期
        if sell_active:
            # 简化：遇到止盈或止损就释放，但冷却期已由last_signal_bar控制
            sell_active = False  # 让下一个信号可以检测
            continue
        
        # 冷却期检查
        if (i - last_signal_bar) < cooldown_bars:
            continue
        
        # === 三策略检测 ===
        # 策略1: 动量
        m1 = zhangdie > MOM_ZD_THRESH
        m2 = fengxian > MOM_RISK_THRESH
        m3 = amount_wan >= MOM_AMOUNT_THRESH_WAN
        m4 = price > ma + MOM_MA_ABOVE
        m5 = abs(macd_zhu) > MOM_MACD_THRESH
        momentum_hit = m1 and m2 and m3 and m4 and m5
        
        # 策略2: BOLL
        hit_upper = high >= boll_upper * BOLL_TOUCH_RATIO
        b1 = hit_upper
        b2 = amount_wan >= BOLL_AMOUNT_THRESH_WAN
        b3 = price > ma + BOLL_MA_ABOVE
        b4 = price_deviation > BOLL_DEVIATION_THRESH
        b5 = macd_zhu > BOLL_MACD_THRESH
        boll_hit = b1 and b2 and b3 and b4 and b5
        
        # 策略3: 冲高回落（简化：额≥3000万 + 高价>均价+0.1 + 冲高回落特征）
        # 冲高回落需要前后K线比较，这里简化只检测前两个策略
        pullback_hit = False
        
        triggered = momentum_hit or boll_hit or pullback_hit
        if not triggered:
            continue
        
        strategy = '动量策略' if momentum_hit else ('BOLL补充' if boll_hit else '冲高回落')
        
        # 90分钟窗口评估
        eval_end = min(i + EVAL_WINDOW, len(df) - 1)
        if eval_end <= i:
            continue
        
        window_low = min(float(df.iloc[j]['最低']) for j in range(i + 1, eval_end + 1))
        window_low_time = None
        for j in range(i + 1, eval_end + 1):
            if float(df.iloc[j]['最低']) == window_low:
                window_low_time = str(df.iloc[j]['时间'])[-8:]
                break
        
        # 达标判定
        daoT_success = window_low <= price - DAO_T_THRESH
        daoT_profit = price - window_low
        hit_020 = window_low <= price - 0.20
        hit_025 = window_low <= price - 0.25
        
        # 止损提示（仅提示）
        stop_loss_diff = 0.20  # 缩量日
        stop_price = price + stop_loss_diff
        first_stop_time = None
        for j in range(i + 1, eval_end + 1):
            if float(df.iloc[j]['收盘']) >= stop_price:
                first_stop_time = str(df.iloc[j]['时间'])[-8:]
                break
        
        sell_active = True
        last_signal_bar = i
        
        evaluated_signals.append({
            'type': '倒T',
            'strategy': strategy,
            'time': str(row['时间'])[-8:],
            'price': price,
            'window_low': window_low,
            'window_low_time': window_low_time,
            'daoT_success': daoT_success,
            'daoT_profit': daoT_profit,
            'hit_020': hit_020,
            'hit_025': hit_025,
            'first_stop_time': first_stop_time,
            'stop_price': stop_price,
        })
    
    # 正T检测（简化）
    zhengt_active = False
    for i in range(len(df)):
        if zhengt_active:
            zhengt_active = False
            continue
        if (i - last_zhengt_bar) < cooldown_bars:
            continue
        
        row = df.iloc[i]
        price = float(row['收盘'])
        high = float(row['最高'])
        amount_wan = float(row['成交额_万'])
        zhangdie = float(row['涨跌'])
        fengxian = float(row['风险'])
        ma = float(row['日均价'])
        price_deviation = price - ma
        
        dt = pd.to_datetime(row['时间'])
        if dt.hour >= 14:
            continue
        
        z1 = zhangdie < ZHENGT_ZD_THRESH
        z2 = fengxian < ZHENGT_RISK_THRESH
        z3 = amount_wan >= ZHENGT_AMOUNT_THRESH_WAN
        z4 = price_deviation > ZHENGT_MA_BELOW  # 偏离>0.40（注意符号：价格远低于均价）
        # 简化：不检测振幅
        
        zhengt_hit = z1 and z2 and z3 and z4
        if not zhengt_hit:
            continue
        
        eval_end = min(i + EVAL_WINDOW, len(df) - 1)
        if eval_end <= i:
            continue
        
        window_high = max(float(df.iloc[j]['最高']) for j in range(i + 1, eval_end + 1))
        zhengT_success = window_high >= price + ZHENG_T_THRESH
        zhengT_profit = window_high - price
        
        zhengt_active = True
        last_zhengt_bar = i
        
        evaluated_signals.append({
            'type': '正T',
            'strategy': '正T',
            'time': str(row['时间'])[-8:],
            'price': price,
            'window_high': window_high,
            'zhengT_success': zhengT_success,
            'zhengT_profit': zhengT_profit,
        })
    
    return evaluated_signals


def generate_daily_chart(df: pd.DataFrame, output_path: str) -> bool:
    """
    生成每日策略分析图表（四图）
    """
    try:
        df = df.copy()
        df['时间'] = pd.to_datetime(df['时间'])
        
        fig, axes = plt.subplots(4, 1, figsize=(14, 12), sharex=True)
        fig.suptitle(f'{df["时间"].iloc[0].strftime("%Y-%m-%d")} 中国平安 策略指标分析', 
                     fontsize=14, fontweight='bold')
        
        # 1. 价格和BOLL带
        ax1 = axes[0]
        ax1.plot(df['时间'], df['收盘'], label='收盘价', color='black', linewidth=1.2)
        ax1.plot(df['时间'], df['BOLL上轨'], label='BOLL上轨', color='red', linestyle='--', alpha=0.7)
        ax1.plot(df['时间'], df['BOLL中轨'], label='BOLL中轨', color='blue', linestyle='--', alpha=0.7)
        ax1.plot(df['时间'], df['BOLL下轨'], label='BOLL下轨', color='green', linestyle='--', alpha=0.7)
        ax1.fill_between(df['时间'], df['BOLL上轨'], df['BOLL下轨'], alpha=0.1, color='gray')
        ax1.set_ylabel('价格')
        ax1.legend(loc='upper left', fontsize=9)
        ax1.grid(True, alpha=0.3)
        max_width = df['BOLL带宽'].max()
        ax1.set_title(f'价格与BOLL带 (今天带宽最大{max_width:.2f}元)')
        
        # 2. BOLL带宽
        ax2 = axes[1]
        ax2.plot(df['时间'], df['BOLL带宽'], color='purple', linewidth=1.2, label='BOLL带宽')
        ax2.set_ylabel('BOLL带宽(元)')
        ax2.grid(True, alpha=0.3)
        ax2.set_title(f'BOLL带宽 (v14.1已移除带宽条件)')
        
        # 3. MACD柱
        ax3 = axes[2]
        colors = ['red' if x > 0 else 'green' for x in df['MACD柱']]
        ax3.bar(df['时间'], df['MACD柱'], color=colors, width=0.003, alpha=0.7)
        ax3.axhline(y=MOM_MACD_THRESH, color='red', linestyle='--', label=f'动量阈值{MOM_MACD_THRESH}')
        ax3.axhline(y=-BOLL_MACD_THRESH, color='green', linestyle='--', label=f'BOLL阈值-{BOLL_MACD_THRESH}')
        ax3.axhline(y=0, color='black', linestyle='-', linewidth=0.5)
        ax3.set_ylabel('MACD柱')
        ax3.legend(loc='upper left', fontsize=9)
        ax3.grid(True, alpha=0.3)
        macd_above = (df['MACD柱'] > MOM_MACD_THRESH).sum()
        macd_below = (df['MACD柱'] < -BOLL_MACD_THRESH).sum()
        ax3.set_title(f'MACD柱 ({macd_above}根>{MOM_MACD_THRESH}, {macd_below}根<-{BOLL_MACD_THRESH})')
        
        # 4. 成交额
        ax4 = axes[3]
        ax4.bar(df['时间'], df['成交额_万'], color='orange', width=0.003, alpha=0.7)
        ax4.axhline(y=MOM_AMOUNT_THRESH_WAN, color='red', linestyle='--', label=f'阈值{MOM_AMOUNT_THRESH_WAN}万')
        ax4.set_ylabel('成交额(万)')
        ax4.set_xlabel('时间')
        ax4.legend(loc='upper left', fontsize=9)
        ax4.grid(True, alpha=0.3)
        amount_above = (df['成交额_万'] >= MOM_AMOUNT_THRESH_WAN).sum()
        ax4.set_title(f'成交额 ({amount_above}根K线>{MOM_AMOUNT_THRESH_WAN}万)')
        
        # 格式化x轴
        for ax in axes:
            ax.xaxis.set_major_formatter(mdates.DateFormatter('%H:%M'))
            ax.xaxis.set_major_locator(mdates.HourLocator(interval=1))
        
        plt.tight_layout()
        plt.savefig(output_path, dpi=150, bbox_inches='tight')
        plt.close()
        
        return True
    except Exception as e:
        print(f"生成图表失败: {e}")
        return False


def analyze_strategy_conditions(df: pd.DataFrame) -> dict:
    """
    v15.1.2 三策略条件满足度分析
    
    策略1 动量卖出：涨跌>100 + 风险>85 + 额≥3000万 + 股价>均价+0.1 + |MACD柱|>0.06
    策略2 BOLL补充：触碰上轨 + 额≥3000万 + 股价>均价+0.1 + 偏离>0.3 + MACD柱>0.06
    策略3 冲高回落：冲高形态 + 额≥3000万 + 最高价>均价+0.1
    正T买入（v15.0极低位高胜率组合）：涨跌<0 + 风险<10 + 额≥5000万 + 偏离均价>0.40 + 日振幅≥0.80
    """
    results = {
        # 动量卖出
        '动量_涨跌>100': 0,
        '动量_风险>85': 0,
        '动量_额≥3000万': 0,
        '动量_价>均价+0.1': 0,
        '动量_|MACD|>0.06': 0,
        '动量_满足4+/5': 0,
        '动量_全部满足': 0,
        # BOLL补充
        'BOLL_触碰上轨': 0,
        'BOLL_额≥3000万': 0,
        'BOLL_价>均价+0.1': 0,
        'BOLL_偏离>0.3': 0,
        'BOLL_MACD>0.06': 0,
        'BOLL_满足4+/5': 0,
        'BOLL_全部满足': 0,
        # 冲高回落
        '冲高_额≥3000万': 0,
        '冲高_高价>均价+0.1': 0,
        # 正T（v15.0新条件，6条件）
        '正T_涨跌≤0': 0,
        '正T_风险<10': 0,
        '正T_额≥5000万': 0,
        '正T_偏离>0.40': 0,
        '正T_振幅≥0.80': 0,
        '正T_BOLL带宽>1.0': 0,
        '正T_满足4+/6': 0,
        '正T_满足5+/6': 0,
        '正T_全部满足': 0,
    }
    
    near_signals = []
    
    # v15.3.1修复：日振幅应取全天最高价-最低价，而非单根K线的high-low
    day_high = df['最高'].max()
    day_low = df['最低'].min()
    day_amplitude = day_high - day_low
    
    for idx, row in df.iterrows():
        price = float(row['收盘'])
        high = float(row['最高'])
        low = float(row['最低'])
        amount_wan = float(row.get('成交额_万', row.get('成交额', 0) / 10000))
        avg_price = float(row['日均价']) if not pd.isna(row['日均价']) else float('inf')
        macd_bar = float(row['MACD柱']) if not pd.isna(row['MACD柱']) else 0
        boll_upper = float(row['BOLL上轨']) if not pd.isna(row['BOLL上轨']) else float('inf')
        boll_mid = float(row['BOLL中轨']) if not pd.isna(row['BOLL中轨']) else float('inf')
        boll_lower = float(row['BOLL下轨']) if not pd.isna(row['BOLL下轨']) else 0
        zhangdie = float(row.get('涨跌', 0)) if not pd.isna(row.get('涨跌', 0)) else 0
        fengxian = float(row.get('风险', 0)) if not pd.isna(row.get('风险', 0)) else 0

        price_diff = price - avg_price
        high_diff = high - avg_price
        boll_width = float(row.get('BOLL带宽', 0)) if not pd.isna(row.get('BOLL带宽', 0)) else 0
        
        # ===== 动量卖出 =====
        m_cond1 = zhangdie > MOM_ZD_THRESH
        m_cond2 = fengxian > MOM_RISK_THRESH
        m_cond3 = amount_wan >= MOM_AMOUNT_THRESH_WAN
        m_cond4 = price_diff > MOM_MA_ABOVE
        m_cond5 = abs(macd_bar) > MOM_MACD_THRESH
        
        if m_cond1: results['动量_涨跌>100'] += 1
        if m_cond2: results['动量_风险>85'] += 1
        if m_cond3: results['动量_额≥3000万'] += 1
        if m_cond4: results['动量_价>均价+0.1'] += 1
        if m_cond5: results['动量_|MACD|>0.06'] += 1
        
        m_count = sum([m_cond1, m_cond2, m_cond3, m_cond4, m_cond5])
        if m_count >= 4: results['动量_满足4+/5'] += 1
        if m_count >= 5: results['动量_全部满足'] += 1
        
        # ===== BOLL补充 =====
        # 策略判断用宽松条件(0.995)，统计显示用严格条件(>=上轨)
        b_cond1 = high >= boll_upper * BOLL_TOUCH_RATIO  # 策略触发条件
        boll_strict_touch = high >= boll_upper             # 统计显示条件
        b_cond2 = amount_wan >= BOLL_AMOUNT_THRESH_WAN
        b_cond3 = price_diff > BOLL_MA_ABOVE
        b_cond4 = price_diff > BOLL_DEVIATION_THRESH
        b_cond5 = macd_bar > BOLL_MACD_THRESH
        
        if boll_strict_touch: results['BOLL_触碰上轨'] += 1
        if b_cond2: results['BOLL_额≥3000万'] += 1
        if b_cond3: results['BOLL_价>均价+0.1'] += 1
        if b_cond4: results['BOLL_偏离>0.3'] += 1
        if b_cond5: results['BOLL_MACD>0.06'] += 1
        
        b_count = sum([b_cond1, b_cond2, b_cond3, b_cond4, b_cond5])
        if b_count >= 4: results['BOLL_满足4+/5'] += 1
        if b_count >= 5: results['BOLL_全部满足'] += 1
        
        # ===== 冲高回落 =====
        p_cond2 = amount_wan >= PULLBACK_AMOUNT_THRESH_WAN
        p_cond3 = high_diff > PULLBACK_MA_ABOVE
        
        if p_cond2: results['冲高_额≥3000万'] += 1
        if p_cond3: results['冲高_高价>均价+0.1'] += 1
        
        # ===== 正T买入（v15.0极低位高胜率组合）=====
        # 注意：price_diff = price - avg_price，当股价低于均价时为负值
        # ZHENGT_MA_BELOW=0.40 意味着偏离均价>0.40元（即price_diff < -0.40）
        # 但在pa_monitor.py中条件是 price_diff > ZHENGT_MA_BELOW（用绝对偏离）
        # 这里为统一显示，用price低于均价的绝对偏离来计算
        price_deviation = avg_price - price  # 正值=低于均价
        t_cond1 = zhangdie <= ZHENGT_ZD_THRESH               # 涨跌 ≤ 0（与pa_monitor.py cond4对齐）
        t_cond2 = fengxian < ZHENGT_RISK_THRESH              # 风险 < 10
        t_cond3 = amount_wan >= ZHENGT_AMOUNT_THRESH_WAN     # 额 ≥ 5000万
        t_cond4 = price_deviation > ZHENGT_MA_BELOW          # 偏离均价 > 0.40元
        # v15.3.1修复：使用全天真实日振幅（与pa_monitor.py盘中计算方式一致）
        bar_amplitude = day_amplitude
        t_cond5 = bar_amplitude >= ZHENGT_MIN_AMPLITUDE       # 振幅 ≥ 0.80元
        t_cond6 = boll_width > ZHENGT_MIN_BOLL_WIDTH        # BOLL带宽 > 1.0元（与pa_monitor.py cond6对齐）

        if t_cond1: results['正T_涨跌≤0'] += 1
        if t_cond2: results['正T_风险<10'] += 1
        if t_cond3: results['正T_额≥5000万'] += 1
        if t_cond4: results['正T_偏离>0.40'] += 1
        if t_cond5: results['正T_振幅≥0.80'] += 1
        if t_cond6: results['正T_BOLL带宽>1.0'] += 1

        t_count = sum([t_cond1, t_cond2, t_cond3, t_cond4, t_cond5, t_cond6])
        if t_count >= 4: results['正T_满足4+/6'] += 1
        if t_count >= 5: results['正T_满足5+/6'] += 1
        if t_count >= 6: results['正T_全部满足'] += 1
        
        # 收集接近信号（任一策略≥4条件）
        best_count = max(m_count, b_count, t_count)
        best_strategy = '动量' if m_count >= b_count and m_count >= t_count else ('BOLL' if b_count >= t_count else '正T')
        if best_count >= 4:
            near_signals.append({
                '时间': row['时间'],
                '价格': price,
                '策略': best_strategy,
                '满足条件数': best_count,
                '涨跌': zhangdie,
                '风险': fengxian,
            })
    
    return results, near_signals


def generate_enhanced_report(df: pd.DataFrame, signal_count: int = 0, 
                             zhengt_count: int = 0, prev_close: float = 0) -> tuple:
    """
    生成增强版复盘报告
    
    Args:
        df: 已计算指标的K线DataFrame
        signal_count: 倒T信号次数
        zhengt_count: 正T信号次数
        prev_close: 昨日收盘价（用于计算涨跌幅和振幅）
    
    Returns:
        (报告文本, 图表路径)
    """
    df = df.copy()
    # 确保时间是datetime类型
    if not pd.api.types.is_datetime64_any_dtype(df['时间']):
        df['时间'] = pd.to_datetime(df['时间'])
    
    # v15.2 FIX: 只取当天数据（full_df可能包含多天K线）
    today_str = df['时间'].iloc[-1].strftime('%Y-%m-%d')  # 用最后一根K线的日期
    df = df[df['时间'].dt.strftime('%Y-%m-%d') == today_str].copy()
    
    if len(df) == 0:
        return "复盘报告：无当日数据", None
    
    # 基本统计
    open_price = df['开盘'].iloc[0]
    close_price = df['收盘'].iloc[-1]
    high_price = df['最高'].max()
    low_price = df['最低'].min()
    
    # v15.2 FIX: 成交额计算统一用成交额_万列（避免单位混乱）
    if '成交额_万' in df.columns:
        total_amount = df['成交额_万'].sum() / 10000  # 万→亿
    else:
        total_amount = df['成交额'].sum() / 100000000  # 元→亿
    
    # 涨跌幅：用昨收价计算（标准算法）
    if prev_close > 0:
        change_pct = (close_price - prev_close) / prev_close * 100
        amplitude_pct = (high_price - low_price) / prev_close * 100
    else:
        # 没有昨收价时退回用开盘价
        change_pct = (close_price - open_price) / open_price * 100
        amplitude_pct = (high_price - low_price) / open_price * 100
    
    # 成交额合理性校验（防止pytdx数据异常）
    if total_amount > 200:
        # 中国平安历史最大日成交额约150亿，超过200亿一定是数据异常
        total_amount = df['成交额_万'].sum() / 10000  # 万→亿
    
    # 策略条件分析
    cond_stats, near_signals = analyze_strategy_conditions(df)
    
    # 90分钟窗口回测评估
    eval_signals = evaluate_signals_90min(df, signal_count, zhengt_count)
    
    # 生成图表
    chart_path = str(PROJECT_DIR / "daily_charts" / f"{today_str}_策略分析.png")
    Path(chart_path).parent.mkdir(parents=True, exist_ok=True)
    chart_generated = generate_daily_chart(df, chart_path)
    
    # 构建报告
    change_emoji = "🔴" if change_pct >= 0 else "🟢"
    total_bars = len(df)
    
    report = f"""📊 {today_str} 中国平安 复盘报告

【行情概况】
昨收: {prev_close:.2f}  开盘: {open_price:.2f}  收盘: {close_price:.2f}
最高: {high_price:.2f}  最低: {low_price:.2f}
涨跌幅: {change_emoji} {change_pct:+.2f}%（vs昨收）
振幅: {amplitude_pct:.2f}%（高-低/昨收）
成交额: {total_amount:.2f}亿

【策略1 动量卖出】（共{total_bars}根K线）
涨跌>100: {cond_stats['动量_涨跌>100']}次 ({cond_stats['动量_涨跌>100']/total_bars*100:.1f}%)
风险>85: {cond_stats['动量_风险>85']}次 ({cond_stats['动量_风险>85']/total_bars*100:.1f}%)
额≥3000万: {cond_stats['动量_额≥3000万']}次 ({cond_stats['动量_额≥3000万']/total_bars*100:.1f}%)
价>均价+0.1: {cond_stats['动量_价>均价+0.1']}次 ({cond_stats['动量_价>均价+0.1']/total_bars*100:.1f}%)
|MACD|>0.06: {cond_stats['动量_|MACD|>0.06']}次 ({cond_stats['动量_|MACD|>0.06']/total_bars*100:.1f}%)
接近触发(4/5): {cond_stats['动量_满足4+/5']}次 | 全部满足: {cond_stats['动量_全部满足']}次

【策略2 BOLL补充】
触碰上轨: {cond_stats['BOLL_触碰上轨']}次 ({cond_stats['BOLL_触碰上轨']/total_bars*100:.1f}%) [严格:最高价≥上轨]
额≥3000万: {cond_stats['BOLL_额≥3000万']}次 ({cond_stats['BOLL_额≥3000万']/total_bars*100:.1f}%)
价>均价+0.1: {cond_stats['BOLL_价>均价+0.1']}次 ({cond_stats['BOLL_价>均价+0.1']/total_bars*100:.1f}%)
偏离>0.3: {cond_stats['BOLL_偏离>0.3']}次 ({cond_stats['BOLL_偏离>0.3']/total_bars*100:.1f}%)
MACD>0.06: {cond_stats['BOLL_MACD>0.06']}次 ({cond_stats['BOLL_MACD>0.06']/total_bars*100:.1f}%)
接近触发(4/5): {cond_stats['BOLL_满足4+/5']}次 | 全部满足: {cond_stats['BOLL_全部满足']}次

【策略3 冲高回落】
额≥3000万: {cond_stats['冲高_额≥3000万']}次 ({cond_stats['冲高_额≥3000万']/total_bars*100:.1f}%)
高价>均价+0.1: {cond_stats['冲高_高价>均价+0.1']}次 ({cond_stats['冲高_高价>均价+0.1']/total_bars*100:.1f}%)

【正T买入】（v15.0极低位高胜率组合）
涨跌<0: {cond_stats['正T_涨跌<0']}次 ({cond_stats['正T_涨跌<0']/total_bars*100:.1f}%)
风险<10: {cond_stats['正T_风险<10']}次 ({cond_stats['正T_风险<10']/total_bars*100:.1f}%)
额≥5000万: {cond_stats['正T_额≥5000万']}次 ({cond_stats['正T_额≥5000万']/total_bars*100:.1f}%)
偏离>0.40: {cond_stats['正T_偏离>0.40']}次 ({cond_stats['正T_偏离>0.40']/total_bars*100:.1f}%)
振幅≥0.80: {cond_stats['正T_振幅≥0.80']}次 ({cond_stats['正T_振幅≥0.80']/total_bars*100:.1f}%)
接近触发(4/5): {cond_stats['正T_满足4+/5']}次 | 全部满足: {cond_stats['正T_全部满足']}次

【信号统计】
倒T卖出信号: {signal_count}次
正T买入信号: {zhengt_count}次"""

    # 添加接近信号详情（最多5个，按时间排序）
    if near_signals:
        report += f"\n\n【接近信号时刻】（任一策略≥4条件）\n"
        for sig in near_signals[:5]:
            t = sig['时间'] if isinstance(sig['时间'], str) else sig['时间'].strftime('%H:%M')
            report += f"  {t} 价{sig['价格']:.2f} {sig['策略']}({sig['满足条件数']}/5) 涨跌{sig.get('涨跌',0):.0f} 风险{sig.get('风险',0):.0f}\n"

    # ===== 90分钟窗口回测评估 =====
    if eval_signals:
        report += f"\n【90分钟窗口回测评估】（达标≤卖价-{DAO_T_THRESH}元 | 止损仅提示不影响盈亏）\n"
        for s in eval_signals:
            if s['type'] == '倒T':
                success_tag = '✅成功' if s['daoT_success'] else '❌失败'
                report += f"  🚨 {s['strategy']} @ {s['time']} 卖{s['price']:.2f}\n"
                report += f"     90min最低{s['window_low']:.2f}@{s['window_low_time']} 差价{s['daoT_profit']:+.3f}元 {success_tag}\n"
                report += f"     达标: 0.20{'✅' if s['hit_020'] else '❌'} 0.25{'✅' if s['hit_025'] else '❌'} 0.30{'✅' if s['daoT_success'] else '❌'}\n"
                if s['first_stop_time']:
                    report += f"     ⚠️止损提示: {s['first_stop_time']}@{s['stop_price']:.2f}（仅提示）\n"
            elif s['type'] == '正T':
                success_tag = '✅成功' if s['zhengT_success'] else '❌失败'
                report += f"  📈 正T @ {s['time']} 买{s['price']:.2f}\n"
                report += f"     90min最高{s['window_high']:.2f} 差价{s['zhengT_profit']:+.3f}元 {success_tag}\n"
    else:
        report += f"\n【90分钟窗口回测评估】无信号触发\n"
    
    # 明日建议
    max_width = df['BOLL带宽'].max()
    total_amount_yi = total_amount
    
    suggestions = []
    if total_amount_yi < 30:
        suggestions.append(f"极端缩量（{total_amount_yi:.1f}亿），做T目标降至0.15元")
    elif total_amount_yi < 72:
        suggestions.append(f"缩量日（{total_amount_yi:.1f}亿），审慎交易，目标0.3元")
    else:
        suggestions.append(f"量能正常（{total_amount_yi:.1f}亿），目标0.4元")
    
    if max_width < 0.5:
        suggestions.append(f"BOLL带宽仅{max_width:.2f}元，波动极低，等放量突破")
    
    if cond_stats['动量_涨跌>100'] == 0:
        suggestions.append("今日涨跌未过100，动量策略无机会")
    
    if cond_stats['正T_偏离>0.40'] > 0 and cond_stats['正T_全部满足'] == 0:
        suggestions.append(f"正T有{cond_stats['正T_偏离>0.40']}次深度偏离但其他条件不满足")
    
    if suggestions:
        report += f"\n【明日建议】\n" + "\n".join(f"• {s}" for s in suggestions)
    
    return report, chart_path if chart_generated else None


if __name__ == "__main__":
    # 测试：读取今天的数据生成报告
    import sys
    sys.path.insert(0, '.')
    from pa_monitor import calc_indicators
    
    today_str = datetime.now().strftime('%Y-%m-%d')
    csv_path = str(PROJECT_DIR / "monitor_data" / f"{today_str}.csv")
    
    if Path(csv_path).exists():
        df = pd.read_csv(csv_path)
        df = calc_indicators(df)
        report, chart = generate_enhanced_report(df, prev_close=58.03)
        print(report)
        if chart:
            print(f"\n图表已保存: {chart}")
    else:
        print(f"未找到今天数据: {csv_path}")
