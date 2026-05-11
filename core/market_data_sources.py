"""
AI Quant Fund OS — 免费市场数据源采集层

使用完全免费的第三方数据源，无需 API Key：
- Fear & Greed Index (alternative.me)
- CoinTelegraph RSS / CoinDesk RSS / Bitcoin Magazine RSS
"""

import json, time
from datetime import datetime
from typing import Optional
import requests
import feedparser


# ────────────────────────────────────────────
# Fear & Greed Index
# ────────────────────────────────────────────

FEAR_GREED_URL = "https://api.alternative.me/fng/?limit=1"


def fetch_fear_greed() -> dict:
    """
    获取 Fear & Greed Index。
    返回: {"value": int 0-100, "classification": str, "timestamp": str}
    失败时返回 {"value": 50, "classification": "Neutral", "error": "..."}
    """
    try:
        r = requests.get(FEAR_GREED_URL, timeout=15)
        data = r.json()
        item = data["data"][0]
        return {
            "value": int(item["value"]),
            "classification": item["value_classification"],
            "timestamp": item.get("timestamp", datetime.now().isoformat()),
        }
    except Exception as e:
        return {"value": 50, "classification": "Neutral", "error": str(e)}


# ────────────────────────────────────────────
# RSS 新闻摘要
# ────────────────────────────────────────────

RSS_FEEDS = [
    ("CoinTelegraph", "https://cointelegraph.com/rss"),
    ("CoinDesk", "https://www.coindesk.com/arc/outboundfeeds/rss/"),
    ("Bitcoin Magazine", "https://bitcoinmagazine.com/.rss/full/"),
]

MAX_ARTICLES_PER_FEED = 5


def fetch_news_headlines() -> list[dict]:
    """
    从多个 RSS 源获取最新加密新闻标题。
    返回: [{"source": str, "title": str, "published": str, "link": str}, ...]
    """
    articles = []
    for source_name, url in RSS_FEEDS:
        try:
            feed = feedparser.parse(url)
            for entry in feed.entries[:MAX_ARTICLES_PER_FEED]:
                articles.append({
                    "source": source_name,
                    "title": entry.get("title", ""),
                    "published": entry.get("published", "")[:16],
                    "link": entry.get("link", ""),
                })
        except Exception:
            pass  # 单个源失败不影响整体
    return articles


# ────────────────────────────────────────────
# 综合市场情绪
# ────────────────────────────────────────────


def collect_market_sentiment(target_symbol: str = "") -> dict:
    """
    采集所有免费数据源，输出综合市场情绪。

    返回结构:
    {
        "fear_greed": {...},
        "news_headlines": [...],
        "sentiment_score": -1.0 ~ 1.0,   # -1=极度恐惧, 1=极度贪婪
        "confidence": 0.0 ~ 1.0,          # 数据可信度
        "timestamp": "...",
    }
    """
    fng = fetch_fear_greed()
    headlines = fetch_news_headlines()

    # Fear & Greed → 映射为 -1 ~ 1 分数
    fng_value = fng.get("value", 50)
    sentiment_score = (fng_value - 50) / 50.0  # 0→-1, 100→1

    # 数据源数量决定可信度
    active_sources = 1  # Fear & Greed 总是可用
    if headlines:
        active_sources += 1

    confidence = min(active_sources / 3.0, 0.9)

    return {
        "fear_greed": fng,
        "news_headlines": headlines,
        "sentiment_score": round(sentiment_score, 3),
        "news_count": len(headlines),
        "confidence": round(confidence, 2),
        "timestamp": datetime.now().isoformat(),
    }
