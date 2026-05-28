"""
中国平安 v10.2 倒T策略 — 推送通知模块
支持 Bark（iOS）、ntfy（Android/跨平台）和 企业微信机器人 Webhook

使用方法：
  1. Bark：在 App Store 安装 Bark，打开后复制推送 URL
  2. ntfy：下载 ntfy 应用，创建主题（如 teresa），订阅即可接收推送
  3. 企业微信：创建群 → 群设置 → 群机器人 → 添加机器人 → 复制 Webhook URL
  4. 在 monitor_config.json 中填入对应配置
"""

import json
import os
import requests
from datetime import datetime
from pathlib import Path

# 配置文件路径
CONFIG_PATH = Path(__file__).parent / "monitor_config.json"


def load_config() -> dict:
    """加载配置文件"""
    if not CONFIG_PATH.exists():
        return {}
    with open(CONFIG_PATH, "r", encoding="utf-8") as f:
        return json.load(f)


def send_bark(title: str, body: str, url: str, group: str = "中国平安多多", sound: str = "alarm"):
    """通过 Bark 推送到 iOS（POST JSON，通知预览干净无参数）"""
    if not url:
        return False
    try:
        # v11.6: Bark强制不走代理（避免Clash等代理拦截api.day.app）
        # 注意：pa_monitor.py启动时已清除环境变量中的代理设置，
        # 这里通过proxies参数双重保障
        payload = {
            "title": title,
            "body": body,
            "group": group,
            "sound": sound,
            "isArchive": 1,
        }
        api_url = f"{url.rstrip('/')}/"

        resp = requests.post(api_url, json=payload, timeout=10, proxies={"http": None, "https": None})
        if resp.status_code == 200:
            data = resp.json()
            if data.get("code") == 200:
                return True
            else:
                print(f"  [Bark] 返回错误: {data}")
                return False
        else:
            print(f"  [Bark] HTTP {resp.status_code}")
            return False
    except Exception as e:
        print(f"  [Bark] 推送失败: {e}")
        return False


def send_wechat_bot(title: str, body: str, url: str):
    """通过企业微信机器人 Webhook 推送"""
    if not url:
        return False
    try:
        # 企业微信群机器人支持 markdown 格式
        content = f"## {title}\n\n{body}"
        resp = requests.post(
            url,
            json={"msgtype": "markdown", "markdown": {"content": content}},
            timeout=10,
            proxies={"http": None, "https": None},
        )
        if resp.status_code == 200:
            data = resp.json()
            if data.get("errcode") == 0:
                return True
            else:
                print(f"  [企业微信] 返回错误: {data}")
                return False
        else:
            print(f"  [企业微信] HTTP {resp.status_code}")
            return False
    except Exception as e:
        print(f"  [企业微信] 推送失败: {e}")
        return False


def send_ntfy(title: str, body: str, topic: str, server: str = "https://ntfy.sh", priority: str = "default"):
    """
    通过 ntfy 推送通知（支持 Android/iOS/Web）
    
    priority: default, low, high, urgent
    """
    if not topic:
        return False
    try:
        import re
        
        # 清理标题：移除 emoji 和特殊字符，避免 header 编码问题
        def clean_header(text):
            """清理字符串，只保留 ASCII 字符"""
            # 移除所有非 ASCII 字符
            text = text.encode('ascii', 'ignore').decode('ascii')
            # 移除换行和多余空格
            text = text.replace('\n', ' ').replace('\r', ' ')
            text = ' '.join(text.split())
            return text.strip()
        
        clean_title = clean_header(title)
        
        # ntfy 使用 HTTP Header 传递元数据
        headers = {
            "Priority": priority,
        }
        
        # 只有清理后的标题非空才添加
        if clean_title:
            headers["Title"] = clean_title
        
        # 根据消息类型设置标签
        if "卖出" in title or "sell" in title.lower():
            headers["Tags"] = "red_circle,speaker_high_volume"
        elif "买入" in title or "buy" in title.lower():
            headers["Tags"] = "green_circle,bell"
        elif "心跳" in title or "heartbeat" in title.lower():
            headers["Tags"] = "heartbeat"
        else:
            headers["Tags"] = "chart_with_upwards_trend"
        
        api_url = f"{server.rstrip('/')}/{topic}"
        
        resp = requests.post(
            api_url, 
            data=body.encode('utf-8'), 
            headers=headers, 
            timeout=10,
            proxies={"http": None, "https": None}
        )
        
        if resp.status_code == 200:
            return True
        else:
            print(f"  [ntfy] HTTP {resp.status_code}: {resp.text[:100]}")
            return False
    except Exception as e:
        print(f"  [ntfy] 推送失败: {e}")
        return False


def notify(title: str, body: str, level: str = "signal", color: str = None):
    """
    统一推送接口 - 支持 Bark（iOS）+ ntfy（Android/跨平台）双通道
    level: 
      - "sell"=卖出信号（倒T，sos急促警报）
      - "buy"=买入信号（正T，bell清脆铃声）
      - "remind"=回买/止损提醒（alarm普通警报）
      - "signal"=通用信号（alarm，向后兼容）
      - "heartbeat"=心跳（静音）
      - "info"=日常（default）
      - "error"=错误（glass）
    color: "cyan"=翠绿色（用于价格预测的最高/最低价）
    """
    config = load_config()
    bark_urls = config.get("bark_urls", [])
    # 兼容旧配置的单 URL 字段
    bark_url_old = config.get("bark_url", "")
    if bark_url_old and bark_url_old not in bark_urls:
        bark_urls.insert(0, bark_url_old)
    wechat_url = config.get("wechat_webhook", "")
    
    # ntfy 配置
    ntfy_topic = config.get("ntfy_topic", "")
    ntfy_server = config.get("ntfy_server", "https://ntfy.sh")

    # v13.1: 不同信号类型用不同声音，便于区分
    sound = {
        "sell": "horn",       # 倒T卖出：汽车喇叭（响亮醒目）
        "buy": "bell",        # 正T买入：清脆铃声
        "remind": "alarm",    # 回买/止损提醒：普通警报
        "signal": "alarm",    # 通用信号：普通警报（向后兼容）
        "error": "glass",     # 错误：玻璃破碎声
        "heartbeat": "",      # 心跳：静音
        "info": "default",    # 日常：默认声音
    }.get(level, "default")
    
    # ntfy 优先级映射
    ntfy_priority = {
        "sell": "urgent",     # 卖出：紧急
        "buy": "high",        # 买入：高
        "remind": "high",     # 提醒：高
        "signal": "default",  # 通用：默认
        "error": "urgent",    # 错误：紧急
        "heartbeat": "low",   # 心跳：低
        "info": "default",    # 日常：默认
    }.get(level, "default")
    
    # v12.0: 颜色标记（用于价格预测推送）
    # 预期最高用红色🔴，预期最低用绿色🟢
    if color == "cyan" or color == "green" or color == "forecast":
        body = body.replace("📈 预期最高:", "🔴📈 预期最高:")
        body = body.replace("📉 预期最低:", "🟢📉 预期最低:")

    # 时间戳
    now = datetime.now().strftime("%H:%M:%S")
    body_with_time = f"⏰ {now}\n\n{body}" if level not in ("info", "heartbeat") else body

    success = False
    has_any_channel = bool(bark_urls or wechat_url or ntfy_topic)

    # Bark（iOS 主力推送渠道，支持多设备）
    if bark_urls:
        for i, bark_url in enumerate(bark_urls):
            label = f"  ✅ Bark[{i+1}]" if len(bark_urls) > 1 else "  ✅ Bark"
            fail_label = f"  ❌ Bark[{i+1}]" if len(bark_urls) > 1 else "  ❌ Bark"
            if send_bark(title, body_with_time, bark_url, sound=sound):
                print(f"{label} 推送成功")
                success = True
            else:
                print(f"{fail_label} 推送失败")

    # ntfy（Android/跨平台推送）
    if ntfy_topic:
        if send_ntfy(title, body_with_time, ntfy_topic, ntfy_server, priority=ntfy_priority):
            print(f"  ✅ ntfy 推送成功")
            success = True
        else:
            print(f"  ❌ ntfy 推送失败")

    if not has_any_channel:
        print(f"  ⚠️ 未配置任何推送渠道，请编辑 monitor_config.json")

    # 企业微信（备用）
    if wechat_url:
        if send_wechat_bot(title, body_with_time, wechat_url):
            print(f"  ✅ 企业微信推送成功")
            success = True
        else:
            print(f"  ❌ 企业微信推送失败")

    return success


# ==================== 测试 ====================
if __name__ == "__main__":
    print("推送测试...")
    print("=" * 40)

    # 测试配置
    config = load_config()
    bark_urls = config.get("bark_urls", [])
    bark_url_old = config.get("bark_url", "")
    if bark_url_old and bark_url_old not in bark_urls:
        bark_urls.insert(0, bark_url_old)
    wechat = config.get("wechat_webhook", "")
    ntfy_topic = config.get("ntfy_topic", "")
    ntfy_server = config.get("ntfy_server", "https://ntfy.sh")

    print(f"Bark 设备数: {len(bark_urls)}{' ✅' if bark_urls else ' ❌'}")
    for i, u in enumerate(bark_urls):
        print(f"  Bark[{i+1}]: ...{u[-20:]}")
    print(f"ntfy 主题: {ntfy_topic}{' ✅' if ntfy_topic else ' ❌'}")
    if ntfy_topic:
        print(f"  服务器: {ntfy_server}")
    print(f"企业微信: {'已配置 ✅' if wechat else '未配置 ❌'}")

    if bark_urls or wechat or ntfy_topic:
        print("\n发送测试消息...")
        notify(
            "🔔 测试消息",
            "如果你看到了这条消息，说明推送配置正确！\n\n这是中国平安 v10.2 倒T策略监控系统的测试推送。",
            level="signal",
        )
        print("\n测试完成，请检查手机是否收到推送。")
    else:
        print("\n请先编辑 monitor_config.json 填入推送配置：")
        print(f"  配置文件路径: {CONFIG_PATH}")
