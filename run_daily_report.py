"""
收盘自动复盘脚本 — 每日15:05自动运行

功能：
1. 从pytdx拉取当天1分钟K线
2. 调用daily_report_enhanced生成复盘报告和图表
3. 推送报告到Bark（iPhone，带图表图片）+ ntfy（Android）
4. 保存报告到日志目录

图表访问：Nginx 8888端口 /pa-charts/ 路径托管
  URL格式: http://175.178.232.233:8888/pa-charts/2026-04-26_策略分析.png

部署：systemd timer，周一至周五 15:05 自动运行
"""

import os
import sys
import json
import requests
from datetime import datetime
from pathlib import Path

# 确保项目目录在搜索路径
PROJECT_DIR = Path(__file__).parent
sys.path.insert(0, str(PROJECT_DIR))

# 清除代理（避免推送被拦截）
for key in ['http_proxy', 'https_proxy', 'HTTP_PROXY', 'HTTPS_PROXY', 'all_proxy', 'ALL_PROXY']:
    os.environ.pop(key, None)

# 导入项目模块
from daily_report_enhanced import generate_enhanced_report
from pa_notify import send_bark, send_ntfy

CONFIG_PATH = PROJECT_DIR / "monitor_config.json"
SERVER_IP = "175.178.232.233"
CHART_BASE_URL = f"http://{SERVER_IP}:8888/pa-charts"


def load_config():
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def fetch_today_klines():
    """从pytdx获取最近交易日1分钟K线和昨收价
    
    工作日：获取当天数据
    周末/非交易日：自动获取最近交易日的数据
    TDX服务器周末关闭时：返回None，脚本跳过复盘
    """
    try:
        from pytdx.hq import TdxHq_API
        
        api = TdxHq_API()
        prev_close = 0
        last_trade_date = ""
        
        # 第一步：从日K线获取最近交易日和昨收价
        if not api.connect('119.147.212.81', 7709):
            print("⚠️ TDX服务器无法连接（周末维护中），跳过复盘")
            return None, 0
        
        try:
            daily_df = api.to_df(api.get_security_bars(9, 1, '601318', 0, 10))
            if daily_df is not None and len(daily_df) >= 2:
                last_trade_date = str(daily_df.iloc[-1]['datetime'])[:10]
                prev_close = float(daily_df.iloc[-2]['close'])
                today_str = datetime.now().strftime('%Y-%m-%d')
                if last_trade_date != today_str:
                    print(f"  📅 今天非交易日，使用最近交易日: {last_trade_date}")
                print(f"  昨收价: {prev_close:.2f}")
        finally:
            api.disconnect()
        
        if not last_trade_date:
            print("❌ 无法获取日K线数据")
            return None, 0
        
        # 第二步：获取1分钟K线
        df = None
        if not api.connect('119.147.212.81', 7709):
            print("⚠️ TDX服务器二次连接失败")
            return None, 0
        
        try:
            df = api.to_df(api.get_security_bars(8, 1, '601318', 0, 240))
        finally:
            api.disconnect()
        
        if df is None or len(df) == 0:
            print("❌ 未获取到1分钟K线数据")
            return None, 0
        
        # 检查数据有效性
        if len(df) == 1 and df.iloc[0].isna().all():
            print("❌ pytdx返回无效数据（可能非交易日）")
            return None, 0
        
        # 重命名列
        col_map = {
            'open': '开盘', 'high': '最高', 'low': '最低', 
            'close': '收盘', 'vol': '成交量', 'amount': '成交额'
        }
        df = df.rename(columns=col_map)
        
        # 时间列统一
        if 'datetime' in df.columns:
            df = df.rename(columns={'datetime': '时间'})
        
        # 成交额转换
        df['成交额_万'] = df['成交额'] / 10000
        
        # 只保留最近交易日的数据
        df['时间'] = df['时间'].astype(str)
        df = df[df['时间'].str.startswith(last_trade_date)].copy()
        
        if len(df) == 0:
            print(f"❌ {last_trade_date} 无1分钟K线数据")
            return None, 0
        
        print(f"✅ 获取到 {len(df)} 根K线，日期={last_trade_date}，昨收={prev_close:.2f}")
        return df, prev_close
        
    except Exception as e:
        print(f"❌ 获取K线数据失败: {e}")
        import traceback
        traceback.print_exc()
        return None, 0


def push_report(report_text: str, chart_filename: str = ""):
    """推送复盘报告到手机"""
    config = load_config()
    
    bark_urls = config.get("bark_urls", [])
    ntfy_topic = config.get("ntfy_topic", "")
    ntfy_server = config.get("ntfy_server", "https://ntfy.sh")
    
    success_count = 0
    chart_url = f"{CHART_BASE_URL}/{chart_filename}" if chart_filename else ""
    
    # 1. 推送图表+报告到Bark（带图片预览，点击看大图）
    for bark_url in bark_urls:
        if not bark_url:
            continue
        try:
            # Bark限制单条约4000字符，超长截断
            body = report_text[:3800] + ("..." if len(report_text) > 3800 else "")
            payload = {
                "title": "📊 平安复盘",
                "body": body,
                "group": "平安复盘",
                "sound": "glass",
                "isArchive": 1,
            }
            # 附加图表：icon显示缩略图，url点击打开大图
            if chart_url:
                payload["icon"] = chart_url
                payload["url"] = chart_url
            
            api_url = f"{bark_url.rstrip('/')}/"
            resp = requests.post(api_url, json=payload, timeout=10, proxies={"http": None, "https": None})
            if resp.status_code == 200 and resp.json().get("code") == 200:
                success_count += 1
                print(f"  ✅ Bark推送成功（含图表）")
            else:
                print(f"  ❌ Bark推送失败: HTTP {resp.status_code}")
        except Exception as e:
            print(f"  ❌ Bark推送失败: {e}")
    
    # 2. 推送到ntfy（Android，纯文本）
    if ntfy_topic:
        try:
            body = report_text[:3800] + ("..." if len(report_text) > 3800 else "")
            if send_ntfy("📊 平安复盘", body, ntfy_topic, ntfy_server, priority="default"):
                success_count += 1
                print(f"  ✅ ntfy推送成功")
        except Exception as e:
            print(f"  ❌ ntfy推送失败: {e}")
    
    return success_count > 0


def save_report(report_text: str):
    """保存报告到日志目录"""
    log_dir = PROJECT_DIR / "monitor_logs"
    log_dir.mkdir(parents=True, exist_ok=True)
    
    today_str = datetime.now().strftime('%Y-%m-%d')
    report_path = log_dir / f"{today_str}_复盘报告.txt"
    
    with open(report_path, "w", encoding="utf-8") as f:
        f.write(report_text)
    
    print(f"📝 报告已保存: {report_path}")
    return str(report_path)


def main():
    today = datetime.now().strftime('%Y-%m-%d')
    weekday = ['周一','周二','周三','周四','周五','周六','周日'][datetime.now().weekday()]
    print(f"{'='*50}")
    print(f"📊 收盘复盘报告 — {today} {weekday}")
    print(f"{'='*50}")
    
    # 1. 获取K线数据
    print("\n📡 获取K线数据...")
    df, prev_close = fetch_today_klines()
    
    if df is None or len(df) == 0:
        print("⚠️ 无可用K线数据，跳过复盘")
        return
    
    # 2. 计算指标
    print("\n📐 计算技术指标...")
    try:
        from pa_monitor import calc_indicators
        df = calc_indicators(df)
    except ImportError:
        print("⚠️ 无法导入calc_indicators，使用daily_report_enhanced内置计算")
    
    # 3. 生成复盘报告
    print("\n📊 生成复盘报告...")
    report, chart_path = generate_enhanced_report(df, signal_count=0, zhengt_count=0, prev_close=prev_close)
    
    print(f"\n{report}")
    
    # 4. 保存报告
    save_report(report)
    
    # 5. 提取图表文件名
    chart_filename = ""
    if chart_path and Path(chart_path).exists():
        chart_filename = Path(chart_path).name
        print(f"📈 图表已生成: {chart_path}")
        print(f"   外网URL: {CHART_BASE_URL}/{chart_filename}")
    
    # 6. 推送到手机
    print("\n📱 推送到手机...")
    push_ok = push_report(report, chart_filename)
    if push_ok:
        print("✅ 推送成功！")
    else:
        print("⚠️ 推送失败，请检查配置")
    
    print(f"\n{'='*50}")
    print(f"📊 复盘完成 — {datetime.now().strftime('%H:%M:%S')}")
    print(f"{'='*50}")


if __name__ == "__main__":
    main()
