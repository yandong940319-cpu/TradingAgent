"""
AI Quant Fund OS — 信号追踪系统

记录每次发出的信号及后续价格变动，用于复盘分析。
"""

import csv, os, json, time
from pathlib import Path
from datetime import datetime, timedelta

SIGNAL_LOG = Path(__file__).parent / "scanner_data" / "signal_log.csv"
STATS_FILE = Path(__file__).parent / "scanner_data" / "signal_stats.json"


def log_signal(symbol: str, signal: str, price: float, confidence: float,
               fusion_details: str, source: str = "scanner"):
    """记录一次信号到 CSV"""
    SIGNAL_LOG.parent.mkdir(parents=True, exist_ok=True)

    is_new = not SIGNAL_LOG.exists()
    with open(SIGNAL_LOG, "a", newline="") as f:
        writer = csv.writer(f)
        if is_new:
            writer.writerow([
                "timestamp", "symbol", "signal", "price", "confidence",
                "fusion_details", "source",
            ])
        writer.writerow([
            datetime.now().isoformat(),
            symbol, signal, f"{price:.2f}", f"{confidence:.3f}",
            fusion_details, source,
        ])


def get_daily_signal_count() -> dict:
    """统计当日各标的的信号触发次数"""
    today = datetime.now().strftime("%Y-%m-%d")
    counts = {"LONG": 0, "SHORT": 0, "total": 0, "per_symbol": {}}

    if not SIGNAL_LOG.exists():
        return counts

    with open(SIGNAL_LOG, "r") as f:
        reader = csv.DictReader(f)
        for row in reader:
            if row.get("timestamp", "").startswith(today):
                sym = row.get("symbol", "?")
                sig = row.get("signal", "NO_TRADE")
                counts["total"] += 1
                counts[sig] = counts.get(sig, 0) + 1
                counts["per_symbol"][sym] = counts["per_symbol"].get(sym, 0) + 1

    return counts


def save_stats():
    """保存当日统计到 JSON"""
    stats = get_daily_signal_count()
    stats["date"] = datetime.now().strftime("%Y-%m-%d")
    stats["timestamp"] = datetime.now().isoformat()
    STATS_FILE.parent.mkdir(parents=True, exist_ok=True)
    with open(STATS_FILE, "w") as f:
        json.dump(stats, f, indent=2, ensure_ascii=False)
    return stats


def get_recent_signals(limit: int = 20) -> list[dict]:
    """获取最近的 N 条信号记录"""
    if not SIGNAL_LOG.exists():
        return []

    with open(SIGNAL_LOG, "r") as f:
        reader = csv.DictReader(f)
        rows = list(reader)

    return rows[-limit:]


def generate_review_report() -> dict:
    """
    生成复盘报告。
    统计当日信号触发情况，供 review_agent 使用。
    """
    today = datetime.now().strftime("%Y-%m-%d")
    weekly = (datetime.now() - timedelta(days=7)).strftime("%Y-%m-%d")

    signals_today = 0
    signals_week = 0
    symbol_breakdown = {}

    if SIGNAL_LOG.exists():
        with open(SIGNAL_LOG, "r") as f:
            reader = csv.DictReader(f)
            for row in reader:
                ts = row.get("timestamp", "")
                if ts.startswith(today):
                    signals_today += 1
                    sym = row.get("symbol", "?")
                    symbol_breakdown[sym] = symbol_breakdown.get(sym, 0) + 1
                if ts >= weekly:
                    signals_week += 1

    return {
        "date": today,
        "signals_today": signals_today,
        "signals_week": signals_week,
        "avg_daily": round(signals_week / 7, 1) if signals_week > 0 else 0,
        "symbol_breakdown": symbol_breakdown,
    }
