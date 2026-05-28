#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""
RSS智能筛选器 - 每日从Miniflux拉取新文章，关键词筛选，保存Markdown
不用Bark推送，避免与盯盘信号重叠
"""

import os
import sys
import json
import re
from datetime import datetime, timedelta
from pathlib import Path

import requests

# ==================== 配置 ====================

MINIFLUX_BASE = "http://127.0.0.1:8080/v1"
MINIFLUX_USER = "feihong"
MINIFLUX_PASS = "Rss2026Pa!"

# 保存目录
OUTPUT_DIR = "/opt/rss-hub/articles"
LOG_FILE = "/opt/rss-hub/rss_filter.log"

# 筛选关键词（命中任一即保存）
KEYWORDS = {
    "AI工具与趋势": [
        "AI", "GPT", "Claude", "LLM", "大模型", "人工智能", "机器学习",
        "深度学习", "OpenAI", "Gemini", "Copilot", "Agent", "智能体",
        "提示词", "Prompt", "RAG", "微调", "Fine-tune", "多模态",
        "AI搜索", "AI编程", "AI写作", "AI绘画", "Cursor", "Windsurf",
        "WorkBuddy", "Claude Code", "Sora", "Midjourney",
    ],
    "投资与量化": [
        "中国平安", "保险股", "做T", "量化", "T+0", "日内交易",
        "A股", "沪深300", "北向资金", "降息", "LPR", "利率",
        "估值", "PE", "PB", "ROE", "股息率", "保险业",
        "金融股", "银行股", "券商", "可转债",
    ],
    "管理与认知": [
        "管理", "领导力", "决策", "沟通", "团队", "组织",
        "认知", "思维模型", "复盘", "方法论", "效率",
        "时间管理", "目标管理", "OKR", "KPI",
        "董事长", "CEO", "高管", "助理",
    ],
    "心理学": [
        "心理学", "心理", "焦虑", "压力", "情绪", "动机",
        "认知偏差", "行为经济学", "交易心理", "自律",
        "阿德勒", "荣格", "弗洛伊德", "心流", "正念",
        "自我价值", "内在动机", "习得性无助",
    ],
    "科技与商业": [
        "零售", "手机", "华为", "苹果", "OPPO", "vivo",
        "通信", "运营商", "电商", "消费电子",
        "创业", "商业模式", "数字化转型", "新零售",
    ],
}

# ==================== 工具函数 ====================

def log(msg):
    """写日志"""
    ts = datetime.now().strftime("%Y-%m-%d %H:%M:%S")
    line = "[%s] %s" % (ts, msg)
    print(line)
    with open(LOG_FILE, "a", encoding="utf-8") as f:
        f.write(line + "\n")


def match_keywords(title, summary, category_name):
    """检查标题和摘要是否命中关键词"""
    text = (title + " " + summary).lower()
    keywords = KEYWORDS.get(category_name, [])
    matched = []
    for kw in keywords:
        if kw.lower() in text:
            matched.append(kw)
    return matched


def sanitize_filename(name):
    """清理文件名"""
    name = re.sub(r'[\\/:*?"<>|]', '_', name)
    name = name.strip()[:80]
    return name


def fetch_entries(hours=24):
    """从Miniflux获取最近N小时的条目"""
    auth = (MINIFLUX_USER, MINIFLUX_PASS)
    since = datetime.now() - timedelta(hours=hours)
    # Miniflux API: 获取最近条目
    entries = []
    offset = 0
    limit = 100

    while True:
        r = requests.get(
            MINIFLUX_BASE + "/entries",
            auth=auth,
            params={
                "order": "published_at",
                "direction": "desc",
                "limit": limit,
                "offset": offset,
                "status": "unread",
            }
        )
        if r.status_code != 200:
            log("API错误: %d %s" % (r.status_code, r.text[:100]))
            break

        data = r.json()
        batch = data.get("entries", [])
        if not batch:
            break

        for entry in batch:
            pub_time = entry.get("published_at", "")
            if pub_time:
                try:
                    pub_dt = datetime.fromisoformat(pub_time.replace("Z", "+00:00"))
                    if pub_dt.replace(tzinfo=None) < since:
                        return entries
                except:
                    pass
            entries.append(entry)

        if len(batch) < limit:
            break
        offset += limit

    return entries


def save_article(entry, matched_keywords, category_name):
    """保存文章为Markdown"""
    title = entry.get("title", "无标题")
    url = entry.get("url", "")
    feed_title = entry.get("feed", {}).get("title", "未知来源")
    pub_time = entry.get("published_at", "")[:19].replace("T", " ")
    content = entry.get("content", "") or entry.get("description", "")

    # 清理HTML标签
    content = re.sub(r'<[^>]+>', '', content)
    content = content.strip()

    # 截断过长内容
    if len(content) > 5000:
        content = content[:5000] + "\n\n... (内容过长已截断)"

    today = datetime.now().strftime("%Y-%m-%d")
    output_path = Path(OUTPUT_DIR) / today
    output_path.mkdir(parents=True, exist_ok=True)

    filename = sanitize_filename(title) + ".md"
    filepath = output_path / filename

    # 如果文件已存在，跳过
    if filepath.exists():
        return False

    md = """# {title}

> 📰 {feed_title} | 🕐 {pub_time}
> 🔗 [原文链接]({url})
> 🏷️ {category} | 关键词: {keywords}

---

{content}
""".format(
        title=title,
        feed_title=feed_title,
        pub_time=pub_time,
        url=url,
        category=category_name,
        keywords=", ".join(matched_keywords),
        content=content
    )

    with open(filepath, "w", encoding="utf-8") as f:
        f.write(md)

    return True


# ==================== 主流程 ====================

def main():
    log("=" * 50)
    log("RSS智能筛选器启动")

    # 获取条目
    entries = fetch_entries(hours=24)
    log("获取到 %d 条未读文章" % len(entries))

    # 获取分类映射
    auth = (MINIFLUX_USER, MINIFLUX_PASS)
    r = requests.get(MINIFLUX_BASE + "/categories", auth=auth)
    cat_map = {c["id"]: c["title"] for c in r.json()}

    # 获取feed-分类映射
    r = requests.get(MINIFLUX_BASE + "/feeds", auth=auth)
    feed_cat = {}
    for f in r.json():
        feed_cat[f["id"]] = f.get("category", {}).get("id", 1)

    # 筛选并保存
    total_matched = 0
    total_saved = 0

    for entry in entries:
        feed_id = entry.get("feed", {}).get("id", 0)
        cat_id = feed_cat.get(feed_id, 1)
        cat_name = cat_map.get(cat_id, "未分类")

        title = entry.get("title", "")
        summary = entry.get("description", "")[:500]

        matched = match_keywords(title, summary, cat_name)
        if matched:
            total_matched += 1
            saved = save_article(entry, matched, cat_name)
            if saved:
                total_saved += 1
                log("✅ 保存: [%s] %s (命中: %s)" % (cat_name, title[:40], ",".join(matched[:3])))

    log("筛选完成: 总%d条 / 命中%d条 / 新保存%d条" % (len(entries), total_matched, total_saved))

    # 写一份今天的摘要
    today = datetime.now().strftime("%Y-%m-%d")
    summary_path = Path(OUTPUT_DIR) / today / "_daily_summary.md"
    if total_saved > 0:
        with open(summary_path, "w", encoding="utf-8") as f:
            f.write("# 📰 每日RSS精选 - %s\n\n" % today)
            f.write("- 总扫描: %d篇\n" % len(entries))
            f.write("- 命中筛选: %d篇\n" % total_matched)
            f.write("- 新保存: %d篇\n\n" % total_saved)
            f.write("---\n\n*由肥洪RSS智能筛选器自动生成*\n")

    # 标记已读（避免重复处理）
    entry_ids = [e["id"] for e in entries if e["id"]]
    if entry_ids:
        requests.put(
            MINIFLUX_BASE + "/entries",
            auth=auth,
            json={"entry_ids": entry_ids, "status": "read"}
        )
        log("已标记 %d 条为已读" % len(entry_ids))


if __name__ == "__main__":
    main()
