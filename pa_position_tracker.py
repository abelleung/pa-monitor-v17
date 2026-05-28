#!/usr/bin/env python3
"""
中国平安持仓跟踪分析系统
功能：
1. 记录每次截图的持仓数据
2. 对比同等股数下的成本变化
3. 推算不同股数下的等效成本
4. 计算做T效果和成本递减进度
"""

import json
import os
from datetime import datetime
from dataclasses import dataclass, asdict
from typing import List, Optional, Tuple

@dataclass
class PositionRecord:
    """持仓记录"""
    date: str
    time: str
    quantity: int          # 持股数量
    cost_price: float      # 持仓成本价
    current_price: float   # 当前股价
    market_value: float    # 市值
    total_cost: float      # 总成本 (quantity * cost_price)
    floating_pnl: float    # 浮动盈亏
    pnl_percent: float     # 盈亏百分比
    notes: str = ""        # 备注

@dataclass
class TradeRecord:
    """交易记录"""
    date: str
    time: str
    type: str              # "buy" 或 "sell"
    quantity: int          # 交易数量
    price: float           # 交易价格
    amount: float          # 交易金额
    notes: str = ""
    # v15.3: 双口径盈亏
    actual_pnl: float = 0.0        # 实际操作盈亏（按止盈/止损成交价计算）
    signal_valid: bool = None      # 信号理论有效性（90分钟窗口评估：倒T<卖出价-0.25/正T>买入价+0.20）
    signal_eval_price: float = 0.0 # 评估时刻价格（用于计算理论有效性）

class PositionTracker:
    """持仓跟踪器"""
    
    def __init__(self, data_file: str = "pa_position_tracker.json"):
        self.data_file = data_file
        self.data = self._load_data()
    
    def _load_data(self) -> dict:
        """加载数据文件"""
        if os.path.exists(self.data_file):
            with open(self.data_file, 'r', encoding='utf-8') as f:
                return json.load(f)
        return self._init_data()
    
    def _init_data(self) -> dict:
        """初始化数据结构"""
        return {
            "stock_name": "中国平安",
            "stock_code": "601318",
            "tracking_start_date": datetime.now().strftime("%Y-%m-%d"),
            "target": "成本递减至负数",
            "records": [],
            "trades": [],
            "statistics": {
                "initial_cost": 0,
                "current_cost": 0,
                "cost_reduction": 0,
                "total_trades": 0,
                "successful_t_trades": 0,
                # v15.3: 双口径统计
                "signal_valid_count": 0,       # 信号理论有效次数
                "signal_invalid_count": 0,     # 信号理论失败次数
                "signal_eval_pending": 0       # 待评估次数
            }
        }
    
    def _save_data(self):
        """保存数据"""
        with open(self.data_file, 'w', encoding='utf-8') as f:
            json.dump(self.data, f, ensure_ascii=False, indent=2)
    
    def add_record(self, quantity: int, cost_price: float, current_price: float,
                   market_value: float, floating_pnl: float, pnl_percent: float,
                   notes: str = "") -> str:
        """
        添加新的持仓记录
        
        Args:
            quantity: 持股数量
            cost_price: 持仓成本价
            current_price: 当前股价
            market_value: 市值
            floating_pnl: 浮动盈亏
            pnl_percent: 盈亏百分比
            notes: 备注
        """
        now = datetime.now()
        total_cost = quantity * cost_price
        
        record = PositionRecord(
            date=now.strftime("%Y-%m-%d"),
            time=now.strftime("%H:%M"),
            quantity=quantity,
            cost_price=cost_price,
            current_price=current_price,
            market_value=market_value,
            total_cost=total_cost,
            floating_pnl=floating_pnl,
            pnl_percent=pnl_percent,
            notes=notes
        )
        
        # 转换为字典并添加
        self.data["records"].append(asdict(record))
        
        # 更新统计
        if len(self.data["records"]) == 1:
            self.data["statistics"]["initial_cost"] = cost_price
        self.data["statistics"]["current_cost"] = cost_price
        
        self._save_data()
        
        # 生成分析报告
        return self._generate_report(record)
    
    def _generate_report(self, current: PositionRecord) -> str:
        """生成持仓对比分析报告"""
        records = self.data["records"]
        
        if len(records) == 1:
            # 首次记录
            return self._format_first_record(current)
        
        # 获取上一次记录
        prev_dict = records[-2]
        previous = PositionRecord(**prev_dict)
        
        report = []
        report.append("=" * 50)
        report.append(f"📊 中国平安持仓跟踪报告")
        report.append(f"记录时间: {current.date} {current.time}")
        report.append("=" * 50)
        
        # 1. 当前持仓状态
        report.append("\n【当前持仓】")
        report.append(f"  持股数量: {current.quantity:,} 股")
        report.append(f"  持仓成本: ¥{current.cost_price:.3f}")
        report.append(f"  当前股价: ¥{current.current_price:.3f}")
        report.append(f"  市值: ¥{current.market_value:,.2f}")
        report.append(f"  浮动盈亏: ¥{current.floating_pnl:,.2f} ({current.pnl_percent:+.2f}%)")
        
        # 2. 与上次对比（同等股数）
        report.append("\n【与上次对比 - 同等股数对比】")
        report.append(f"  上次股数: {previous.quantity:,} 股")
        report.append(f"  上次成本: ¥{previous.cost_price:.3f}")
        report.append(f"  本次成本: ¥{current.cost_price:.3f}")
        
        cost_change = current.cost_price - previous.cost_price
        if cost_change < 0:
            report.append(f"  ✅ 成本下降: ¥{abs(cost_change):.3f} ↓")
        elif cost_change > 0:
            report.append(f"  ⚠️ 成本上升: ¥{cost_change:.3f} ↑")
        else:
            report.append(f"  ➖ 成本持平")
        
        # 3. 等效成本推算（不同股数情况）
        if current.quantity != previous.quantity:
            report.append("\n【等效成本推算】")
            report.append(f"  注: 股数变化 {previous.quantity:,} → {current.quantity:,}")
            
            # 推算如果股数回到上次数量，成本会是多少
            if current.quantity > 0:
                # 当前总成本
                current_total_cost = current.quantity * current.cost_price
                
                # 假设买回/卖出到上次股数
                share_diff = current.quantity - previous.quantity
                
                if share_diff > 0:
                    # 当前股数更多，假设卖出到上次股数
                    hypothetical_sell = share_diff * current.current_price
                    new_total_cost = current_total_cost - hypothetical_sell
                    if previous.quantity > 0:
                        equivalent_cost = new_total_cost / previous.quantity
                        report.append(f"  若卖出 {share_diff:,} 股至 {previous.quantity:,} 股:")
                        report.append(f"    等效成本: ¥{equivalent_cost:.3f}")
                        equiv_change = equivalent_cost - previous.cost_price
                        if equiv_change < 0:
                            report.append(f"    相比上次成本: 下降 ¥{abs(equiv_change):.3f} ✅")
                        else:
                            report.append(f"    相比上次成本: 上升 ¥{equiv_change:.3f}")
                else:
                    # 当前股数更少，假设买回到上次股数
                    shares_to_buy = abs(share_diff)
                    hypothetical_buy = shares_to_buy * current.current_price
                    new_total_cost = current_total_cost + hypothetical_buy
                    equivalent_cost = new_total_cost / previous.quantity
                    report.append(f"  若买入 {shares_to_buy:,} 股至 {previous.quantity:,} 股:")
                    report.append(f"    等效成本: ¥{equivalent_cost:.3f}")
                    equiv_change = equivalent_cost - previous.cost_price
                    if equiv_change < 0:
                        report.append(f"    相比上次成本: 下降 ¥{abs(equiv_change):.3f} ✅")
                    else:
                        report.append(f"    相比上次成本: 上升 ¥{equiv_change:.3f}")
        
        # 4. 累计进度
        report.append("\n【累计进度】")
        initial_cost = self.data["statistics"]["initial_cost"]
        total_reduction = initial_cost - current.cost_price
        reduction_percent = (total_reduction / initial_cost * 100) if initial_cost > 0 else 0
        
        report.append(f"  初始成本: ¥{initial_cost:.3f}")
        report.append(f"  当前成本: ¥{current.cost_price:.3f}")
        report.append(f"  累计降本: ¥{total_reduction:.3f} ({reduction_percent:.2f}%)")
        
        # 距离负成本还有多远
        if current.cost_price > 0:
            progress_to_zero = (initial_cost - current.cost_price) / initial_cost * 100
            report.append(f"  归零进度: {progress_to_zero:.1f}%")
        else:
            report.append(f"  🎉 已实现负成本！")
        
        # 5. 做T效果估算
        if len(records) >= 2:
            report.append("\n【做T效果分析】")
            report.append(f"  记录次数: {len(records)}")
            
            # 简单估算：如果成本下降，估算节省金额
            if total_reduction > 0 and current.quantity > 0:
                saved_amount = total_reduction * current.quantity
                report.append(f"  估算节省: ¥{saved_amount:,.2f} (基于当前持仓)")
            
            # v15.3: 双口径统计
            stats = self.data["statistics"]
            valid = stats.get("signal_valid_count", 0)
            invalid = stats.get("signal_invalid_count", 0)
            pending = stats.get("signal_eval_pending", 0)
            total_signals = valid + invalid
            
            report.append("\n【双口径做T统计】")
            report.append(f"  信号理论有效: {valid}次")
            report.append(f"  信号理论失败: {invalid}次")
            if pending > 0:
                report.append(f"  待评估: {pending}次")
            if total_signals > 0:
                report.append(f"  理论胜率: {valid/total_signals*100:.0f}%")
                report.append(f"  （评估标准：倒T<卖出价-0.25元 / 正T>买入价+0.20元）")
        
        report.append("\n" + "=" * 50)
        
        return "\n".join(report)
    
    def _format_first_record(self, record: PositionRecord) -> str:
        """格式化首次记录"""
        report = []
        report.append("=" * 50)
        report.append(f"📊 中国平安持仓跟踪 - 初始记录")
        report.append(f"记录时间: {record.date} {record.time}")
        report.append("=" * 50)
        report.append(f"\n持股数量: {record.quantity:,} 股")
        report.append(f"持仓成本: ¥{record.cost_price:.3f}")
        report.append(f"当前股价: ¥{record.current_price:.3f}")
        report.append(f"市值: ¥{record.market_value:,.2f}")
        report.append(f"浮动盈亏: ¥{record.floating_pnl:,.2f}")
        report.append(f"\n🎯 目标: 成本递减至负数")
        report.append("=" * 50)
        return "\n".join(report)
    
    def get_history(self, limit: int = 10) -> str:
        """获取历史记录"""
        records = self.data["records"][-limit:]
        
        report = []
        report.append("📈 历史持仓记录")
        report.append("-" * 60)
        report.append(f"{'日期':<12} {'时间':<8} {'数量':>8} {'成本价':>10} {'股价':>10} {'盈亏':>12}")
        report.append("-" * 60)
        
        for r in records:
            report.append(f"{r['date']:<12} {r['time']:<8} {r['quantity']:>8,} ¥{r['cost_price']:>9.3f} ¥{r['current_price']:>9.3f} ¥{r['floating_pnl']:>11.2f}")
        
        report.append("-" * 60)
        return "\n".join(report)
    
    def add_trade(self, trade_type: str, quantity: int, price: float,
                  notes: str = "", actual_pnl: float = 0.0,
                  signal_valid: bool = None, signal_eval_price: float = 0.0):
        """添加交易记录
        
        Args:
            trade_type: "buy" 或 "sell"
            quantity: 交易数量
            price: 交易价格
            notes: 备注
            actual_pnl: v15.3 实际操作盈亏（按止盈/止损成交价计算）
            signal_valid: v15.3 信号理论有效性（90分钟窗口评估）
            signal_eval_price: v15.3 评估时刻价格
        """
        now = datetime.now()
        amount = quantity * price
        
        trade = TradeRecord(
            date=now.strftime("%Y-%m-%d"),
            time=now.strftime("%H:%M"),
            type=trade_type,
            quantity=quantity,
            price=price,
            amount=amount,
            notes=notes,
            actual_pnl=actual_pnl,
            signal_valid=signal_valid,
            signal_eval_price=signal_eval_price
        )
        
        self.data["trades"].append(asdict(trade))
        self.data["statistics"]["total_trades"] += 1
        
        # v15.3: 更新信号理论有效性统计
        if signal_valid is True:
            self.data["statistics"]["signal_valid_count"] += 1
        elif signal_valid is False:
            self.data["statistics"]["signal_invalid_count"] += 1
        else:
            self.data["statistics"]["signal_eval_pending"] += 1
        
        self._save_data()
        
        # 生成双口径报告
        report = f"✅ 已记录交易: {trade_type.upper()} {quantity}股 @ ¥{price:.2f}"
        if actual_pnl != 0:
            report += f"\n💰 实际盈亏: ¥{actual_pnl:+.2f}"
        if signal_valid is not None:
            report += f"\n📋 信号理论: {'✅有效' if signal_valid else '❌失败'}"
        else:
            report += f"\n📋 信号理论: ⏳待评估"
        return report


# 便捷函数
def add_position_record(quantity: int, cost_price: float, current_price: float,
                       market_value: float, floating_pnl: float, pnl_percent: float,
                       notes: str = "") -> str:
    """添加持仓记录的便捷函数"""
    tracker = PositionTracker()
    return tracker.add_record(quantity, cost_price, current_price, 
                             market_value, floating_pnl, pnl_percent, notes)


def parse_screenshot_data(quantity: int, cost_price: float, current_price: float,
                         market_value: float, floating_pnl: float, pnl_percent: float) -> str:
    """
    从截图数据解析并记录
    参数直接从截图中获取
    """
    return add_position_record(
        quantity=quantity,
        cost_price=cost_price,
        current_price=current_price,
        market_value=market_value,
        floating_pnl=floating_pnl,
        pnl_percent=pnl_percent,
        notes="截图录入"
    )


if __name__ == "__main__":
    # 测试：记录今天的数据
    result = parse_screenshot_data(
        quantity=8200,
        cost_price=58.897,
        current_price=58.820,
        market_value=482324.00,
        floating_pnl=-634.77,
        pnl_percent=-0.13
    )
    print(result)
    
    # 显示历史
    tracker = PositionTracker()
    print("\n" + tracker.get_history())
