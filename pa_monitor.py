"""
中国平安(601318) v16.1.2 三策略倒T+正T策略 — 实盘监控系统

v16.1.2 正T/倒T互斥解除（2026-04-27）：
  - 正T和倒T不再互斥，各自独立触发、独立冷却
  - 倒T冷却期不再阻塞正T信号判断
  - 72天回测对比：互斥14次正T vs 不互斥16次（+3个信号，100%@0.20）
  - 心跳、收盘提醒、仓位追踪均支持双向同时运行

v16.1.1 冲高回落策略v16.0重构部署（2026-04-27）：
  - 冲高回落从v14.1（8条件）重构为v16.0（6条件）
  - 去掉"高点递减×2"→改为"从盘中最高点回落>0.20元"
  - 去掉"偏离均价>0.35"→改为"盘中最高点偏离均价>0.20元"
  - 去掉"量能萎缩<80%"（与冲高互斥，冲高时往往放量）
  - 新增"收盘价偏离均价>0.20元"（过滤假冲高，价格确实在均线上方）
  - 时间窗口从9:40-11:00扩展为9:40-13:30
  - 新增day_high参数：主循环传入盘中最高价（self.daily_stats['high_price']）
  - 72天全量回测：36信号/83.3%@0.25/86.1%@0.20/均差价0.763元
  - 推送消息和接近触发日志同步更新

v16.1 正T策略优化（2026-04-27）：
  - 新增BOLL带宽>1%硬约束（回测59天/88信号：胜率从72%→83%@0.20目标）
    * BOLL>1%是最大胜率提升器（+10pp），过滤极窄带宽日的无效信号
    * 极窄带宽(BOLL<1%)意味着市场萎缩、缺乏弹性，正T反弹无力
  - 涨跌条件从<0改为≤0（覆盖平盘场景，回测差异极小+7信号/胜率不变）
  - 振幅阈值保持≥0.80元（回测4条件满足时振幅天然>0.80，降到0.70无额外信号）
  - 回测数据：振幅≥0.80+BOLL>1% → 88信号/83%@0.20/87.5%@0.15/均反弹0.546元

v15.3 90分钟窗口评估机制（2026-04-25）：
  - 核心改动：止损/冷却期不再终止信号追踪，改为90分钟窗口评估信号成败
  - 止损触发后：推送改为"⚠️风险提示，仅供参考"，不再暗示"必须操作"
  - 新增 EVAL_WINDOW_BARS=90：90分钟窗口到期后自动评估信号理论有效性
    * 倒T评估标准：窗口内最低价 < 卖出价-0.25元 → 信号成功
    * 正T评估标准：窗口内最高价 > 买入价+0.20元 → 信号成功
  - 新增窗口评估推送：90分钟到期自动推送评估结果（成功/失败）
  - 新增心跳90分钟倒计时：盘中可见信号距窗口评估还剩多少分钟
  - 止损触发后sell_active/zhengt_buy_active不再关闭，窗口到期后才关闭
  - 回测胜率数据更新：90分钟窗口下倒T@0.25=76%/正T@0.20=91%/综合@0.25=77%
  - 盘前播报增加"90分钟窗口评估"说明

v15.2 冷却期优化 + 成交额预估重构（2026-04-24）：
  - 冷却期从硬60根缩短为30根（倒T信号天然间隔>60min，缩短无历史胜率损失）
  - 新增智能冷却：信号完成（止盈/止损）后立即解锁冷却期，不再等满30根
  - 修Bug：4/24实盘10:08 BOLL信号失败后，10:09更强动量5/5信号被60根冷却期锁住
  - 正T偏离阈值保持0.40不动（回测0.35新增3信号全部失败，胜率从75%跌至57%）
  - check_buyback_and_stoploss/check_zhengt_sell_and_stoploss 新增 total_bars 参数
  - 成交额预估算法重构：上午占比法+下午线性外推 → 累计占比法（线性插值）
    * 解决13:30预估跳变问题（11:20预估34.9亿→13:30变成24.3亿）
    * 新算法：全天预估 = 累计额 / 该时刻累计占比（CUM_RATIO_TABLE + 线性插值）
    * 32天回测精度提升：09:40误差76%→25%，10:30误差30%→18%，14:30误差5%→4%
  - 新增CUM_RATIO_TABLE（10个关键节点）和_interpolate_cum_ratio()函数
  - 新交易日重置新增 self.last_signal_bar = -COOLDOWN_BARS - 1

v15.1.2 代码审查修复（2026-04-23）：
  - P0: 冲高回落接近触发日志从/6改为/8（v15.1.1新增cond7+cond8后实际8条件）
  - P0: 倒T止损措辞从"连跌保护"改为"价格反转保护"（原措辞严重误导操作方向）
  - P0: 新增收盘前正T/倒T未了结仓位提醒（避免持仓过夜无提醒）
  - P1: 版本号统一（pa_monitor/setup_monitor/healthcheck）
  - P1: daily_report_enhanced正T条件同步为v15.0新条件
  - P1: BOLL带宽显示去掉%号（实际单位为元，非百分比）
  - P1: 删除EXTREME_LOW_TARGET重复定义
  - P1: config中删除target_diff死字段
  - P2: 裸except改为except Exception
  - P2: 心跳预估复用主循环df（避免重复拉取240根K线）
  - P2: setup_monitor/healthcheck Python路径改为动态获取

v15.1.1 修复优化（2026-04-23）：
  - 冲高回落策略新增成交额≥3000万门槛（回测该策略37%失败率，主因之一为低量冲高假信号）
  - 修复P0 bug：_reset_daily_stats()覆盖consecutive_down_days和prev_close，导致正T连跌约束失效

v15.1 优化升级（2026-04-23）：
  - 新增14:00后不做正T硬约束（回测胜率仅36%，时间<40分钟不足以反弹）
  - 新增连跌>2天不做正T硬约束（回测连跌≥3天胜率骤降，1月暴跌期50% vs 其他94%）
  - 正T目标差价从动态0.30/0.40降为固定0.20元（回测0.20元目标胜率87.1%，远高于0.30元74.2%）
  - 正T止损差价设为0.15元（与0.20目标匹配）
  - 新增_calc_consecutive_down()方法，从腾讯日K线计算连跌天数
  - daily_stats新增consecutive_down_days字段

v15.0 正T策略升级（2026-04-23）：
  - 正T买入条件替换为"极低位高胜率"组合（回测76.3%胜率，93次信号）
  - 新条件：低于均价0.40元 + 风险<10 + 成交额≥5000万 + 涨跌<0
  - 去掉MACD柱条件（极低位时MACD柱已极度负值，无筛选附加价值）
  - 成交额阈值从3000万提升到5000万（最强筛选器，回测验证成交额<3000万时0.3元反弹概率极低）
  - 新增日振幅<0.8元不做正T的硬约束（4月回测证明低振幅日正T必然亏损）

v14.1 紧急修复（2026-04-23）：
  - 【紧急】修复pytdx成交额数据异常：新增腾讯API校验，当pytdx成交额偏差>2倍时自动校准
  - 【重要】修复launchd启动可靠性：KeepAlive失败重试 + 网络就绪等待 + cron新增09:25/09:35检查点
  - 【优化】策略3冲高回落条件3改为"最高价>均价+0.1"（原"收盘价>均价+0.25"在阴跌日永不满足）
  - 【修复】成交额预估算法：上午改用AM_LOW_RATIO占比法（56.7%），去掉PREOPEN_MINS硬编码和全天0.657修正系数。84天实测平均误差从31.4%降至13.6%
  - 【修复】缩量判断改为基于预估全天成交额（亿元）而非每分钟均额

v14.0 重大升级（2026-04-22）：
  - 倒T策略回归动量型：恢复v10.2涨跌+风险为主力策略（59天回测80.6%胜率）
  - BOLL上轨策略降级为补充策略（去掉带宽死条件，1分钟线带宽条件无筛选价值）
  - 三策略优先级：动量策略→BOLL补充→冲高回落（低波动日备用）
  - 原因：59天1分钟线穷举证明BOLL带宽>1.9在1分钟线上永远无法满足，
    BOLL策略胜率72.9%远低于v10.2的80.6%，信号过多（210次 vs 62次）

v13.5 修复（2026-04-15）：
  - 修复心跳预估数据不准确问题：心跳时强制实时拉取最新数据计算预估
  - 移除心跳对缓存df的依赖，确保预估全天成交额基于实时数据
  - 收盘统计同样改为实时拉取，不再使用可能过期的缓存数据

v13.4 重大升级（2026-04-10）：
  - 移除午休跳过逻辑，程序持续运行到15:00收盘
  - 修复振幅预估逻辑：预估振幅取基于成交额的预估和实际已发生振幅的较大值
  - 心跳增加当前实际振幅显示（最高价-最低价）
  - 新增动态目标差价和止损差价：根据量能环境自动调整
    * 缩量交易日（<72亿）：目标0.30元，止损0.20元
    * 非缩量交易日（≥72亿）：目标0.40元，止损0.30元
    * 极端缩量（<30亿）：目标0.15元，止损0.10元

v13.2 重大升级（2026-04-10）：
  - 新增双策略系统：高波动日BOLL上轨策略 + 低波动日冲高回落策略
  - 自动判断波动率（BOLL带宽<1.5%启用备用策略）
  - 冲高回落策略：高点递减×2 + 量能萎缩 + 远离均线 + 已从上轨回落
  - 回测基础：2026-04-10成功捕捉10:03高点（59.71卖出，59.33买回，差价0.38元）

v13.1 新增（2026-04-09）：
  - 每日收盘后自动生成增强复盘报告
  - 包含四图分析（价格/BOLL带宽/MACD/成交额）
  - 策略条件满足度统计
  - 明日交易建议

v13.0 重大升级（2026-04-08）：
  - 倒T策略升级为BOLL上轨策略（v2.3优化版）
  - 回测基础：2026-01-05至2026-04-03，73.3%胜率（0.40元目标）
  - 倒T条件：触碰BOLL上轨 + 额≥3000万 + 股价>均价+0.1 + 带宽>1.9% + 偏离>0.3 + MACD>0.06
  - 移除涨跌>100、风险>85条件，改用BOLL带宽+偏离日均价过滤
  - 保留正T买入策略（方案二参数）
  - v16.1.2：倒T和正T不再互斥，各自独立触发（正T有独立冷却期）

v12.0 历史（2026-04-08）：
  - 新增正T买入策略（方案二参数）

v11.0 改进（2026-04-07）：
  - 修复收盘后不退出持续循环推送的bug
  - 修复盘后日报数据错误（改用全天K线统计）
  - 修复风险值偶尔负数（加max(0,...)保护）
  - 修复日志双行重复（移除StreamHandler）
  - 心跳增加MACD数据（DIF/DEA/MACD柱）
  - 确保15:00心跳正常打出
  - 增加网络请求超时保护
  - 增加PID文件防重复实例
  - 收盘后自动导出全量1分钟数据到CSV
  - 收盘后程序自动退出

v10.2 倒T卖出条件（全部满足才触发）：
  1. 涨跌 > 100
  2. 风险 > 85
  3. 成交额 ≥ 3000万
  4. 股价 > 日均价 + 0.1元
  5. |MACD柱| > 0.06
  6. 时间在 09:40 ~ 14:30 内

v11.6 改进（2026-04-08）：
  - 心跳内容完整性修复：缓存所有指标（涨跌/风险/力道/成交额/量能预估），确保心跳推送内容不变少
  - 心跳逻辑简化：数据拉取前发心跳（用缓存），数据拉取后只更新缓存，不再重复发
  - Bark/企微推送强制不走代理（修复nohup启动时Bark静默失败）
  - 修复午休区间从 11:31~12:58 调整为 11:31~12:59（13:00才开盘，12:59退出午休无意义）
  - 修复12:00心跳被午休分支吞掉的问题（午休期间12:00整仍发心跳）
  - 清理pa_notify.py中未使用的no_proxy_env死代码

v11.5 改进（2026-04-08）：
  - 心跳判断移到数据拉取之前（修复数据卡住时心跳丢失的bug）
  - 新增缓存价格机制，数据拉取失败时用缓存价格发简版心跳
  - 彻底解决午休后/开盘后心跳静默问题

v11.4 改进（2026-04-08）：
  - 修复11:30心跳因K线延迟+午休竞态被吞的bug（心跳改为系统时间驱动，不依赖K线更新）
  - 午休进入时补发一个"上午收盘"心跳
  - 新增跳空修正：预估振幅自动加入跳空缺口（|开盘价-昨收价|），推送显示跳高/跳低修正幅度

v11.3 改进（2026-04-08）：
  - 振幅显示从"元"改为"百分比"（振幅/昨收价×100%）
  - Bark推送改为POST JSON，通知预览干净无参数（去掉title=, group=, sound=）
  - 盘后日报新增实际振幅百分比

v11.2 新增（2026-04-08）：
  - 修复信号判断使用未完成K线导致成交额误判的bug（改用已完成K线）
  - 新增成交额预测：每10分钟预估全天成交额（60分钟修正系数0.657）
  - 新增振幅预估：振幅 ≈ 0.0178 × 全天成交额(亿元) + 0.47元
  - 新增缩量预警：全天<30亿为极端缩量，目标差价自动降至0.15元

使用方法：
  1. pip install pytdx pandas requests
  2. 编辑 monitor_config.json，填入 bark_url 或 wechat_webhook
  3. python pa_notify.py  # 测试推送
  4. python pa_monitor.py  # 启动监控

版本：v15.3  2026-04-24
"""

import os
import sys
import json
import time
import signal
import logging
import requests
from datetime import datetime, timedelta
from pathlib import Path

# 清除代理（pytdx 用 TCP 直连）
for _k in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'ALL_PROXY', 'all_proxy']:
    os.environ.pop(_k, None)
os.environ['NO_PROXY'] = '*'
os.environ['no_proxy'] = '*'

import numpy as np
import pandas as pd
from pytdx.hq import TdxHq_API

# 导入推送模块
from pa_notify import notify

# 导入增强复盘报告模块
try:
    from daily_report_enhanced import generate_enhanced_report
    ENHANCED_REPORT_AVAILABLE = True
except ImportError:
    ENHANCED_REPORT_AVAILABLE = False

# ==================== 配置 ====================

CONFIG_PATH = Path(__file__).parent / "monitor_config.json"
PROJECT_DIR = Path(__file__).parent
PID_FILE = PROJECT_DIR / "monitor_logs" / "monitor.pid"
DATA_DIR = PROJECT_DIR / "monitor_data"

# 信号历史记录文件（API服务器读取）
SIGNAL_HISTORY_FILE = DATA_DIR / "signal_history.json"

def save_signal_to_history(signal_data: dict):
    """将信号写入历史文件，供API服务器实时读取"""
    try:
        history = []
        if SIGNAL_HISTORY_FILE.exists():
            with open(SIGNAL_HISTORY_FILE, "r", encoding="utf-8") as f:
                history = json.load(f)
        # 添加新信号到开头
        history.insert(0, signal_data)
        # 最多保留200条
        history = history[:200]
        with open(SIGNAL_HISTORY_FILE, "w", encoding="utf-8") as f:
            json.dump(history, f, ensure_ascii=False, indent=2)
    except Exception as e:
        logging.getLogger(__name__).error(f"写入信号历史失败: {e}")


def update_signal_status(signal_time: str, direction: str, status: str, profit: float = 0):
    """更新signal_history中指定信号的状态和盈亏（90分钟窗口评估后调用）"""
    try:
        if not SIGNAL_HISTORY_FILE.exists():
            return
        with open(SIGNAL_HISTORY_FILE, "r", encoding="utf-8") as f:
            history = json.load(f)
        updated = False
        for sig in history:
            if sig.get("time", "").startswith(signal_time[:16]) and sig.get("direction") == direction and sig.get("status") == "active":
                sig["status"] = status  # "成功" or "失败"
                sig["profit"] = round(profit, 2)
                sig["eval_time"] = datetime.now().strftime("%Y-%m-%d %H:%M")
                updated = True
                break
        if updated:
            with open(SIGNAL_HISTORY_FILE, "w", encoding="utf-8") as f:
                json.dump(history, f, ensure_ascii=False, indent=2)
            logging.getLogger(__name__).info(f"信号状态已更新: {signal_time} {direction} → {status}, 盈亏={profit:.2f}")
    except Exception as e:
        logging.getLogger(__name__).error(f"更新信号状态失败: {e}")


# v14.0 BOLL上轨补充策略参数（降级为补充策略）
# 59天1分钟线穷举证明：BOLL带宽条件无筛选价值（0.10~0.80元区间胜率仅差1-2%）
# v14.0去掉带宽条件，仅保留触碰上轨+量能+偏离+MACD（5条件）
BOLL_AMOUNT_THRESH_WAN = 3000    # 成交额 ≥ 3000万
BOLL_MA_ABOVE = 0.10             # 股价 > 日均价 + 0.1元
BOLL_MACD_THRESH = 0.06          # MACD柱 > 0.06
BOLL_DEVIATION_THRESH = 0.3      # 偏离日均价 > 0.3元
BOLL_TOUCH_RATIO = 0.995         # 触碰上轨：最高价 ≥ BOLL上轨 × 0.995

# ==================== 低波动日备用策略参数（冲高回落）====================
# 适用场景：BOLL带宽<1.5%的低波动日，捕捉早盘冲高回落
# 回测基础：2026-04-10，成功捕捉10:03高点（59.71卖出，59.33买回，差价0.38元）
PULLBACK_AMOUNT_THRESH_WAN = 3000  # 成交额 ≥ 3000万
PULLBACK_DAY_HIGH_DEVIATION = 0.20  # v16.0: 盘中最高点偏离均价>0.20元
PULLBACK_PULLBACK_FROM_HIGH = 0.20  # v16.0: 从盘中最高点回落>0.20元
PULLBACK_CLOSE_ABOVE_AVG = 0.20    # v16.0: 收盘价偏离均价>0.20元（过滤假冲高）
PULLBACK_START = (9, 40)         # 策略启动时间
PULLBACK_END = (13, 30)          # v16.0: 策略结束时间（扩展到下午，原11:00）
PULLBACK_BANDWIDTH_THRESH = 1.5  # BOLL带宽阈值，低于此值启用备用策略

# v14.0 动量策略参数（主力策略，恢复v10.2逻辑）
# 回测基础：2026-01-05至2026-04-03，59天14160根K线，62信号/80.6%胜率(0.25)/均差0.517
ZHANGDIE_THRESH = 100      # 涨跌 > 100
FENGXIAN_THRESH = 85       # 风险 > 85
MA_ABOVE = 0.10            # 股价 > 日均价 + 0.1元
MACD_BAR_THRESH = 0.06     # |MACD柱| > 0.06

# 正T策略共用参数
AMOUNT_THRESH_WAN = 3000    # 成交额 ≥ 3000万（正T与倒T共用）

# 正T策略参数（买入）- v16.1 极低位高胜率组合 + BOLL带宽约束
# 回测基础：2026-01-02至2026-04-03，59天156信号→88信号（BOLL>1%过滤43%噪音）
# 60分钟窗口：76.3%胜率，93次信号 | 90分钟窗口：83%胜率@0.20目标，88次信号
# v16.1: 新增BOLL带宽>1%约束（胜率从72%→83%），涨跌从<0改为≤0
# 核心逻辑：极低位深跌+活跃资金+超卖确认 → 0.20元反弹概率极高
ZHENGT_MA_BELOW = 0.40      # 股价 < 日均价 - 0.40元（深度偏离）
ZHENGT_RISK_THRESH = 10     # 风险 < 10（超卖确认）
ZHENGT_AMOUNT_THRESH_WAN = 5000  # 成交额 ≥ 5000万（活跃资金筛选器）
ZHENGT_ZD_THRESH = 0        # 涨跌 ≤ 0（当天仍在下跌或平盘）
# 新增：日振幅硬约束
ZHENGT_MIN_AMPLITUDE = 0.80  # 日振幅 < 0.80元 不做正T
# v16.1新增：BOLL带宽硬约束（回测BOLL>1%时胜率从72%→83%）
ZHENGT_MIN_BOLL_WIDTH = 1.0  # BOLL带宽 ≤ 1.0% 不做正T（极窄带宽=市场萎缩，反弹无力）
# v15.1新增：时间硬约束 + 连跌硬约束
ZHENGT_LATEST_HOUR = 14     # 14:00后不做正T（回测14:00后胜率仅36%）
ZHENGT_MAX_CONSEC_DOWN = 2  # 连跌>2天（即第3天起）不做正T（回测连跌≥3天胜率骤降）

TRADE_START = (9, 40)       # 09:40 开始监控（跳过开盘10分钟波动，避免虚假信号）
TRADE_END = (14, 30)        # 14:30 截止（14:30后信号胜率极低，v11.6回测验证）
COOLDOWN_BARS = 30          # 冷却期30根K线≈30分钟（v15.2: 60→30，配合智能冷却——信号完成/失败后立即解锁）
EVAL_WINDOW_BARS = 90       # 90分钟窗口评估（v15.3: 止损不终止追踪，窗口到期才判定信号成败；90→120仅+1.8pp性价比拐点）
WARMUP_BARS = 350           # 指标预热期：主力指标最长窗口27+5+5+3+5=45，实测350根确保指标稳定

# ==================== 动态目标差价 & 止损差价配置 ====================
# 根据量能环境自动调整：缩量日目标低、止损紧；非缩量日目标高、止损宽
# 缩量判断标准：每分钟均成交额 < VOLUME_LOW_LINE (3000万)

# 缩量交易日（<72亿）
TARGET_DIFF_LOW_VOLUME = 0.30      # 目标差价 0.30元（3毛）
STOP_LOSS_DIFF_LOW_VOLUME = 0.20   # 止损差价 0.20元（2毛）

# 非缩量交易日（≥72亿）
TARGET_DIFF_NORMAL = 0.40          # 目标差价 0.40元（4毛）
STOP_LOSS_DIFF_NORMAL = 0.30       # 止损差价 0.30元（3毛）

# 极端缩量（<30亿）- 定义见L265，此处不再重复

# v15.1: 正T专用目标差价（90分钟窗口回测0.20元目标胜率91%，远高于0.30元的74.2%）
# 正T逻辑：低位买入→反弹卖出，0.20元更现实（失败案例反弹中位数0.195元）
ZHENGT_TARGET_DIFF = 0.20          # 正T目标差价 0.20元
ZHENGT_STOP_LOSS_DIFF = 0.15       # 正T止损差价 0.15元

# 向后兼容的默认参数（实际使用时会根据量能动态获取）
TARGET_DIFF = TARGET_DIFF_LOW_VOLUME      # 默认使用缩量参数（保守）
STOP_LOSS_DIFF = STOP_LOSS_DIFF_LOW_VOLUME  # 默认使用缩量参数（保守）

# 成交额预测 & 振幅预估参数（基于32个交易日1分钟线统计）
# v15.2: 累计占比法替代上午/下午分段法
# 核心逻辑：全天预估 = 累计额 / 该时刻累计占比（线性插值）
# 优点：①自然反映下午量能衰减 ②尾盘放量自动包含 ③无需区分上午/下午
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
# 保留旧常量兼容（某些日志/注释可能引用）
AM_LOW_RATIO = 57.8         # 上午成交额占全天比例（%），32天统计
PM_LOW_RATIO = 42.2         # 下午成交额占全天比例（%）
# 振幅映射：振幅 ≈ 0.0178 × 全天成交额(亿元) + 0.47元
AMP_SLOPE = 0.0178
AMP_INTERCEPT = 0.47
# 缩量阈值
VOLUME_LOW_LINE = 3000      # 每分钟均成交额3000万 → 全天72亿
EXTREME_LOW_LINE = 1250     # 每分钟均成交额1250万 → 全天30亿（极端缩量）
EXTREME_LOW_TARGET = 0.15   # 极端缩量时做T目标差价降到0.15元

# 通达信服务器
TDX_SERVERS = [
    ('180.153.18.170', 7709),
    ('119.147.212.81', 7709),
    ('112.74.214.43', 7709),
    ('221.231.141.60', 7709),
    ('101.227.73.20', 7709),
    ('101.227.77.254', 7709),
    ('14.215.128.18', 7709),
    ('59.173.18.140', 7709),
    ('47.103.48.45', 7709),
]

# ==================== PID文件（防重复实例） ====================

def acquire_pid():
    """写入PID文件，防止重复启动"""
    PID_FILE.parent.mkdir(parents=True, exist_ok=True)
    if PID_FILE.exists():
        try:
            old_pid = int(PID_FILE.read_text().strip())
            # 检查旧进程是否还活着
            os.kill(old_pid, 0)
            # 进一步验证：该PID是否真的是pa_monitor进程（避免cron自检残留PID冲突）
            try:
                import subprocess
                cmd_line = subprocess.run(
                    ['ps', '-p', str(old_pid), '-o', 'args='],
                    capture_output=True, text=True, timeout=2
                ).stdout.strip()
                if 'pa_monitor' not in cmd_line:
                    # PID被其他进程复用，安全覆盖
                    print(f"⚠️ PID文件残留（PID {old_pid}非pa_monitor进程），自动覆盖")
                    PID_FILE.write_text(str(os.getpid()))
                    return PID_FILE
            except Exception:
                pass  # 无法验证时保守处理
            print(f"❌ 监控已在运行中 (PID: {old_pid})，请先停止再启动")
            sys.exit(1)
        except (ProcessLookupError, ValueError):
            pass  # 旧进程已死，可以覆盖
    PID_FILE.write_text(str(os.getpid()))
    return PID_FILE

def release_pid():
    """释放PID文件"""
    try:
        if PID_FILE.exists():
            pid_in_file = int(PID_FILE.read_text().strip())
            if pid_in_file == os.getpid():
                PID_FILE.unlink()
    except Exception:
        pass

# ==================== 日志 ====================

def setup_logging():
    """配置日志系统（仅文件，不输出到stdout避免nohup双行）"""
    config = load_config()
    log_dir = Path(config.get("log_dir", str(PROJECT_DIR / "monitor_logs")))
    log_dir.mkdir(parents=True, exist_ok=True)

    today = datetime.now().strftime("%Y-%m-%d")
    log_file = log_dir / f"monitor_{today}.log"

    # 清理30天前的日志
    for old_log in log_dir.glob("monitor_*.log"):
        try:
            file_date = old_log.stem.replace("monitor_", "")
            file_dt = datetime.strptime(file_date, "%Y-%m-%d")
            if (datetime.now() - file_dt).days > 30:
                old_log.unlink()
        except Exception:
            pass

    logger = logging.getLogger("PA_Monitor")
    logger.setLevel(logging.INFO)
    # 仅文件handler，不输出stdout（避免nohup重复）
    handler = logging.FileHandler(log_file, encoding="utf-8")
    handler.setFormatter(logging.Formatter("%(asctime)s [%(levelname)s] %(message)s"))
    logger.addHandler(handler)
    return logger


# ==================== 配置加载 ====================

def load_config() -> dict:
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


# ==================== 通达信数据获取 ====================

class TdxClient:
    """通达信行情客户端，带自动重连、超时保护和成交额校验"""

    # v14.1: 成交额校验相关常量
    # pytdx的amount字段单位是"元"（正确），但有时返回异常偏低值
    # 中国平安1分钟正常成交额范围：500万~8000万（极端行情可达1亿+）
    # 低于50万（<0.05亿）的1分钟成交额几乎不可能出现在交易时段
    AMOUNT_SANITY_MIN_WAN = 50        # 单根1分钟线成交额低于50万视为可疑
    AMOUNT_CALIBRATION_ROUNDS = 3     # 连续几次可疑后触发校准
    TENCENT_API_URL = "https://web.ifzq.gtimg.cn/appstock/app/minute/query"

    def __init__(self, market=1, symbol="601318"):
        self.market = market
        self.symbol = symbol
        self.api = TdxHq_API()
        self.connected = False
        self._last_activity = time.time()  # 最后活动时间，用于检测卡死
        self._timeout = 120  # 120秒无活动视为卡死
        
        # v14.1: 成交额校验状态
        self._suspect_count = 0          # 连续可疑数据计数
        self._calibration_mode = False   # 是否进入校准模式（使用腾讯API）
        self._calibration_ratio = 1.0    # 校准系数（腾讯成交额/pytdx成交额）
        self._calibration_checked_today = False  # 今日是否已做过初始校准

    def touch(self):
        """更新最后活动时间"""
        self._last_activity = time.time()

    def is_stale(self):
        """检查是否卡死"""
        return (time.time() - self._last_activity) > self._timeout

    def connect(self):
        """连接通达信服务器"""
        for ip, port in TDX_SERVERS:
            try:
                if self.api.connect(ip, port, time_out=10):
                    self.connected = True
                    self.touch()
                    return True
            except Exception:
                continue
        self.connected = False
        return False

    def reconnect(self):
        """重连"""
        try:
            self.api.disconnect()
        except Exception:
            pass
        time.sleep(1)
        self.api = TdxHq_API()
        return self.connect()

    def get_latest_bars(self, count=100, timeout=10):
        """
        获取最近 count 根1分钟K线
        返回 DataFrame，列: 时间, 开盘, 收盘, 最高, 最低, 成交量, 成交额
        timeout: 超时时间（秒）
        """
        if not self.connected:
            if not self.reconnect():
                return None

        try:
            self.touch()
            # 通达信获取最近K线，从最新的往前取
            all_bars = []
            # 每次最多800条，取2个800覆盖全天
            for start in [0, 800]:
                # 设置socket超时防止阻塞
                import socket
                old_timeout = socket.getdefaulttimeout()
                socket.setdefaulttimeout(timeout)
                try:
                    data = self.api.get_security_bars(8, self.market, self.symbol, start, 800)
                    if data:
                        all_bars.extend(data)
                except socket.timeout:
                    logging.warning(f"获取K线超时({timeout}s)")
                    socket.setdefaulttimeout(old_timeout)
                    return None
                finally:
                    socket.setdefaulttimeout(old_timeout)
                time.sleep(0.1)

            if not all_bars:
                return None

            # 转换为 DataFrame
            records = []
            for bar in all_bars:
                records.append({
                    '时间': bar['datetime'],
                    '开盘': float(bar['open']),
                    '收盘': float(bar['close']),
                    '最高': float(bar['high']),
                    '最低': float(bar['low']),
                    '成交量': int(bar['vol']),
                    '成交额': float(bar['amount']),
                })

            df = pd.DataFrame(records)
            # 去重、排序
            df.drop_duplicates(subset=['时间'], keep='first', inplace=True)
            df.sort_values('时间', inplace=True)
            df.reset_index(drop=True, inplace=True)

            # 只返回最近 count 条（保留足够预热数据）
            if len(df) > count:
                df = df.iloc[-count:].reset_index(drop=True)

            # v14.1: 成交额校验 —— 首次拉取时用腾讯API校准
            if not self._calibration_checked_today:
                today = datetime.now().strftime("%Y-%m-%d")
                today_rows = df[df['时间'].astype(str).str.startswith(today)]
                if len(today_rows) >= 10:
                    # 有足够今日数据，执行校准
                    df = self._calibrate_amount_from_tencent(df)
                    self._calibration_checked_today = True
                else:
                    # 数据还不够，先做一个快速合理性检查
                    # 如果今日交易时段内单分钟成交额普遍低于50万，标记可疑
                    trading_rows = today_rows[
                        today_rows['时间'].astype(str).str.contains(r' (09|10|11|13|14):')
                    ]
                    if len(trading_rows) > 0:
                        low_amount_count = sum(1 for _, r in trading_rows.iterrows() 
                                              if float(r['成交额']) / 10000 < self.AMOUNT_SANITY_MIN_WAN)
                        if low_amount_count > len(trading_rows) * 0.5:
                            # 超过一半的1分钟线成交额低于50万，极可能异常
                            self._suspect_count += 1
                            logging.warning(
                                f"⚠️ pytdx成交额可疑: {low_amount_count}/{len(trading_rows)}根K线"
                                f"成交额<{self.AMOUNT_SANITY_MIN_WAN}万 (可疑计数={self._suspect_count})"
                            )
                            if self._suspect_count >= self.AMOUNT_CALIBRATION_ROUNDS:
                                df = self._calibrate_amount_from_tencent(df)
                                self._calibration_checked_today = True

            return df

        except Exception as e:
            logging.error(f"获取K线失败: {e}")
            self.connected = False
            return None

    def _fetch_tencent_minute_data(self):
        """
        v14.1: 从腾讯API获取分时成交数据，用于校准pytdx的成交额异常
        
        腾讯分时API返回格式:
          min_data={"code":0,"data":{"sh601318":{"data":{"data":["0930 57.98 2188 12686024.00","0931 ..."], ...}}}}
          每行: "时间 价格 累计成交量 累计成交额(元)"
        
        返回: dict {时间字符串(如"09:31"): 单分钟成交额(元)} 或 None
        """
        try:
            prefix = "sh" if self.market == 1 else "sz"
            url = f"{self.TENCENT_API_URL}?_var=min_data&code={prefix}{self.symbol}"
            resp = requests.get(url, timeout=10, proxies={"http": None, "https": None})
            if resp.status_code != 200:
                return None
            
            text = resp.text
            # 解析JSONP: min_data={...}
            json_str = text.split("=", 1)[1].strip() if "=" in text else text
            data = json.loads(json_str)
            
            if not data or "data" not in data:
                return None
            
            # 提取分时数据数组
            stock_key = f"{prefix}{self.symbol}"
            minute_list = None
            for key, val in data["data"].items():
                if isinstance(val, dict) and "data" in val:
                    inner = val["data"]
                    if isinstance(inner, dict) and "data" in inner:
                        minute_list = inner["data"]
                        break
                    elif isinstance(inner, list):
                        minute_list = inner
                        break
            
            if not minute_list or len(minute_list) < 3:
                return None
            
            # 解析每行: "0930 57.98 2188 12686024.00"
            # 计算: 单分钟成交额 = 当前累计 - 前一根累计
            result = {}
            for i, line in enumerate(minute_list):
                parts = line.split()
                if len(parts) < 4:
                    continue
                
                time_raw = parts[0]  # "0930"
                # 转换为pytdx匹配格式 "09:30"
                time_key = f"{time_raw[:2]}:{time_raw[2:]}"
                
                cum_amount = float(parts[3])  # 累计成交额（元）
                
                if i == 0:
                    single_amount = cum_amount
                else:
                    prev_parts = minute_list[i - 1].split()
                    if len(prev_parts) >= 4:
                        prev_cum = float(prev_parts[3])
                        single_amount = cum_amount - prev_cum
                    else:
                        continue
                
                result[time_key] = single_amount  # 单位：元
            
            return result
            
        except Exception as e:
            logging.warning(f"腾讯API获取分时数据失败: {e}")
            return None
    
    def _calibrate_amount_from_tencent(self, df):
        """
        v14.1: 用腾讯API数据校准pytdx的成交额
        
        策略：
        1. 从腾讯获取今日分时累计成交额
        2. 与pytdx对应时间段的成交额对比
        3. 如果偏差超过2倍，计算校准系数并应用
        
        参数: df - pytdx返回的DataFrame（含'时间'和'成交额'列）
        返回: 校准后的DataFrame（原地修改成交额列）
        """
        tencent_data = self._fetch_tencent_minute_data()
        if not tencent_data:
            return df
        
        today = datetime.now().strftime("%Y-%m-%d")
        
        # 找出今日pytdx数据与腾讯数据的交集
        tdx_total = 0  # pytdx今日累计成交额
        tencent_total = 0  # 腾讯今日累计成交额
        match_count = 0
        
        for idx, row in df.iterrows():
            time_str = str(row['时间'])
            if not time_str.startswith(today):
                continue
            
            # pytdx时间格式: "2026-04-23 09:31"
            # 腾讯时间格式: "09:31"
            time_part = time_str.split(' ')[1] if ' ' in time_str else ''
            
            if time_part in tencent_data:
                tdx_total += float(row['成交额'])
                tencent_total += float(tencent_data[time_part])
                match_count += 1
        
        if match_count < 3 or tdx_total <= 0:
            return df
        
        ratio = tencent_total / tdx_total
        
        if ratio > 2.0 or ratio < 0.5:
            # 偏差超过2倍，需要校准
            self._calibration_ratio = ratio
            self._calibration_mode = True
            logging.warning(
                f"⚠️ pytdx成交额异常！腾讯/tdx比值={ratio:.1f}x "
                f"(腾讯={tencent_total/10000:.0f}万 vs tdx={tdx_total/10000:.0f}万, "
                f"匹配{match_count}根K线)，启用校准系数{ratio:.2f}"
            )
            # 应用校准系数
            df = df.copy()
            df['成交额'] = df['成交额'] * ratio
            # 同时校准成交量（近似，用成交额比例）
            df['成交量'] = (df['成交量'] * ratio).astype(int)
        else:
            # 数据正常，无需校准
            self._calibration_mode = False
            self._calibration_ratio = 1.0
            logging.info(f"✅ pytdx成交额校验通过（腾讯/tdx比值={ratio:.2f}x，匹配{match_count}根K线）")
        
        return df

    def disconnect(self):
        try:
            self.api.disconnect()
        except Exception:
            pass
        self.connected = False


# ==================== 指标计算 ====================

def sma_wilder(series, period, weight):
    """Wilder 平滑（SMA 变体）"""
    result = np.full(len(series), np.nan)
    for i in range(len(series)):
        if np.isnan(series[i]):
            continue
        if i == 0 or np.isnan(result[i-1]):
            result[i] = series[i]
        else:
            result[i] = (result[i-1] * (period - weight) + series[i] * weight) / period
    return result

def ema(series, period):
    return sma_wilder(series, period, 2)

def llv(series, period):
    result = np.full(len(series), np.nan)
    for i in range(len(series)):
        start = max(0, i - period + 1)
        window = series[start:i+1]
        valid = window[~np.isnan(window)]
        if len(valid) > 0:
            result[i] = np.min(valid)
    return result

def hhv(series, period):
    result = np.full(len(series), np.nan)
    for i in range(len(series)):
        start = max(0, i - period + 1)
        window = series[start:i+1]
        valid = window[~np.isnan(window)]
        if len(valid) > 0:
            result[i] = np.max(valid)
    return result

def ma_simple(series, period):
    result = np.full(len(series), np.nan)
    for i in range(period - 1, len(series)):
        window = series[i - period + 1:i + 1]
        if not np.any(np.isnan(window)):
            result[i] = np.mean(window)
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
    llv27 = llv(l, 27); hhv27 = hhv(h, 27)
    raw27 = np.full(n, np.nan)
    for i in range(n):
        denom = hhv27[i] - llv27[i]
        if denom > 0: raw27[i] = (c[i] - llv27[i]) / denom * 100
    fast27 = sma_wilder(raw27, 5, 1); slow27 = sma_wilder(fast27, 5, 1)
    diff27 = fast27 * 3 - slow27 * 2
    zhangdie = ma_simple(sma_wilder(diff27, 3, 1), 5)

    # === 风险指标（v11.0: 加max(0,...)保护，防止负数） ===
    llv21 = llv(l, 21); hhv21 = hhv(h, 21)
    var8 = np.full(n, np.nan)
    for i in range(n):
        denom = hhv21[i] - llv21[i]
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
    # VAR2 = (CLOSE - LLV(LOW,24)) / (HHV(HIGH,24) - LLV(LOW,24)) * 2000
    # 买卖力道 = SMA(VAR2, 3, 1)
    # 含义：价格在近期24根K线波动区间的位置，正值=买方主导，负值=卖方主导
    llv24 = llv(l, 24)
    hhv24 = hhv(h, 24)
    var2 = np.full(n, np.nan)
    for i in range(n):
        denom = hhv24[i] - llv24[i]
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


# ==================== v10.2 策略判断 ====================

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
    return (h, m) >= TRADE_START and (h, m) <= TRADE_END




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
    price = float(row['收盘'])
    high = float(row['最高'])
    amount_wan = float(row['成交额_万'])
    avg_price = float(row['日均价']) if not np.isnan(row['日均价']) else 0
    macd_bar = float(row['MACD柱']) if not np.isnan(row['MACD柱']) else 0
    boll_upper = float(row['BOLL上轨']) if not np.isnan(row['BOLL上轨']) else 0
    boll_width = float(row['BOLL带宽']) if not np.isnan(row['BOLL带宽']) else 0
    
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
    cond1 = high >= boll_upper * BOLL_TOUCH_RATIO  # 触碰BOLL上轨
    cond2 = amount_wan >= BOLL_AMOUNT_THRESH_WAN    # 成交额≥3000万
    cond3 = price_diff > BOLL_MA_ABOVE              # 股价>日均价+0.1
    cond4 = price_diff > BOLL_DEVIATION_THRESH      # 偏离日均价>0.3元
    cond5 = macd_bar > BOLL_MACD_THRESH             # MACD柱>0.06
    
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
    price = float(row['收盘'])
    zhangdie = float(row['涨跌']) if not np.isnan(row['涨跌']) else 0
    fengxian = float(row['风险']) if not np.isnan(row['风险']) else 0
    amount_wan = float(row['成交额_万'])
    avg_price = float(row['日均价']) if not np.isnan(row['日均价']) else 0
    macd_bar = float(row['MACD柱']) if not np.isnan(row['MACD柱']) else 0
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
    cond1 = zhangdie > ZHANGDIE_THRESH
    cond2 = fengxian > FENGXIAN_THRESH
    cond3 = amount_wan >= AMOUNT_THRESH_WAN
    cond4 = price_diff > MA_ABOVE
    cond5 = macd_abs > MACD_BAR_THRESH

    details['满足条件'] = {
        f'涨跌>{ZHANGDIE_THRESH}': cond1,
        f'风险>{FENGXIAN_THRESH}': cond2,
        f'成交额≥{AMOUNT_THRESH_WAN}万': cond3,
        f'股价>均价+{MA_ABOVE}': cond4,
        f'|MACD柱|>{MACD_BAR_THRESH}': cond5,
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
    price = float(row['收盘'])
    zhangdie = float(row['涨跌']) if not np.isnan(row['涨跌']) else 0
    fengxian = float(row['风险']) if not np.isnan(row['风险']) else 0
    amount_wan = float(row['成交额_万'])
    avg_price = float(row['日均价']) if not np.isnan(row['日均价']) else 0
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
    cond1 = price_diff > ZHENGT_MA_BELOW           # 偏离均价 > 0.40元（深度超卖）
    cond2 = fengxian < ZHENGT_RISK_THRESH           # 风险 < 10（超卖确认）
    cond3 = amount_wan >= ZHENGT_AMOUNT_THRESH_WAN   # 成交额 ≥ 5000万（活跃资金）
    cond4 = zhangdie <= ZHENGT_ZD_THRESH              # 涨跌 ≤ 0（仍在下跌或平盘）
    cond5 = amplitude >= ZHENGT_MIN_AMPLITUDE         # 日振幅 ≥ 0.80元（有反弹空间）
    cond6 = boll_width > ZHENGT_MIN_BOLL_WIDTH       # BOLL带宽 > 1.0%（市场有弹性，非萎缩态）

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
    
    price = float(current['收盘'])
    high = float(current['最高'])
    amount_wan = float(current['成交额_万'])
    avg_price = float(current['日均价']) if not np.isnan(current['日均价']) else 0
    boll_upper = float(current['BOLL上轨']) if not np.isnan(current['BOLL上轨']) else 0
    boll_width = float(current['BOLL带宽']) if not np.isnan(current['BOLL带宽']) else 0
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
    in_time_window = (PULLBACK_START <= (h, m) <= PULLBACK_END)
    
    # v16.0 冲高回落条件（6个条件，精简重构）
    cond1 = high_diff_from_avg > PULLBACK_DAY_HIGH_DEVIATION  # 盘中最高点偏离均价>0.20元
    cond2 = pullback_from_high > PULLBACK_PULLBACK_FROM_HIGH   # 从最高点回落>0.20元
    cond3 = close_diff > PULLBACK_CLOSE_ABOVE_AVG              # 收盘偏离均价>0.20元
    cond4 = amount_wan >= PULLBACK_AMOUNT_THRESH_WAN           # 成交额≥3000万
    cond5 = price < boll_upper                                  # 已从BOLL上轨回落
    cond6 = in_time_window                                      # 时间窗口9:40-13:30

    details['满足条件'] = {
        f'盘中最高偏离均价>{PULLBACK_DAY_HIGH_DEVIATION}({high_diff_from_avg:+.3f})': cond1,
        f'从高点回落>{PULLBACK_PULLBACK_FROM_HIGH}({pullback_from_high:+.3f})': cond2,
        f'收盘偏离均价>{PULLBACK_CLOSE_ABOVE_AVG}({close_diff:+.3f})': cond3,
        f'成交额≥{PULLBACK_AMOUNT_THRESH_WAN}万({amount_wan:.0f})': cond4,
        '已从上轨回落': cond5,
        f'在时间窗口{PULLBACK_START[0]}:{PULLBACK_START[1]:02d}-{PULLBACK_END[0]}:{PULLBACK_END[1]:02d}': cond6,
    }
    details['全部满足'] = all([cond1, cond2, cond3, cond4, cond5, cond6])
    details['满足数量'] = sum([cond1, cond2, cond3, cond4, cond5, cond6])
    
    return details['全部满足'], details


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
    actual_high = float(today_df['最高'].max())
    actual_low = float(today_df['最低'].min())
    actual_amplitude = actual_high - actual_low
    
    # 振幅预估（基于成交额）
    estimated_amplitude_from_volume = AMP_SLOPE * estimated_daily_yi + AMP_INTERCEPT
    
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
    
    suggested_target = EXTREME_LOW_TARGET if is_extreme_low else TARGET_DIFF
    
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

class PAMonitor:
    """中国平安 v15.2 三策略倒T+正T策略监控器"""

    def __init__(self):
        self.config = load_config()
        self.logger = setup_logging()
        self.tdx = TdxClient(
            market=self.config.get("market", 1),
            symbol=self.config.get("stock_code", "601318"),
        )
        self.last_signal_bar = -COOLDOWN_BARS - 1
        self.signal_count_today = 0
        self.running = True
        self.daily_report_sent = False  # v11.0: 防止重复发日报

        # === 日内数据记录（用于CSV导出） ===
        self.daily_bars = []  # 存储今天所有已处理K线的指标数据

        # === 日报统计 ===
        self.daily_stats = {
            'near_trigger_count': 0,
            'max_boll_upper': 0,
            'max_boll_width': 0,
            'max_macd': 0,
            'max_amount_wan': 0,
            'open_price': None,
            'close_price': None,
            'high_price': None,
            'low_price': None,
            'total_amount_wan': 0,
            'prev_close': 0,  # 昨收价，用于振幅百分比计算
            'consecutive_down_days': 0,  # v15.1: 连跌天数（用于正T约束）
        }

        # === 卖出后追踪 ===
        self.sell_active = False
        self.sell_price = 0
        self.sell_time = ""
        self.target_buy_price = 0
        self.stop_loss_price = 0
        self.buyback_notified = False
        self.sell_stop_loss_triggered = False  # v15.3: 止损已触发，但90分钟窗口评估未结束
        self.sell_signal_bar = 0               # v15.3: 倒T信号触发的bar编号，用于90分钟窗口倒计时
        self.sell_eval_notified = False         # v15.3: 90分钟窗口评估结果已推送
        self.sell_window_min_price = None      # 90分钟窗口内最低价追踪

        # === 正T买入后追踪 ===
        self.zhengt_buy_active = False  # 正T买入后待卖出状态
        self.zhengt_buy_price = 0
        self.zhengt_buy_time = ""
        self.zhengt_target_sell_price = 0  # 目标卖出价
        self.zhengt_stop_loss_price = 0    # 止损价
        self.zhengt_sell_notified = False
        self.zhengt_stop_loss_triggered = False  # v15.3: 正T止损已触发，但90分钟窗口评估未结束
        self.zhengt_signal_bar = 0               # v15.3: 正T信号触发的bar编号，用于90分钟窗口倒计时
        self.zhengt_eval_notified = False         # v15.3: 正T90分钟窗口评估结果已推送
        self.zhengt_window_max_price = None      # 90分钟窗口内最高价追踪

        # 信号计数
        self.zhengt_signal_count_today = 0  # 正T信号计数
        self.last_zhengt_signal_bar = 0

        # 信号处理
        signal.signal(signal.SIGINT, self._shutdown)
        signal.signal(signal.SIGTERM, self._shutdown)

    def _shutdown(self, signum, frame):
        self.logger.info("收到停止信号，正在关闭...")
        self.running = False

    def is_trading_day(self):
        """判断今天是否是A股交易日，同时获取昨收价"""
        today = datetime.now()
        if today.weekday() >= 5:
            return False

        # v15.3.1: 增加重试机制，避免网络抖动导致误判
        max_retries = 3
        for attempt in range(max_retries):
            try:
                date_str = today.strftime("%Y-%m-%d")
                url = "https://push2his.eastmoney.com/api/qt/stock/kline/get"
                params = {
                    "secid": "1.601318",
                    "fields1": "f1,f2,f3,f4,f5,f6",
                    "fields2": "f51,f52,f53,f54,f55,f56,f57",
                    "klt": "101",
                    "fqt": "1",
                    "beg": "0",
                    "end": "20500101",
                    "lmt": "5",
                }
                resp = requests.get(url, params=params, timeout=10, proxies={"http": None, "https": None})
                data = resp.json()
                if data and data.get("data") and data["data"].get("klines"):
                    klines = data["data"]["klines"]
                    # 从日K线获取昨收价：最后一条K线的收盘价就是昨收价（今天是最新一条）
                    for line in klines:
                        kline_date = line.split(",")[0]
                        if kline_date == date_str:
                            # 找到今天的K线，取前一条的收盘价作为昨收价
                            idx = klines.index(line)
                            if idx >= 1:
                                prev_close = float(klines[idx - 1].split(",")[2])
                                self.daily_stats['prev_close'] = prev_close
                            # v15.1: 计算连跌天数（从最近的日K往前数）
                            self._calc_consecutive_down(klines)
                            return True
                    # 今天K线还未生成（开盘前）：最后一条K线是昨天
                    now_h = today.hour
                    now_m = today.minute
                    is_before_open = (now_h * 60 + now_m) < (9 * 60 + 30)
                    if is_before_open:
                        # 开盘前，今天K线未生成是正常的，取最后一条K线的收盘价作为昨收价
                        if klines:
                            prev_close = float(klines[-1].split(",")[2])
                            self.daily_stats['prev_close'] = prev_close
                            self.logger.info(f"开盘前，今日K线未生成属正常，昨收价={prev_close}，判断为交易日")
                        # v15.1: 开盘前也算连跌（基于昨日K线）
                        self._calc_consecutive_down(klines)
                        return True
                    self.logger.info(f"今天 {date_str} 不在近5个交易日K线中，判断为休市")
                    return False
                # 数据为空，可能是网络问题
                self.logger.warning(f"东方财富返回数据为空，第{attempt+1}/{max_retries}次重试...")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
            except requests.exceptions.Timeout:
                self.logger.warning(f"交易日历查询超时，第{attempt+1}/{max_retries}次重试...")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
            except requests.exceptions.ConnectionError:
                self.logger.warning(f"交易日历查询连接失败，第{attempt+1}/{max_retries}次重试...")
                if attempt < max_retries - 1:
                    time.sleep(2 ** attempt)
                    continue
            except Exception as e:
                self.logger.warning(f"交易日历查询失败（第{attempt+1}次）: {e}")
                if attempt < max_retries - 1:
                    time.sleep(2)
                    continue
        # 重试全部失败，回退到TDX判断
        self.logger.warning("东方财富交易日历查询全部失败，回退到TDX判断")

        try:
            now_h = today.hour
            now_m = today.minute
            is_before_open = (now_h, now_m) < (9, 30)
            # v15.2 FIX: 拉更多K线确保包含昨天数据（5根可能全是今天的）
            df = self.tdx.get_latest_bars(count=250)
            if df is not None and len(df) > 0:
                last_time = str(df.iloc[-1]['时间'])
                last_date = last_time.split(' ')[0] if ' ' in last_time else last_time[:10]
                if last_date == today.strftime("%Y-%m-%d"):
                    # v11.6: TDX兜底分支也尝试获取prev_close
                    if self.daily_stats['prev_close'] == 0 and len(df) >= 2:
                        # 取昨天最后一根K线的收盘价
                        first_today_idx = None
                        for i, row in df.iterrows():
                            if str(row['时间']).startswith(today.strftime("%Y-%m-%d")):
                                first_today_idx = i
                                break
                        if first_today_idx is not None and first_today_idx > 0:
                            self.daily_stats['prev_close'] = float(df.iloc[first_today_idx - 1]['收盘'])
                            self.logger.info(f"TDX兜底获取prev_close={self.daily_stats['prev_close']}")
                    return True
                if is_before_open:
                    self.logger.info(f"开盘前通达信数据为 {last_date}（今日尚未开盘），按工作日处理")
                    return True
                self.logger.info(f"通达信最新数据日期 {last_date} != 今天 {today.strftime('%Y-%m-%d')}，判断为休市")
                return False
        except Exception:
            pass

        return True

    def wait_for_market_open(self):
        """等待开盘（09:25 开始准备，自动跳过节假日）"""
        while self.running:
            now = datetime.now()

            if not self.is_trading_day():
                self.logger.info(f"今天 {now.strftime('%Y-%m-%d')} 非交易日，休眠中...")
                time.sleep(300)
                continue

            target = now.replace(hour=9, minute=25, second=0, microsecond=0)
            if now < target:
                wait_secs = (target - now).total_seconds()
                self.logger.info(f"等待开盘... 距离 09:25 还有 {wait_secs/60:.0f} 分钟")
                time.sleep(min(30, wait_secs))
                continue

            break

    def _calc_consecutive_down(self, klines):
        """v15.1: 计算连跌天数（正T约束：连跌≥3天不做正T）
        klines: 腾讯日K线列表，格式 "日期,开盘,收盘,最高,最低,成交量,成交额,振幅..."
        """
        try:
            if not klines or len(klines) < 2:
                return
            # 从最后一条往前数连跌
            streak = 0
            for i in range(len(klines) - 1, 0, -1):
                close_curr = float(klines[i].split(",")[2])
                close_prev = float(klines[i - 1].split(",")[2])
                if close_curr < close_prev:
                    streak += 1
                else:
                    break
            self.daily_stats['consecutive_down_days'] = streak
            self.logger.info(f"v15.1: 连跌天数={streak}（正T约束：>{ZHENGT_MAX_CONSEC_DOWN}天不做）")
        except Exception as e:
            self.logger.warning(f"连跌天数计算失败: {e}")

    def _reset_daily_stats(self):
        """重置每日状态
        v15.1修复：prev_close和consecutive_down_days在is_trading_day()中已计算，
        _reset_daily_stats()不能覆盖它们，否则正T连跌硬约束失效。
        """
        saved_prev_close = self.daily_stats.get('prev_close', 0)
        saved_consec_down = self.daily_stats.get('consecutive_down_days', 0)
        self.daily_stats = {
            'near_trigger_count': 0,
            'max_boll_upper': 0,
            'max_boll_width': 0,
            'max_macd': 0,
            'max_amount_wan': 0,
            'open_price': None,
            'close_price': None,
            'high_price': None,
            'low_price': None,
            'total_amount_wan': 0,
            'prev_close': saved_prev_close,  # v15.1修复：保留已计算的昨收价
            'consecutive_down_days': saved_consec_down,  # v15.1修复：保留已计算的连跌天数
        }
        self.daily_bars = []
        self.daily_report_sent = False
        # v14.1: 重置成交额校验状态
        self.tdx._calibration_checked_today = False
        self.tdx._suspect_count = 0
        self.tdx._calibration_mode = False
        self.tdx._calibration_ratio = 1.0
        # 重置90分钟窗口极值追踪
        self.sell_window_min_price = None
        self.zhengt_window_max_price = None

    def send_morning_brief(self):
        """盘前播报"""
        today_str = datetime.now().strftime("%Y-%m-%d")
        weekday_names = ["周一", "周二", "周三", "周四", "周五", "周六", "周日"]
        weekday = weekday_names[datetime.now().weekday()]

        msg = (
            f"📅 {today_str} {weekday}\n\n"
            f"🐷 肥洪量化 v16.1.2 监控已启动\n"
            f"📊 股票：中国平安 (601318)\n"
            f"⏰ 监控时段：09:40 ~ 14:30\n"
            f"🎯 目标差价：{TARGET_DIFF}元\n"
            f"📈 策略：动量(主)+BOLL(补)+冲高回落 → 倒T卖出 + 正T买入(极低位91%)\n"
            f"🔄 正T/倒T独立运行，互不阻塞\n"
            f"📋 评估：90分钟窗口（止损不终止追踪，窗口到期自动评估信号成败）\n\n"
            f"系统正常运行中，有信号会立即通知你！"
        )
        notify("📈 监控已启动", msg, level="info")
        self.logger.info("盘前播报已推送")

    def send_daily_report(self, full_day_df=None):
        """
        盘后日报：使用全天K线数据计算准确统计
        v11.0: 优先用full_day_df（收盘前拉到的全天数据），
               回退用self.daily_bars（盘中逐条记录的数据）
        """
        s = self.daily_stats
        today_str = datetime.now().strftime("%Y-%m-%d")

        # v11.0: 用全天K线修正统计数据
        if full_day_df is not None and len(full_day_df) > 0:
            time_col = '时间' if '时间' in full_day_df.columns else None
            if time_col:
                today_klines = full_day_df[full_day_df[time_col].astype(str).str.startswith(today_str)]
            else:
                today_klines = full_day_df
            if len(today_klines) > 0:
                open_col = '开盘' if '开盘' in today_klines.columns else 'open'
                close_col = '收盘' if '收盘' in today_klines.columns else 'close'
                high_col = '最高' if '最高' in today_klines.columns else 'high'
                low_col = '最低' if '最低' in today_klines.columns else 'low'
                amount_col = '成交额' if '成交额' in today_klines.columns else 'amount'
                s['open_price'] = round(float(today_klines.iloc[0][open_col]), 2)
                s['close_price'] = round(float(today_klines.iloc[-1][close_col]), 2)
                s['high_price'] = float(today_klines[high_col].max())
                s['low_price'] = float(today_klines[low_col].min())
                s['total_amount_wan'] = float(today_klines[amount_col].sum()) / 10000

        # 成交额格式化
        total_wan = s['total_amount_wan']
        if total_wan >= 10000:
            amount_text = f"{total_wan/10000:.2f}亿"
        else:
            amount_text = f"{total_wan:.0f}万"

        # 实际振幅（元为单位，最高-最低）
        if s['high_price'] is not None and s['low_price'] is not None:
            actual_amp_yuan = s['high_price'] - s['low_price']
            amp_text = f"{actual_amp_yuan:.2f}元"
        else:
            amp_text = "—"

        # 单笔最大额：从全天K线重新计算（避免进程重启导致数据丢失）
        max_amount_wan_from_klines = s['max_amount_wan']  # 默认用盘中记录的
        if full_day_df is not None and len(full_day_df) > 0:
            time_col = '时间' if '时间' in full_day_df.columns else None
            if time_col:
                today_klines = full_day_df[full_day_df[time_col].astype(str).str.startswith(today_str)]
            else:
                today_klines = full_day_df
            if len(today_klines) > 0:
                amount_col = '成交额' if '成交额' in today_klines.columns else 'amount'
                if amount_col in today_klines.columns:
                    # 成交额转为万，找最大值
                    max_amount_val = today_klines[amount_col].max()
                    max_amount_wan_from_klines = float(max_amount_val) / 10000 if max_amount_val > 0 else 0

        # 卖出后状态
        sell_status = ""
        if self.sell_active:
            eval_status = ""
            if self.sell_stop_loss_triggered and not self.sell_eval_notified:
                eval_status = "\n⚠️ 已触发止损，90分钟窗口评估中"
            elif self.sell_eval_notified:
                eval_status = "\n📋 90分钟窗口评估已完成"
            sell_status = (
                f"\n\n⚠️ 卖出后待买回状态\n"
                f"卖出价：{self.sell_price}元（{self.sell_time}）\n"
                f"目标买回：{self.target_buy_price}元\n"
                f"止损价格：{self.stop_loss_price}元"
                f"{eval_status}"
            )

        high_display = f"{s['high_price']:.2f}" if s['high_price'] is not None else "—"
        low_display = f"{s['low_price']:.2f}" if s['low_price'] is not None else "—"
        msg = (
            f"📊 {today_str} 监控日报\n\n"
            f"行情概况\n"
            f"开/收盘：{s['open_price'] or '—'} / {s['close_price'] or '—'}\n"
            f"最高/最低：{high_display} / {low_display}\n"
            f"振幅：{amp_text}\n"
            f"成交额：{amount_text}\n\n"
            f"策略指标峰值\n"
            f"BOLL上轨最高：{s.get('max_boll_upper', 0):.3f}\n"
            f"BOLL带宽最大：{s.get('max_boll_width', 0):.2f}元\n"
            f"MACD柱最高：{s.get('max_macd', 0):.4f}（阈值>{BOLL_MACD_THRESH}）\n"
            f"单笔最大额：{max_amount_wan_from_klines:.0f}万\n\n"
            f"信号统计\n"
            f"倒T卖出信号：{self.signal_count_today} 次\n"
            f"正T买入信号：{self.zhengt_signal_count_today} 次\n"
            f"接近触发（≥3条件）：{s['near_trigger_count']} 次"
            f"{sell_status}"
        )

        notify("📋 盘后日报", msg, level="info")
        self.logger.info("盘后日报已推送")
        self.daily_report_sent = True

    def export_daily_csv(self, full_day_df):
        """导出全天1分钟K线+指标数据到CSV"""
        if full_day_df is None:
            return

        today_str = datetime.now().strftime("%Y-%m-%d")
        time_col = '时间' if '时间' in full_day_df.columns else None
        if time_col:
            today_klines = full_day_df[full_day_df[time_col].astype(str).str.startswith(today_str)]
        else:
            today_klines = full_day_df

        if len(today_klines) == 0:
            self.logger.warning("没有今日K线数据，跳过CSV导出")
            return

        # 确保有指标数据
        today_klines = calc_indicators(today_klines)

        # 选择导出列（兼容中英文列名）
        export_cols = ['时间', '开盘', '收盘', '最高', '最低', '成交量', '成交额',
                       '涨跌', '风险', '买卖力道', 'DIF', 'DEA', 'MACD柱',
                       '日均价', '成交额_万', 'BOLL中轨', 'BOLL上轨', 'BOLL下轨', 'BOLL带宽']

        # 同时支持英文列名的备选
        col_aliases = {
            '时间': ['时间', 'datetime'],
            '开盘': ['开盘', 'open'],
            '收盘': ['收盘', 'close'],
            '最高': ['最高', 'high'],
            '最低': ['最低', 'low'],
            '成交量': ['成交量', 'vol'],
            '成交额': ['成交额', 'amount'],
        }

        final_cols = []
        for col in export_cols:
            if col in today_klines.columns:
                final_cols.append(col)
            elif col in col_aliases:
                found = False
                for alias in col_aliases[col]:
                    if alias in today_klines.columns:
                        final_cols.append(alias)
                        found = True
                        break
                if not found:
                    pass  # 列不存在就跳过
            else:
                if col in today_klines.columns:
                    final_cols.append(col)

        export_df = today_klines[final_cols].copy() if final_cols else today_klines.copy()

        # 确保目录存在
        DATA_DIR.mkdir(parents=True, exist_ok=True)

        csv_path = DATA_DIR / f"{today_str}.csv"
        export_df.to_csv(csv_path, index=False, encoding="utf-8-sig")
        self.logger.info(f"已导出 {len(export_df)} 根K线到 {csv_path}")

    def check_buyback_and_stoploss(self, current_price, current_time, total_bars=None):
        """卖出后追踪：回买提醒 + 90分钟窗口评估（v15.3：止损不终止追踪，90分钟后评估信号成败）"""
        if not self.sell_active:
            return

        # v16.1.2 FIX: 更新90分钟窗口内最低价追踪
        if self.sell_window_min_price is None or current_price < self.sell_window_min_price:
            self.sell_window_min_price = current_price

        # 到达目标买回价（成功）
        if not self.buyback_notified and current_price <= self.target_buy_price:
            self.buyback_notified = True
            diff = self.sell_price - current_price
            msg = (
                f"🎉 到达目标买回价！\n\n"
                f"卖出价：{self.sell_price}元\n"
                f"当前价：{current_price}元\n"
                f"目标买回价：{self.target_buy_price}元\n"
                f"预期利润：{diff:.2f}元\n\n"
                f"请打开同花顺买回！"
            )
            notify("🎯 回买提醒 — 到价了！", msg, level="remind")
            self.logger.info(f"🎯 回买提醒：当前价{current_price} ≤ 目标{self.target_buy_price}")
            self.sell_active = False
            self.sell_window_min_price = None  # 清理窗口追踪
            # 更新信号历史状态：倒T成功
            update_signal_status(self.sell_time, "sell", "成功", diff * 1000)
            # v15.2 智能冷却：信号完成（回买成功），立即解锁冷却期
            if total_bars is not None:
                self.last_signal_bar = total_bars - 1 - COOLDOWN_BARS
                self.logger.info(f"🔓 智能冷却解锁：倒T信号完成（回买成功），冷却期立即解除")
            return

        # v15.3: 价格反转保护（止损）——不再终止追踪，只做风险提示
        if not self.sell_stop_loss_triggered and current_price > self.stop_loss_price:
            self.sell_stop_loss_triggered = True
            msg = (
                f"⚠️ 价格反转保护触发！\n\n"
                f"卖出价：{self.sell_price}元（{self.sell_time}）\n"
                f"当前价：{current_price}元（已涨{current_price - self.sell_price:+.2f}元）\n"
                f"止损价格：{self.stop_loss_price}元\n\n"
                f"⚠️ 风险提示，仅供参考！\n"
                f"价格不跌反涨，但不等于信号失败。\n"
                f"系统将在90分钟窗口内继续评估信号有效性。\n"
                f"是否买回请自行判断。"
            )
            notify("⚠️ 价格反转保护 — 风险提示", msg, level="remind")
            self.logger.info(f"⚠️ 价格反转保护：当前价{current_price} > 止损{self.stop_loss_price}，继续90分钟窗口评估")
            # 注意：不再关闭 sell_active，也不解锁冷却期
            # 90分钟窗口到期后会自动评估并结束追踪
            return

        # v15.3: 90分钟窗口评估——止损触发后，窗口到期时评估信号最终成败
        if self.sell_stop_loss_triggered and not self.sell_eval_notified and total_bars is not None:
            elapsed_bars = total_bars - self.sell_signal_bar
            if elapsed_bars >= EVAL_WINDOW_BARS:
                # 90分钟窗口到期：检查窗口内最低价是否低于卖出价-0.25元
                self.sell_eval_notified = True
                window_min = self.sell_window_min_price if self.sell_window_min_price is not None else current_price
                self.logger.info(f"🔍 倒T窗口评估：卖出价={self.sell_price}，窗口最低价={window_min}，阈值={self.sell_price - 0.25:.3f}")
                if window_min <= self.sell_price - 0.25:
                    result_msg = "✅ 信号理论有效（窗口内曾回落≥0.25元）"
                    signal_result = "成功"
                else:
                    result_msg = "❌ 信号理论失败（90分钟窗口内未回落≥0.25元）"
                    signal_result = "失败"
                msg = (
                    f"📋 倒T 90分钟窗口评估\n\n"
                    f"卖出价：{self.sell_price}元（{self.sell_time}）\n"
                    f"窗口最低价：{window_min}元\n"
                    f"止损触发：{'是' if self.sell_stop_loss_triggered else '否'}\n\n"
                    f"评估结果：{result_msg}\n"
                    f"（评估标准：90分钟内最低价 < 卖出价-0.25元）"
                )
                notify(f"📋 倒T窗口评估 — {signal_result}", msg, level="info")
                self.logger.info(f"📋 倒T90分钟窗口评估：{result_msg}")
                # 更新信号历史状态
                daot_profit = (self.sell_price - current_price) * 1000 if signal_result == "成功" else -0.15 * 1000  # 简化估算
                update_signal_status(self.sell_time, "sell", signal_result, daot_profit)
                # 评估完成后关闭追踪
                self.sell_active = False
                self.sell_window_min_price = None  # 清理窗口追踪
                # 智能冷却解锁
                self.last_signal_bar = total_bars - 1 - COOLDOWN_BARS
                self.logger.info(f"🔓 90分钟窗口评估结束，冷却期解锁")
                return

    def check_zhengt_sell_and_stoploss(self, current_price, current_time, total_bars=None):
        """正T买入后追踪：卖出提醒 + 90分钟窗口评估（v15.3：止损不终止追踪，90分钟后评估信号成败）"""
        if not self.zhengt_buy_active:
            return

        # v16.1.2 FIX: 更新90分钟窗口内最高价追踪
        if self.zhengt_window_max_price is None or current_price > self.zhengt_window_max_price:
            self.zhengt_window_max_price = current_price

        # 到达目标卖出价（成功）
        if not self.zhengt_sell_notified and current_price >= self.zhengt_target_sell_price:
            self.zhengt_sell_notified = True
            diff = current_price - self.zhengt_buy_price
            msg = (
                f"🎉 到达目标卖出价！\n\n"
                f"买入价：{self.zhengt_buy_price}元\n"
                f"当前价：{current_price}元\n"
                f"目标卖出价：{self.zhengt_target_sell_price}元\n"
                f"预期利润：{diff:.2f}元\n\n"
                f"请打开同花顺卖出！"
            )
            notify("🎯 正T卖出提醒 — 到价了！", msg, level="remind")
            self.logger.info(f"🎯 正T卖出提醒：当前价{current_price} ≥ 目标{self.zhengt_target_sell_price}")
            self.zhengt_buy_active = False
            self.zhengt_window_max_price = None  # 清理窗口追踪
            # 更新信号历史状态：正T成功
            update_signal_status(self.zhengt_buy_time, "buy", "成功", diff * 1000)
            # v15.2 智能冷却：信号完成（卖出成功），立即解锁冷却期
            if total_bars is not None:
                self.last_zhengt_signal_bar = total_bars - 1 - COOLDOWN_BARS
                self.logger.info(f"🔓 智能冷却解锁：正T信号完成（卖出成功），冷却期立即解除")
            return

        # v15.3: 正T风险提示（止损）——不再终止追踪，只做风险提示
        if not self.zhengt_stop_loss_triggered and current_price < self.zhengt_stop_loss_price:
            self.zhengt_stop_loss_triggered = True
            msg = (
                f"⚠️ 正T风险提示！\n\n"
                f"买入价：{self.zhengt_buy_price}元（{self.zhengt_buy_time}）\n"
                f"当前价：{current_price}元（已跌{current_price - self.zhengt_buy_price:+.2f}元）\n"
                f"止损价格：{self.zhengt_stop_loss_price}元\n\n"
                f"⚠️ 风险提示，仅供参考！\n"
                f"价格继续下跌，但不等于信号失败。\n"
                f"系统将在90分钟窗口内继续评估信号有效性。\n"
                f"是否卖出请自行判断。"
            )
            notify("⚠️ 正T风险提示 — 仅供参考", msg, level="remind")
            self.logger.info(f"⚠️ 正T风险提示：当前价{current_price} < 止损{self.zhengt_stop_loss_price}，继续90分钟窗口评估")
            # 注意：不再关闭 zhengt_buy_active，也不解锁冷却期
            return

        # v15.3: 90分钟窗口评估——止损触发后，窗口到期时评估信号最终成败
        if self.zhengt_stop_loss_triggered and not self.zhengt_eval_notified and total_bars is not None:
            elapsed_bars = total_bars - self.zhengt_signal_bar
            if elapsed_bars >= EVAL_WINDOW_BARS:
                # 90分钟窗口到期：检查窗口内最高价是否高于买入价+0.20元
                self.zhengt_eval_notified = True
                window_max = self.zhengt_window_max_price if self.zhengt_window_max_price is not None else current_price
                self.logger.info(f"🔍 正T窗口评估：买入价={self.zhengt_buy_price}，窗口最高价={window_max}，阈值={self.zhengt_buy_price + 0.20:.3f}")
                if window_max >= self.zhengt_buy_price + 0.20:
                    result_msg = "✅ 信号理论有效（窗口内曾反弹≥0.20元）"
                    signal_result = "成功"
                else:
                    result_msg = "❌ 信号理论失败（90分钟窗口内未反弹≥0.20元）"
                    signal_result = "失败"
                msg = (
                    f"📋 正T 90分钟窗口评估\n\n"
                    f"买入价：{self.zhengt_buy_price}元（{self.zhengt_buy_time}）\n"
                    f"窗口最高价：{window_max}元\n"
                    f"止损触发：{'是' if self.zhengt_stop_loss_triggered else '否'}\n\n"
                    f"评估结果：{result_msg}\n"
                    f"（评估标准：90分钟内最高价 > 买入价+0.20元）"
                )
                notify(f"📋 正T窗口评估 — {signal_result}", msg, level="info")
                self.logger.info(f"📋 正T90分钟窗口评估：{result_msg}")
                # 更新信号历史状态
                zhengt_profit = (current_price - self.zhengt_buy_price) * 1000 if signal_result == "成功" else -0.15 * 1000  # 简化估算
                update_signal_status(self.zhengt_buy_time, "buy", signal_result, zhengt_profit)
                # 评估完成后关闭追踪
                self.zhengt_buy_active = False
                self.zhengt_window_max_price = None  # 清理窗口追踪
                # 智能冷却解锁
                self.last_zhengt_signal_bar = total_bars - 1 - COOLDOWN_BARS
                self.logger.info(f"🔓 90分钟窗口评估结束，冷却期解锁")
                return

    def run(self):
        """主运行循环"""
        self.logger.info("=" * 60)
        self.logger.info("  中国平安 v16.1.2 三策略倒T+正T策略监控系统 启动")
        self.logger.info(f"  股票: {self.config.get('stock_code', '601318')} {self.config.get('stock_name', '中国平安')}")
        self.logger.info("  【策略1: 动量倒T卖出】主力策略（v14.0恢复v10.2，59天回测：80.6%胜率）")
        self.logger.info(f"    条件: 涨跌>{ZHANGDIE_THRESH} + 风险>{FENGXIAN_THRESH} + 额≥{AMOUNT_THRESH_WAN}万")
        self.logger.info(f"           股价>均价+{MA_ABOVE} + |MACD柱|>{MACD_BAR_THRESH}")
        self.logger.info("  【策略2: BOLL上轨倒T卖出】补充策略（v14.0去掉带宽条件）")
        self.logger.info(f"    条件: 触碰BOLL上轨(≥{BOLL_TOUCH_RATIO*100:.1f}%) + 额≥{BOLL_AMOUNT_THRESH_WAN}万")
        self.logger.info(f"           股价>均价+{BOLL_MA_ABOVE} + 偏离均价>{BOLL_DEVIATION_THRESH} + MACD柱>{BOLL_MACD_THRESH}")
        self.logger.info("  【策略3: 冲高回落倒T卖出】低波动日备用（v16.0重构）")
        self.logger.info(f"    适用: 低波动日(带宽<{PULLBACK_BANDWIDTH_THRESH}元)")
        self.logger.info(f"    条件: 盘中最高偏离均价>{PULLBACK_DAY_HIGH_DEVIATION} + 从高点回落>{PULLBACK_PULLBACK_FROM_HIGH} + 收盘偏离均价>{PULLBACK_CLOSE_ABOVE_AVG} + 额≥{PULLBACK_AMOUNT_THRESH_WAN}万")
        self.logger.info(f"           已从上轨回落 + 时间{PULLBACK_START[0]}:{PULLBACK_START[1]:02d}-{PULLBACK_END[0]}:{PULLBACK_END[1]:02d}")
        self.logger.info("  【正T买入策略】v16.1 极低位高胜率组合 + BOLL带宽约束（90min窗口回测83%胜率@0.20目标）")
        self.logger.info(f"    条件: 偏离均价>{ZHENGT_MA_BELOW}元 + 风险<{ZHENGT_RISK_THRESH} + 额≥{ZHENGT_AMOUNT_THRESH_WAN}万")
        self.logger.info(f"           涨跌≤{ZHENGT_ZD_THRESH} + 日振幅≥{ZHENGT_MIN_AMPLITUDE}元 + BOLL带宽>{ZHENGT_MIN_BOLL_WIDTH}%")
        self.logger.info(f"    硬约束: {ZHENGT_LATEST_HOUR}:00后不做 + 连跌>{ZHENGT_MAX_CONSEC_DOWN}天不做")
        self.logger.info(f"    目标差价: {ZHENGT_TARGET_DIFF}元 | 止损: {ZHENGT_STOP_LOSS_DIFF}元")
        self.logger.info(f"  时间窗口: {TRADE_START[0]}:{TRADE_START[1]:02d} ~ {TRADE_END[0]}:{TRADE_END[1]:02d}")
        self.logger.info("  【动态目标差价 & 止损差价】")
        self.logger.info(f"    缩量日(<72亿): 目标{TARGET_DIFF_LOW_VOLUME}元 | 止损{STOP_LOSS_DIFF_LOW_VOLUME}元")
        self.logger.info(f"    正常日(≥72亿): 目标{TARGET_DIFF_NORMAL}元 | 止损{STOP_LOSS_DIFF_NORMAL}元")
        self.logger.info(f"    极端缩量(<30亿): 目标{EXTREME_LOW_TARGET}元 | 止损0.10元")
        self.logger.info("=" * 60)

        # v15.2: 如果启动时已收盘（>=15:07），直接退出，不推送任何消息
        now = datetime.now()
        if now.hour > 15 or (now.hour == 15 and now.minute >= 7):
            self.logger.info(f"当前时间 {now.strftime('%H:%M')} 已收盘，无需监控，退出")
            return

        # 只运行一天，收盘后退出
        # 交易日判断
        if not self.is_trading_day():
            self.logger.info(f"今天 {datetime.now().strftime('%Y-%m-%d')} 非交易日，退出")
            return

        # 等待开盘
        self.wait_for_market_open()
        if not self.running:
            return

        today_str = datetime.now().strftime("%Y-%m-%d")
        self.logger.info(f"═══ 新交易日: {today_str} ═══")

        # 重置状态
        self._reset_daily_stats()
        self.signal_count_today = 0
        self.sell_active = False
        self.buyback_notified = False
        self.last_signal_bar = -COOLDOWN_BARS - 1  # v15.2: 新交易日重置倒T冷却期
        self.sell_stop_loss_triggered = False  # v15.3: 重置倒T止损触发标志
        self.sell_signal_bar = 0               # v15.3: 重置倒T信号bar编号
        self.sell_eval_notified = False         # v15.3: 重置倒T评估推送标志
        self.zhengt_signal_count_today = 0
        self.zhengt_buy_active = False
        self.zhengt_sell_notified = False
        self.last_zhengt_signal_bar = 0
        self.zhengt_stop_loss_triggered = False  # v15.3: 重置正T止损触发标志
        self.zhengt_signal_bar = 0               # v15.3: 重置正T信号bar编号
        self.zhengt_eval_notified = False         # v15.3: 重置正T评估推送标志

        # 连接通达信（带重试机制 + 网络就绪等待）
        self.logger.info("连接通达信服务器...")
        
        # v14.1: 网络就绪检测 — 如果刚从睡眠恢复，等待网络可达
        max_network_wait = 120  # 最多等2分钟
        network_wait_start = time.time()
        while time.time() - network_wait_start < max_network_wait:
            try:
                # 尝试DNS解析通达信服务器
                import socket
                socket.getaddrinfo("180.153.18.170", 7709, socket.AF_INET, socket.SOCK_STREAM)
                self.logger.info("网络就绪，开始连接通达信")
                break
            except Exception as e:
                elapsed = time.time() - network_wait_start
                self.logger.warning(f"网络未就绪（{elapsed:.0f}秒），等待中... ({e})")
                time.sleep(10)
        else:
            self.logger.warning(f"网络等待超时({max_network_wait}秒)，仍然尝试连接")
        
        connect_success = False
        for attempt in range(3):
            if self.tdx.connect():
                connect_success = True
                self.logger.info(f"通达信已连接（第{attempt+1}次尝试成功），开始监控...")
                break
            else:
                self.logger.warning(f"第{attempt+1}次连接失败，10秒后重试...")
                time.sleep(10)
        
        if not connect_success:
            self.logger.error("无法连接通达信服务器，3次重试后退出")
            notify("❌ 连接失败", "无法连接通达信服务器，3次重试后放弃，请手动检查", level="error")
            return

        # 盘前播报
        self.send_morning_brief()

        # 预热
        self.logger.info("预拉历史K线做指标预热...")
        df = self.tdx.get_latest_bars(count=600)
        if df is not None:
            self.logger.info(f"已获取 {len(df)} 根K线（用于指标预热）")
        else:
            self.logger.warning("预拉数据失败，将在盘中重新获取")
            df = pd.DataFrame()

        # 盘中循环
        last_bar_time = None
        check_interval = 3  # 每3秒检查一次
        last_heartbeat = ""  # v11.0: 记录最后心跳时间，防止重复
        # v11.6: 缓存完整心跳指标，确保心跳内容始终完整
        hb_cache = {
            'price': self.daily_stats.get('prev_close') or 0,
            'zd': 0, 'fx': 0, 'amt': 0, 'macd': 0, 'maimai': 0,
            'boll_up': 0, 'boll_width': 0,  # BOLL指标（动量+BOLL策略共用）
            'est_bark': '',  # 量能预估文本
        }

        self.logger.info("进入盘中监控循环...")
        loop_count = 0
        while self.running:
            try:
                now = datetime.now()
                h, m = now.hour, now.minute
                loop_count += 1
                if loop_count <= 5:
                    self.logger.info(f"循环迭代 #{loop_count}, 时间={h}:{m}")

                # ===== 收盘处理 =====
                if (h, m) >= (15, 5):
                    # v15.1.2: 收盘前检查未了结仓位，避免持仓过夜无提醒
                    if self.sell_active:
                        eval_note = ""
                        if self.sell_stop_loss_triggered and not self.sell_eval_notified:
                            eval_note = "\n\n⚠️ 止损已触发但90分钟窗口评估未完成\n请留意盘后90分钟窗口评估推送"
                        msg = (
                            f"⚠️ 倒T卖出未买回！\n\n"
                            f"卖出价：{self.sell_price}元（{self.sell_time}）\n"
                            f"目标买回价：{self.target_buy_price}元\n"
                            f"止损价：{self.stop_loss_price}元\n\n"
                            f"到收盘仍未买回，请确认仓位状态！"
                            f"{eval_note}"
                        )
                        notify("⚠️ 倒T未了结 — 收盘提醒", msg, level="remind")
                        self.logger.warning(f"⚠️ 倒T未了结：卖出价{self.sell_price}，到收盘仍未买回")

                    if self.zhengt_buy_active:
                        eval_note = ""
                        if self.zhengt_stop_loss_triggered and not self.zhengt_eval_notified:
                            eval_note = "\n\n⚠️ 止损已触发但90分钟窗口评估未完成\n请留意盘后90分钟窗口评估推送"
                        msg = (
                            f"⚠️ 正T买入未卖出！\n\n"
                            f"买入价：{self.zhengt_buy_price}元（{self.zhengt_buy_time}）\n"
                            f"目标卖出价：{self.zhengt_target_sell_price}元\n"
                            f"止损价：{self.zhengt_stop_loss_price}元\n\n"
                            f"到收盘仍未卖出，请确认仓位状态！"
                            f"{eval_note}"
                        )
                        notify("⚠️ 正T未了结 — 收盘提醒", msg, level="remind")
                        self.logger.warning(f"⚠️ 正T未了结：买入价{self.zhengt_buy_price}，到收盘仍未卖出")

                    self.logger.info(f"═══ {today_str} 监控结束，共触发 {self.signal_count_today} 次信号 ═══")

                    # 拉取全天数据用于准确日报和CSV导出
                    full_df = self.tdx.get_latest_bars(count=1600)

                    # 日报（使用全天数据）
                    self.send_daily_report(full_day_df=full_df)

                    # 导出CSV
                    self.export_daily_csv(full_df)

                    # v13.1: 发送增强复盘报告（含图表）
                    if ENHANCED_REPORT_AVAILABLE and full_df is not None:
                        try:
                            from daily_report_enhanced import generate_enhanced_report
                            # v13.5 FIX: 确保df已计算指标（含成交额_万列）
                            full_df_with_indicators = calc_indicators(full_df)
                            enhanced_report, chart_path = generate_enhanced_report(
                                full_df_with_indicators, 
                                signal_count=self.signal_count_today,
                                zhengt_count=self.zhengt_signal_count_today,
                                prev_close=self.daily_stats.get('prev_close', 0)
                            )
                            notify("📊 每日复盘报告", enhanced_report, level="info")
                            self.logger.info("增强复盘报告已推送")
                            if chart_path:
                                self.logger.info(f"复盘图表已保存: {chart_path}")
                        except Exception as e:
                            self.logger.warning(f"增强复盘报告生成失败: {e}")

                    # 断开连接
                    self.tdx.disconnect()

                    # v11.0: 收盘后直接退出，不再循环
                    self.logger.info("收盘完毕，程序退出")
                    break

                # v13.4: 移除午休跳过，程序持续运行到15:00收盘

                # v11.6: 心跳判断提到数据拉取之前，用缓存指标发完整心跳
                heartbeat_key = f"{h}:{m // 10 * 10:02d}"
                if m % 10 == 0 and heartbeat_key != last_heartbeat and (h, m) <= (15, 0):
                    last_heartbeat = heartbeat_key
                    cp = hb_cache['price']
                    if cp and cp > 0:
                        czd = hb_cache['zd']
                        cfx = hb_cache['fx']
                        cmm = hb_cache['maimai']
                        mm_tag = f"🔴{cmm:+.0f}" if cmm > 1100 else (f"🟢{cmm:+.0f}" if cmm < 900 else f"⚪{cmm:+.0f}")
                        
                        # v13.5 FIX: 心跳时强制实时拉取最新数据计算预估，不使用缓存df
                        est_bark_for_heartbeat = ""
                        try:
                            # 15:00收盘后显示实际成交额，不再预估
                            if h == 15 and m >= 0:
                                # 收盘后：实时拉取数据计算实际全天成交额
                                df_closing = self.tdx.get_latest_bars(count=240)
                                if df_closing is not None and len(df_closing) > 0:
                                    df_closing = calc_indicators(df_closing)
                                    today_str = datetime.now().strftime('%Y-%m-%d')
                                    today_df = df_closing[df_closing['时间'].astype(str).str.startswith(today_str)]
                                    if len(today_df) > 0:
                                        actual_amount_yi = float(today_df["成交额"].sum()) / 100000000  # 转亿元
                                        actual_high = float(today_df['最高'].max())
                                        actual_low = float(today_df['最低'].min())
                                        actual_amp = actual_high - actual_low
                                        est_bark_for_heartbeat = (
                                            f"\n\n📊 收盘统计\n"
                                            f"全天成交：{actual_amount_yi:.1f}亿\n"
                                            f"全天振幅：{actual_amp:.2f}元（高{actual_high:.2f}-低{actual_low:.2f}）"
                                        )
                            else:
                                # 盘中：实时拉取最新数据计算预估
                                df_live = self.tdx.get_latest_bars(count=240)
                                if df_live is not None and len(df_live) > 0:
                                    df_live = calc_indicators(df_live)
                                    est_live = estimate_daily_amount_and_amplitude(
                                        df_live, self.daily_stats['prev_close'], self.daily_stats.get('open_price') or 0
                                    )
                                    if est_live and est_live['estimated_daily_yi'] >= 1:
                                        # 心跳显示用真实每分钟均额（累计额/已交易分钟）
                                        real_per_min = est_live.get('per_min_amount_wan', 0)
                                        actual_amp = est_live.get('actual_amplitude', 0)
                                        actual_high = est_live.get('actual_high', 0)
                                        actual_low = est_live.get('actual_low', 0)
                                        est_bark_for_heartbeat = (
                                            f"\n\n📈 量能预估\n"
                                            f"已交易：{est_live['elapsed_min']}分钟\n"
                                            f"每分钟均额：{real_per_min:.0f}万\n"
                                            f"预估全天：{est_live['estimated_daily_yi']:.1f}亿\n"
                                            f"预估振幅：{est_live['estimated_amplitude']:.2f}元\n"
                                            f"当前振幅：{actual_amp:.2f}元（高{actual_high:.2f}-低{actual_low:.2f}）"
                                        )
                        except Exception as e:
                            self.logger.warning(f"心跳预估计算失败: {e}")
                            est_bark_for_heartbeat = hb_cache.get('est_bark', '')
                        
                        self.logger.info(
                            f"💓 {now.strftime('%H:%M')} 价格={cp:.2f} 涨跌={czd:.0f} "
                            f"风险={cfx:.0f} 力道={mm_tag} 今日信号={self.signal_count_today}"
                            f"{' ⏳卖出后追踪中' if self.sell_active else ''}"
                        )

                        # v15.3: 90分钟窗口倒计时信息
                        eval_info = ""
                        if self.sell_active and self.sell_stop_loss_triggered and not self.sell_eval_notified:
                            current_total_bars = len(df) if df is not None else 0
                            if current_total_bars > 0 and self.sell_signal_bar > 0:
                                elapsed = current_total_bars - self.sell_signal_bar
                                remaining = max(0, EVAL_WINDOW_BARS - elapsed)
                                eval_info = f"\n⏱️ 倒T评估倒计时：{remaining}分钟"
                        if self.zhengt_buy_active and self.zhengt_stop_loss_triggered and not self.zhengt_eval_notified:
                            current_total_bars = len(df) if df is not None else 0
                            if current_total_bars > 0 and self.zhengt_signal_bar > 0:
                                elapsed = current_total_bars - self.zhengt_signal_bar
                                remaining = max(0, EVAL_WINDOW_BARS - elapsed)
                                eval_info += f"\n⏱️ 正T评估倒计时：{remaining}分钟"

                        notify("💓 中国平安 心跳",
                            f"💓 {now.strftime('%H:%M')} 心跳\n\n"
                            f"价格：{cp:.2f}\n"
                            f"BOLL上轨：{hb_cache.get('boll_up', 0):.3f}\n"
                            f"BOLL带宽：{hb_cache.get('boll_width', 0):.2f}元\n"
                            f"MACD柱：{hb_cache.get('macd', 0):.4f}\n"
                            f"成交额：{hb_cache['amt']:.0f}万\n"
                            f"倒T信号：{self.signal_count_today}{' ⏳追踪中' if self.sell_active else ''}{' ⚠️止损' if self.sell_stop_loss_triggered else ''}\n"
                            f"正T信号：{self.zhengt_signal_count_today}{' ⏳追踪中' if self.zhengt_buy_active else ''}{' ⚠️止损' if self.zhengt_stop_loss_triggered else ''}"
                            f"{eval_info}"
                            f"{est_bark_for_heartbeat}",
                            level="heartbeat")

                # ===== 拉取最新数据 =====
                if loop_count <= 5:
                    self.logger.info(f"[#{loop_count}] 开始拉取数据...")
                df = self.tdx.get_latest_bars(count=600)
                if loop_count <= 5:
                    self.logger.info(f"[#{loop_count}] 数据拉取完成, df={df is not None}")
                if df is None:
                    self.logger.warning("获取数据失败，尝试重连...")
                    if not self.tdx.reconnect():
                        time.sleep(30)
                        continue
                    df = self.tdx.get_latest_bars(count=600)
                    if df is None:
                        time.sleep(30)
                        continue

                # 计算指标
                if loop_count <= 5:
                    self.logger.info(f"[#{loop_count}] 开始计算指标...")
                df = calc_indicators(df)
                if loop_count <= 5:
                    self.logger.info(f"[#{loop_count}] 指标计算完成, 列数={len(df.columns)}")

                # 检查最新K线
                if loop_count <= 5:
                    self.logger.info(f"[#{loop_count}] 开始检查K线...")
                latest = df.iloc[-1]
                latest_time = str(latest['时间'])
                if loop_count <= 5:
                    self.logger.info(f"[#{loop_count}] 最新K线时间={latest_time}")
                completed = df.iloc[-2] if len(df) >= 2 else latest
                if loop_count <= 5:
                    self.logger.info(f"[#{loop_count}] completed K线时间={str(completed['时间'])}")

                # v11.6: 数据拉取成功后，更新缓存指标供下次心跳使用
                if loop_count <= 5:
                    self.logger.info(f"[#{loop_count}] 开始更新缓存...")
                hb_cache['price'] = float(completed['收盘'])
                hb_cache['zd'] = float(completed['涨跌']) if not np.isnan(completed['涨跌']) else hb_cache.get('zd', 0)
                hb_cache['fx'] = float(completed['风险']) if not np.isnan(completed['风险']) else hb_cache.get('fx', 0)
                hb_cache['amt'] = float(completed['成交额_万']) if not np.isnan(completed.get('成交额_万', np.nan)) else hb_cache.get('amt', 0)
                hb_cache['macd'] = float(completed['MACD柱']) if not np.isnan(completed.get('MACD柱', np.nan)) else hb_cache.get('macd', 0)
                hb_cache['maimai'] = float(completed['买卖力道']) if not np.isnan(completed.get('买卖力道', np.nan)) else hb_cache.get('maimai', 0)
                # v13.0: 增加BOLL指标缓存
                hb_cache['boll_up'] = float(completed['BOLL上轨']) if not np.isnan(completed.get('BOLL上轨', np.nan)) else hb_cache.get('boll_up', 0)
                hb_cache['boll_width'] = float(completed['BOLL带宽']) if not np.isnan(completed.get('BOLL带宽', np.nan)) else hb_cache.get('boll_width', 0)

                # v11.6: 每次数据拉取成功后计算量能预估并缓存
                est = estimate_daily_amount_and_amplitude(
                    df, self.daily_stats['prev_close'], self.daily_stats.get('open_price') or 0
                )
                est_bark = ""
                if est:
                    est_daily = est['estimated_daily_yi']
                    est_amp_pct = est['estimated_amplitude_pct']
                    gap = est['gap_amount']
                    # 心跳显示用真实每分钟均额（累计额/已交易分钟）
                    real_per_min = est.get('per_min_amount_wan', 0)
                    # 预估振幅始终用元显示
                    amp_display = f"{est['estimated_amplitude']:.2f}元"
                    if est_daily >= 1:
                        # 计算当前实际振幅
                        actual_amp = est.get('actual_amplitude', 0)
                        actual_high = est.get('actual_high', 0)
                        actual_low = est.get('actual_low', 0)
                        est_bark = (
                            f"\n\n📈 量能预估\n"
                            f"已交易：{est['elapsed_min']}分钟\n"
                            f"每分钟均额：{real_per_min:.0f}万\n"
                            f"预估全天：{est_daily:.1f}亿\n"
                            f"预估振幅：{amp_display}\n"
                            f"当前振幅：{actual_amp:.2f}元（高{actual_high:.2f}-低{actual_low:.2f}）"
                        )
                        if abs(gap) > 0.01:
                            direction = "跳高" if gap > 0 else "跳低"
                            est_bark += f"\n（含{direction}{abs(gap):.2f}元跳空修正）"
                        if est['is_extreme_low']:
                            est_bark += f"\n\n⚠️ 极端缩量！建议目标差价降至{EXTREME_LOW_TARGET}元"
                        elif est['is_volume_low']:
                            est_bark += f"\n\n🟡 缩量交易日，审慎交易"
                hb_cache['est_bark'] = est_bark
                if loop_count <= 5:
                    self.logger.info(f"[#{loop_count}] 缓存更新完成")

                # 避免重复处理同一根K线
                if latest_time == last_bar_time:
                    if loop_count <= 5:
                        self.logger.info(f"[#{loop_count}] K线重复，跳过")
                    time.sleep(check_interval)
                    continue
                last_bar_time = latest_time
                if loop_count <= 5:
                    self.logger.info(f"[#{loop_count}] K线更新，继续处理")

                # 更新每日统计（用最新K线的实际值）
                current_price = float(latest['收盘'])
                current_high = float(latest['最高'])
                current_low = float(latest['最低'])
                amount_val = float(latest['成交额_万'])
                boll_upper_val = float(latest['BOLL上轨']) if not np.isnan(latest.get('BOLL上轨', np.nan)) else 0
                boll_width_val = float(latest['BOLL带宽']) if not np.isnan(latest.get('BOLL带宽', np.nan)) else 0
                macd_val = float(latest['MACD柱']) if not np.isnan(latest.get('MACD柱', np.nan)) else 0
                self.daily_stats['max_boll_upper'] = max(self.daily_stats['max_boll_upper'], boll_upper_val)
                self.daily_stats['max_boll_width'] = max(self.daily_stats['max_boll_width'], boll_width_val)
                self.daily_stats['max_macd'] = max(self.daily_stats['max_macd'], macd_val)
                self.daily_stats['max_amount_wan'] = max(self.daily_stats['max_amount_wan'], amount_val)
                if self.daily_stats['high_price'] is None:
                    self.daily_stats['high_price'] = current_high
                else:
                    self.daily_stats['high_price'] = max(self.daily_stats['high_price'], current_high)
                if self.daily_stats['low_price'] is None:
                    self.daily_stats['low_price'] = current_low
                else:
                    self.daily_stats['low_price'] = min(self.daily_stats['low_price'], current_low)
                if self.daily_stats['open_price'] is None:
                    # v11.0: 开盘价用第一根K线的open字段
                    self.daily_stats['open_price'] = round(float(latest['开盘']), 2)

                # 记录日内数据（用于CSV）
                bar_data = {
                    '时间': latest_time,
                    '开盘': float(latest['开盘']),
                    '收盘': current_price,
                    '最高': float(latest['最高']),
                    '最低': float(latest['最低']),
                    '成交量': int(latest['成交量']),
                    '成交额': float(latest['成交额']),
                    '涨跌': round(float(latest['涨跌']), 1) if not np.isnan(latest.get('涨跌', np.nan)) else 0,
                    '风险': round(float(latest['风险']), 0) if not np.isnan(latest.get('风险', np.nan)) else 0,
                    '成交额_万': round(amount_val, 0),
                }
                # MACD
                if not np.isnan(latest.get('DIF', np.nan)):
                    bar_data['DIF'] = round(float(latest['DIF']), 4)
                    bar_data['DEA'] = round(float(latest['DEA']), 4)
                    bar_data['MACD柱'] = round(float(latest['MACD柱']), 4)
                # BOLL
                if not np.isnan(latest.get('BOLL中轨', np.nan)):
                    bar_data['BOLL中轨'] = round(float(latest['BOLL中轨']), 2)
                    bar_data['BOLL上轨'] = round(float(latest['BOLL上轨']), 2)
                    bar_data['BOLL下轨'] = round(float(latest['BOLL下轨']), 2)
                    bar_data['BOLL带宽'] = round(float(latest['BOLL带宽']), 2)
                # 买卖力道
                if not np.isnan(latest.get('买卖力道', np.nan)):
                    bar_data['买卖力道'] = round(float(latest['买卖力道']), 1)
                self.daily_bars.append(bar_data)

                # v16.2: 盘中实时导出数据给API（每分钟写JSON）
                try:
                    realtime_path = DATA_DIR / 'realtime_bars.json'
                    with open(realtime_path, 'w', encoding='utf-8') as _f:
                        json.dump({
                            'date': latest_time[:10],
                            'bars': self.daily_bars,
                            'last_update': datetime.now().strftime('%Y-%m-%d %H:%M:%S')
                        }, _f, ensure_ascii=False)
                except Exception as _e:
                    self.logger.debug(f'实时数据导出失败: {_e}')

                # 检查交易窗口
                in_trade_window = is_trade_time(latest_time)

                # 倒T卖出后追踪（不限时间窗口）
                self.check_buyback_and_stoploss(current_price, latest_time, total_bars=len(df))

                # 正T买入后追踪（不限时间窗口）
                self.check_zhengt_sell_and_stoploss(current_price, latest_time, total_bars=len(df))

                if not in_trade_window:
                    time.sleep(check_interval)
                    continue

                # v16.1.2: 倒T冷却期检查（正T有独立冷却期，不再被倒T冷却阻塞）
                total_bars = len(df)
                in_daot_cooldown = (total_bars - 1 - self.last_signal_bar) < COOLDOWN_BARS

                # ==================== 三策略卖出判断 ====================
                # v14.0 优先级：动量策略(主) → BOLL补充 → 冲高回落(低波动日备用)
                # v16.1.2: 倒T冷却期间跳过倒T策略（正T不受影响）
                if in_daot_cooldown:
                    momentum_triggered = False
                    momentum_details = None
                    boll_triggered = False
                    boll_details = None
                    pullback_triggered = False
                    pullback_details = None
                    triggered = False
                    details = None
                    strategy_type = None
                else:
                    # 策略1: 动量策略（主力，v10.2涨跌+风险）
                    momentum_triggered, momentum_details = check_momentum_sell_signal(completed, self.logger)
                
                    # 策略2: BOLL上轨策略（补充，仅动量未触发时检查）
                    boll_triggered = False
                    boll_details = None
                    if not momentum_triggered and not self.sell_active:
                        boll_triggered, boll_details = check_boll_sell_signal(completed, self.logger)
                
                    # 策略3: 冲高回落策略（低波动日备用，仅前两个策略都未触发时检查）
                    current_bandwidth = float(completed['BOLL带宽']) if not np.isnan(completed['BOLL带宽']) else 0
                    is_low_volatility = current_bandwidth < PULLBACK_BANDWIDTH_THRESH
                
                    pullback_triggered = False
                    pullback_details = None
                    if not momentum_triggered and not boll_triggered and is_low_volatility and not self.sell_active:
                        # v16.0: 传入盘中最高价（已在daily_stats中跟踪）
                        pullback_triggered, pullback_details = check_pullback_sell_signal(df, total_bars - 2, self.logger, day_high=self.daily_stats['high_price'])
                        if pullback_triggered:
                            self.logger.info(f"📉 低波动日启用冲高回落策略 (带宽={current_bandwidth:.2f}元 < {PULLBACK_BANDWIDTH_THRESH}元)")
                
                    # 确定最终触发策略
                    triggered = momentum_triggered or boll_triggered or pullback_triggered
                    if momentum_triggered:
                        details = momentum_details
                        strategy_type = '动量策略'
                    elif boll_triggered:
                        details = boll_details
                        strategy_type = 'BOLL补充'
                    else:
                        details = pullback_details
                        strategy_type = '冲高回落'
                
                    # 低波动日接近触发日志
                    if is_low_volatility and not self.sell_active and total_bars >= 5 and pullback_details is not None:
                        if '满足数量' in pullback_details:
                            pb_met = pullback_details.get('满足数量', 0)
                            if pb_met >= 4:
                                self.daily_stats['near_trigger_count'] += 1
                                self.logger.info(
                                    f"📉 冲高回落接近触发 ({pb_met}/6): {latest_time} "
                                    f"盘中最高={pullback_details.get('盘中最高', 0):.2f} "
                                    f"回落={pullback_details.get('从高点回落', 0):+.3f} "
                                    f"收盘偏离={pullback_details.get('收盘偏离均价', 0):+.3f} "
                                    f"额={pullback_details.get('成交额万', 0):.0f}万"
                                )
                
                # v16.1.2: 正T买入条件判断（不再与倒T互斥，独立触发）
                zhengt_triggered = False
                zhengt_details = None
                if not self.zhengt_buy_active:
                    # 正T独立冷却期
                    if (total_bars - 1 - self.last_zhengt_signal_bar) >= COOLDOWN_BARS:
                        # v15.1硬约束1: 14:00后不做正T（回测胜率仅36%）
                        current_hour = int(str(latest_time)[11:13]) if len(str(latest_time)) >= 13 else 0
                        if current_hour >= ZHENGT_LATEST_HOUR:
                            pass  # 14:00后跳过正T
                        # v15.1硬约束2: 连跌>2天不做正T（回测连跌≥3天胜率骤降）
                        elif self.daily_stats.get('consecutive_down_days', 0) > ZHENGT_MAX_CONSEC_DOWN:
                            pass  # 连跌天数超标，跳过正T
                        else:
                            # v16.1: 传入当日振幅 + BOLL带宽用于硬约束判断
                            hp = self.daily_stats.get('high_price')
                            lp = self.daily_stats.get('low_price')
                            if hp is None or lp is None:
                                current_amplitude = 0
                            else:
                                current_amplitude = hp - lp
                            if current_amplitude > 100 or current_amplitude < 0:  # 异常值保护（过大或负数）
                                current_amplitude = 0
                            current_boll_width = float(completed['BOLL带宽']) if not np.isnan(completed.get('BOLL带宽', np.nan)) else 0
                            zhengt_triggered, zhengt_details = check_zhengT_buy_signal(completed, self.logger, amplitude=current_amplitude, boll_width=current_boll_width)

                # 提前计算量能预估（供倒T和正T信号共用）
                est = estimate_daily_amount_and_amplitude(df, self.daily_stats['prev_close'], self.daily_stats.get('open_price') or 0)
                
                # 根据量能环境确定目标差价和止损差价（供倒T和正T共用）
                if est:
                    if est['is_extreme_low']:
                        current_target = EXTREME_LOW_TARGET
                        current_stop_loss = 0.10
                    elif est['is_volume_low']:
                        current_target = TARGET_DIFF_LOW_VOLUME
                        current_stop_loss = STOP_LOSS_DIFF_LOW_VOLUME
                    else:
                        current_target = TARGET_DIFF_NORMAL
                        current_stop_loss = STOP_LOSS_DIFF_NORMAL
                else:
                    current_target = TARGET_DIFF_LOW_VOLUME
                    current_stop_loss = STOP_LOSS_DIFF_LOW_VOLUME

                if triggered:
                    self.signal_count_today += 1
                    self.last_signal_bar = total_bars - 1

                    self.sell_active = True
                    sell_price = details.get('价格', 0)
                    self.sell_price = sell_price
                    self.sell_window_min_price = sell_price  # v16.1.2 FIX: 初始化窗口最低价追踪
                    self.sell_time = details.get('时间', '')
                    self.buyback_notified = False
                    self.sell_stop_loss_triggered = False  # v15.3: 重置止损触发标志
                    self.sell_signal_bar = total_bars - 1  # v15.3: 记录信号触发bar编号
                    self.sell_eval_notified = False         # v15.3: 重置评估推送标志

                    # 使用已计算的量能预估生成信号信息
                    est_signal_info = ""
                    if est:
                        amp_display = f"{est.get('estimated_amplitude_pct', 0):.2f}%" if est.get('estimated_amplitude_pct', 0) > 0 else f"{est.get('estimated_amplitude', 0):.2f}元"
                        est_signal_info = (
                            f"\n\n📊 量能环境\n"
                            f"预估全天：{est.get('estimated_daily_yi', 0):.1f}亿\n"
                            f"预估振幅：{amp_display}"
                        )

                        if est.get('is_extreme_low'):
                            est_signal_info += f"\n⚠️ 极端缩量！目标差价{current_target}元，止损{current_stop_loss}元"
                        elif est.get('is_volume_low'):
                            est_signal_info += f"\n🟡 缩量日！目标差价{current_target}元，止损{current_stop_loss}元"
                        else:
                            est_signal_info += f"\n✅ 正常量能！目标差价{current_target}元，止损{current_stop_loss}元"

                    # 设置目标买回价和止损价（使用已计算的动态值）
                    self.target_buy_price = round(sell_price - current_target, 2)
                    self.stop_loss_price = round(sell_price + current_stop_loss, 2)
                    self.current_target_diff = current_target  # 保存用于显示
                    self.current_stop_loss_diff = current_stop_loss  # 保存用于显示

                    # 根据策略类型生成不同的消息内容
                    if strategy_type == '动量策略':
                        zhangdie = details.get('涨跌', 0)
                        fengxian = details.get('风险', 0)
                        amount_wan = details.get('成交额万', 0)
                        price_diff = details.get('股价差', 0)
                        macd_abs = details.get('MACD柱绝对', 0)
                        cond_labels = [
                            f"涨跌 {zhangdie:.1f} > {ZHANGDIE_THRESH}",
                            f"风险 {fengxian:.1f} > {FENGXIAN_THRESH}",
                            f"成交额 {amount_wan:.0f}万 ≥ {AMOUNT_THRESH_WAN}万",
                            f"股价差 {price_diff:+.3f} > {MA_ABOVE}",
                            f"|MACD柱| {macd_abs:.4f} > {MACD_BAR_THRESH}",
                        ]
                        cond_marks = ["✅" if c else "❌" for c in details.get('满足条件', {}).values()]
                        strategy_badge = "🔥 动量策略（主力）"
                    elif strategy_type == 'BOLL补充':
                        boll_upper = details.get('BOLL上轨', 0)
                        high_price = details.get('最高', 0)
                        amount_wan = details.get('成交额万', 0)
                        price_diff = details.get('股价差', 0)
                        macd_bar = details.get('MACD柱', 0)
                        cond_labels = [
                            f"触碰上轨 {high_price:.2f} ≥ {boll_upper*BOLL_TOUCH_RATIO:.3f}",
                            f"成交额 {amount_wan:.0f}万 ≥ {BOLL_AMOUNT_THRESH_WAN}万",
                            f"股价差 {price_diff:+.3f} > {BOLL_MA_ABOVE}",
                            f"偏离均价 {price_diff:+.3f} > {BOLL_DEVIATION_THRESH}",
                            f"MACD柱 {macd_bar:.4f} > {BOLL_MACD_THRESH}",
                        ]
                        cond_marks = ["✅" if c else "❌" for c in details.get('满足条件', {}).values()]
                        strategy_badge = "📊 BOLL补充策略"
                    else:  # 冲高回落策略 v16.0
                        high_price = details.get('最高', 0)
                        day_high_price = details.get('盘中最高', 0)
                        high_diff_from_avg = details.get('盘中最高偏离均价', 0)
                        pullback_from_high = details.get('从高点回落', 0)
                        close_diff = details.get('收盘偏离均价', 0)
                        amount_wan = details.get('成交额万', 0)
                        current_price = details.get('价格', 0)
                        boll_upper = details.get('BOLL上轨', 0)
                        cond_labels = [
                            f"盘中最高偏离均价>{PULLBACK_DAY_HIGH_DEVIATION} {high_diff_from_avg:+.3f}",
                            f"从高点回落>{PULLBACK_PULLBACK_FROM_HIGH} {pullback_from_high:+.3f}",
                            f"收盘偏离均价>{PULLBACK_CLOSE_ABOVE_AVG} {close_diff:+.3f}",
                            f"成交额≥{PULLBACK_AMOUNT_THRESH_WAN}万 {amount_wan:.0f}万",
                            f"已从上轨回落 {current_price:.2f}<{boll_upper:.3f}",
                            f"时间窗口 {PULLBACK_START[0]}:{PULLBACK_START[1]:02d}-{PULLBACK_END[0]}:{PULLBACK_END[1]:02d}",
                        ]
                        cond_marks = ["✅" if c else "❌" for c in details.get('满足条件', {}).values()]
                        strategy_badge = "📉 冲高回落v16.0（低波动日）"
                    
                    sell_price = details.get('价格', 0)
                    msg = (
                        f"{strategy_badge}\n"
                        f"{details.get('时间', '')}  触发卖出信号！\n\n"
                        f"当前指标：\n"
                        f"{'  '.join([f'{m} {l}' for m, l in zip(cond_marks, cond_labels)])}\n\n"
                        f"卖出参考价: {sell_price}元\n"
                        f"建议挂买单: {self.target_buy_price}元（目标差价{self.current_target_diff}元）\n"
                        f"止损买回价: {self.stop_loss_price}元（止损差价{self.current_stop_loss_diff}元）"
                        f"{est_signal_info}\n\n"
                        f"请打开同花顺 App 操作！\n"
                        f"卖出后会持续监控，到价自动提醒买回！"
                    )

                    self.logger.info(f"🚨 卖出信号！{strategy_type} {details.get('时间', '')} 价格={sell_price} "
                                    f"成交额={details.get('成交额万', 0):.0f}万")

                    notify(f"🚨 中国平安 — {strategy_type}卖出信号！", msg, level="sell")

                    # 写入信号历史（供网站API读取）
                    save_signal_to_history({
                        "direction": "sell",
                        "type": strategy_type,
                        "price": sell_price,
                        "time": details.get("时间", ""),
                        "target": self.current_target_diff,
                        "status": "active"
                    })
                else:
                    # 动量策略接近触发日志
                    if momentum_details is not None and '涨跌' in momentum_details:
                        met = sum(momentum_details.get('满足条件', {}).values())
                        total_conds = len(momentum_details.get('满足条件', {}))
                        if met >= total_conds - 1:  # 差1个条件就触发
                            self.daily_stats['near_trigger_count'] += 1
                            self.logger.info(
                                f"接近触发 动量({met}/{total_conds}): {latest_time} "
                                f"涨跌={momentum_details.get('涨跌', 0):.1f} 风险={momentum_details.get('风险', 0):.1f} "
                                f"额={momentum_details.get('成交额万', 0):.0f}万 差={momentum_details.get('股价差', 0):+.3f} "
                                f"|MACD|={momentum_details.get('MACD柱绝对', 0):.4f}"
                            )
                    
                    # BOLL补充策略接近触发日志
                    if boll_details is not None and 'BOLL上轨' in boll_details:
                        met = sum(boll_details.get('满足条件', {}).values())
                        total_conds = len(boll_details.get('满足条件', {}))
                        if met >= total_conds - 1:  # 差1个条件就触发
                            self.daily_stats['near_trigger_count'] += 1
                            self.logger.info(
                                f"接近触发 BOLL({met}/{total_conds}): {latest_time} "
                                f"上轨={boll_details.get('BOLL上轨', 0):.3f} "
                                f"额={boll_details.get('成交额万', 0):.0f}万 差={boll_details.get('股价差', 0):+.3f} "
                                f"MACD={boll_details.get('MACD柱', 0):.4f}"
                            )

                # 正T买入信号处理
                if zhengt_triggered and zhengt_details:
                    self.zhengt_signal_count_today += 1
                    self.last_zhengt_signal_bar = total_bars - 1

                    self.zhengt_buy_active = True
                    zhengt_price = zhengt_details.get('价格', 0)
                    self.zhengt_buy_price = zhengt_price
                    self.zhengt_window_max_price = zhengt_price  # v16.1.2 FIX: 初始化窗口最高价追踪
                    self.zhengt_buy_time = zhengt_details.get('时间', '')
                    # v15.1: 正T使用专用目标差价（0.20元），不再与倒T共用
                    self.zhengt_target_sell_price = round(zhengt_price + ZHENGT_TARGET_DIFF, 2)
                    self.zhengt_stop_loss_price = round(zhengt_price - ZHENGT_STOP_LOSS_DIFF, 2)
                    self.zhengt_sell_notified = False
                    self.zhengt_stop_loss_triggered = False  # v15.3: 重置正T止损触发标志
                    self.zhengt_signal_bar = total_bars - 1  # v15.3: 记录正T信号触发bar编号
                    self.zhengt_eval_notified = False         # v15.3: 重置正T评估推送标志

                    zhengt_cond_labels = [
                        f"偏离均价 {zhengt_details.get('偏离均价', 0):+.3f} > {ZHENGT_MA_BELOW}元",
                        f"风险 {zhengt_details.get('风险', 0):.1f} < {ZHENGT_RISK_THRESH}",
                        f"成交额 {zhengt_details.get('成交额万', 0):.0f}万 ≥ {ZHENGT_AMOUNT_THRESH_WAN}万",
                        f"涨跌 {zhengt_details.get('涨跌', 0):.1f} ≤ {ZHENGT_ZD_THRESH}",
                        f"日振幅 {zhengt_details.get('日振幅', 0):.2f} ≥ {ZHENGT_MIN_AMPLITUDE}元",
                        f"BOLL带宽 {zhengt_details.get('BOLL带宽', 0):.2f}元 > {ZHENGT_MIN_BOLL_WIDTH}元",
                    ]
                    zhengt_cond_marks = ["✅" if c else "❌" for c in zhengt_details.get('满足条件', [])]
                    
                    # 正T量能环境信息
                    zhengt_est_info = ""
                    if est:
                        if est.get('is_extreme_low'):
                            zhengt_est_info = f"\n⚠️ 极端缩量！目标{ZHENGT_TARGET_DIFF}元，止损{ZHENGT_STOP_LOSS_DIFF}元"
                        elif est.get('is_volume_low'):
                            zhengt_est_info = f"\n🟡 缩量日！目标{ZHENGT_TARGET_DIFF}元，止损{ZHENGT_STOP_LOSS_DIFF}元"
                        else:
                            zhengt_est_info = f"\n✅ 正常量能！目标{ZHENGT_TARGET_DIFF}元，止损{ZHENGT_STOP_LOSS_DIFF}元"

                    zhengt_msg = (
                        f"{zhengt_details.get('时间', '')}  触发正T买入信号！\n\n"
                        f"当前指标：\n"
                        f"{'  '.join([f'{m} {l}' for m, l in zip(zhengt_cond_marks, zhengt_cond_labels)])}\n\n"
                        f"买入参考价: {zhengt_price}元\n"
                        f"建议挂卖单: {self.zhengt_target_sell_price}元（目标差价{ZHENGT_TARGET_DIFF}元）\n"
                        f"止损卖出价: {self.zhengt_stop_loss_price}元（止损差价{ZHENGT_STOP_LOSS_DIFF}元）"
                        f"{zhengt_est_info}\n\n"
                        f"请打开同花顺 App 操作！\n"
                        f"买入后会持续监控，到价自动提醒卖出！"
                    )

                    self.logger.info(f"🟢 正T买入信号！{zhengt_details.get('时间', '')} 价格={zhengt_price} "
                                    f"涨跌={zhengt_details.get('涨跌', 0)} 风险={zhengt_details.get('风险', 0)} "
                                    f"成交额={zhengt_details.get('成交额万', 0):.0f}万")

                    notify("🟢 中国平安 — 正T买入信号！", zhengt_msg, level="buy")

                    # 写入信号历史（供网站API读取）
                    save_signal_to_history({
                        "direction": "buy",
                        "type": "正T策略",
                        "price": zhengt_price,
                        "time": zhengt_details.get("时间", ""),
                        "target": ZHENGT_TARGET_DIFF,
                        "status": "active"
                    })

                time.sleep(check_interval)

            except Exception as e:
                self.logger.error(f"运行出错: {e}", exc_info=True)
                notify("❌ 监控异常", f"监控系统出错: {e}\n将自动恢复...", level="error")
                time.sleep(10)

        # 清理
        self.logger.info("监控系统已停止")
        self.tdx.disconnect()
        release_pid()


# ==================== 启动入口 ====================

if __name__ == "__main__":
    # 防重复实例（延迟写入，等子进程稳定）
    # 后台启动时先跳过PID检查
    _skip_pid = os.environ.get("SKIP_PID_CHECK") == "1"
    pid_file = None
    if not _skip_pid:
        pid_file = acquire_pid()

    try:
        monitor = PAMonitor()
        # 启动后写入实际PID
        PID_FILE.parent.mkdir(parents=True, exist_ok=True)
        PID_FILE.write_text(str(os.getpid()))
        monitor.run()
    finally:
        release_pid()
