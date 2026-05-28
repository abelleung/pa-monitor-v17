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
  - 新增 STRATEGY_CONFIG['EVAL_WINDOW_BARS']=90：90分钟窗口到期后自动评估信号理论有效性
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
  - 新交易日重置新增 self.last_signal_bar = -STRATEGY_CONFIG['COOLDOWN_BARS'] - 1

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
    # v16.1.2: 指标和策略函数已解耦到独立文件
    from indicators import (
        calc_indicators,
        estimate_daily_amount_and_amplitude,
        safe_float,
        get_time_tuple,
        is_trade_time,
        _interpolate_cum_ratio,
    )
    from strategies import (
        check_boll_sell_signal,
        check_momentum_sell_signal,
        check_zhengT_buy_signal,
        check_pullback_sell_signal,
    )

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
    """加载配置，并覆盖策略参数（如果配置文件中有 strategy 节）"""
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        config = json.load(f)
    # v16.1.2: 从配置文件覆盖策略参数
    if 'strategy' in config:
        STRATEGY_CONFIG.update(config['strategy'])
        logging.getLogger(__name__).info(f"已从配置文件覆盖 {len(config['strategy'])} 个策略参数")
    return config


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

def hhv(series, period):
    result = np.full(len(series), np.nan)
    for i in range(len(series)):
        start = max(0, i - period + 1)
        window = series[start:i+1]
        valid = window[~np.isnan(window)]
        if len(valid) > 0:
            result[i] = np.max(valid)
    return result

