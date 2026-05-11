"""
Layer 2 — Review Agent (复盘 Agent)

读取 signal_log.csv，对发出超过 4 小时的信号，
用 Binance 公开 API 结算盈亏，输出复盘报告。
"""

import csv, json, math, os
from pathlib import Path
from datetime import datetime, timedelta, timezone
from typing import Optional

import requests
import pandas as pd
import numpy as np

# ── 路径 ──

PROJECT_ROOT = Path(__file__).resolve().parent.parent.parent
SIGNAL_LOG = PROJECT_ROOT / "scanner_data" / "signal_log.csv"
REVIEW_JSON = PROJECT_ROOT / "scanner_data" / "review_report.json"
REVIEW_TXT  = PROJECT_ROOT / "scanner_data" / "review_summary.txt"

REVIEW_HOURS = 4        # 信号发出后 N 小时才结算
MIN_SIGNALS  = 3        # 最少 N 条信号才出统计

# ── 辅助函数 ──


def _fetch_current_price(symbol: str) -> Optional[float]:
    """用 Binance 公开 API 拉取当前价格（不需要 Key）"""
    try:
        r = requests.get(
            f"https://api.binance.com/api/v3/ticker/price?symbol={symbol.upper()}",
            timeout=10,
        )
        if r.status_code == 200:
            return float(r.json()["price"])
    except Exception:
        pass
    return None


def _calc_pnl(entry_price: float, current_price: float, direction: str) -> float:
    """计算盈亏百分比"""
    if direction.upper() == "LONG":
        return (current_price - entry_price) / entry_price
    elif direction.upper() == "SHORT":
        return (entry_price - current_price) / entry_price
    return 0.0


# ── 核心逻辑 ──


def run_review() -> dict:
    """
    主入口：读取信号日志 → 结算 → 统计 → 输出文件。
    返回完整的 review report dict。
    """
    if not SIGNAL_LOG.exists():
        _write_outputs({"error": "signal_log.csv 不存在", "signals_reviewed": 0})
        return {"error": "signal_log.csv 不存在"}

    # 1. 读取信号日志
    df = pd.read_csv(SIGNAL_LOG)
    if df.empty:
        _write_outputs({"error": "信号日志为空", "signals_reviewed": 0})
        return {"error": "信号日志为空"}

    # 2. 补充标准列名（兼容不同写入方）
    #    期望: timestamp, symbol, signal, price, confidence, fusion_details, source
    for col in ["timestamp", "symbol", "signal", "price", "confidence"]:
        if col not in df.columns:
            _write_outputs({"error": f"缺少列: {col}", "signals_reviewed": 0})
            return {"error": f"缺少列: {col}"}

    now = datetime.now(timezone.utc)
    cutoff = now - timedelta(hours=REVIEW_HOURS)

    # 3. 筛选 ≥ 4h 的信号
    df["ts_dt"] = pd.to_datetime(df["timestamp"], utc=True, errors="coerce")
    df_old = df[df["ts_dt"] <= cutoff].copy()

    if df_old.empty:
        _write_outputs({
            "signals_reviewed": 0,
            "message": f"没有超过 {REVIEW_HOURS}h 的信号等待结算",
        })
        return {"signals_reviewed": 0, "message": "无待结算信号"}

    # 4. 对每条信号拉取当前价格并计算盈亏
    symbols_needed = df_old["symbol"].unique()
    prices = {}
    for sym in symbols_needed:
        p = _fetch_current_price(sym)
        if p is not None:
            prices[sym] = p

    if not prices:
        _write_outputs({"error": "无法获取任何标的当前价格", "signals_reviewed": 0})
        return {"error": "价格获取失败"}

    results = []
    for _, row in df_old.iterrows():
        sym = row["symbol"]
        if sym not in prices:
            continue
        entry_price = float(row["price"])
        current_price = prices[sym]
        direction = str(row["signal"]).strip().upper()
        pnl = _calc_pnl(entry_price, current_price, direction)
        outcome = "WIN" if pnl > 0 else "LOSS"

        results.append({
            "timestamp": str(row["timestamp"]),
            "symbol": sym,
            "signal": direction,
            "entry_price": round(entry_price, 2),
            "current_price": round(current_price, 2),
            "pnl_pct": round(pnl, 4),
            "outcome": outcome,
        })

    if not results:
        _write_outputs({"error": "结算结果为空", "signals_reviewed": 0})
        return {"error": "结算结果为空"}

    # 5. 聚合统计
    df_res = pd.DataFrame(results)

    # --- 总体统计 ---
    total = len(df_res)
    wins = len(df_res[df_res["outcome"] == "WIN"])
    losses = len(df_res[df_res["outcome"] == "LOSS"])
    win_rate = wins / total if total > 0 else 0.0

    returns = df_res["pnl_pct"].values
    mean_return = float(np.mean(returns))
    std_return = float(np.std(returns, ddof=1)) if len(returns) > 1 else 0.0

    # Sharpe (简化: 用信号收益率 / 收益率标准差)
    sharpe = (mean_return / std_return) if std_return > 0 else 0.0

    # Sortino (只考虑负收益)
    neg_returns = returns[returns < 0]
    downside_std = float(np.std(neg_returns, ddof=1)) if len(neg_returns) > 1 else 0.0
    sortino = (mean_return / downside_std) if downside_std > 0 else (sharpe if std_return > 0 else 0.0)

    # 最大回撤
    cum_returns = np.cumprod(1 + returns)
    peak = np.maximum.accumulate(cum_returns)
    drawdown = (cum_returns - peak) / peak
    max_drawdown = float(np.min(drawdown)) if len(drawdown) > 0 else 0.0

    # --- 按 symbol 分组 ---
    by_symbol = {}
    for sym in sorted(df_res["symbol"].unique()):
        sub = df_res[df_res["symbol"] == sym]
        n = len(sub)
        w = len(sub[sub["outcome"] == "WIN"])
        wr = w / n if n > 0 else 0.0
        avg_pnl = float(sub["pnl_pct"].mean())
        by_symbol[sym] = {
            "signals": n,
            "wins": w,
            "losses": n - w,
            "win_rate": round(wr, 4),
            "avg_pnl_pct": round(avg_pnl, 4),
        }

    # --- 按 signal 方向分组 ---
    by_signal = {}
    for sig in sorted(df_res["signal"].unique()):
        sub = df_res[df_res["signal"] == sig]
        n = len(sub)
        w = len(sub[sub["outcome"] == "WIN"])
        wr = w / n if n > 0 else 0.0
        avg_pnl = float(sub["pnl_pct"].mean())
        by_signal[sig] = {
            "signals": n,
            "wins": w,
            "losses": n - w,
            "win_rate": round(wr, 4),
            "avg_pnl_pct": round(avg_pnl, 4),
        }

    # 6. 因子状态判定
    enough_data = total >= MIN_SIGNALS
    if enough_data and win_rate >= 0.55 and sharpe >= 0.5:
        factor_status = "VALID"
    elif enough_data and (win_rate >= 0.45 or sharpe >= 0.2):
        factor_status = "MARGINAL"
    else:
        factor_status = "INVALID"

    # 7. 构建报告
    report = {
        "review_time": datetime.now().isoformat(),
        "review_hours": REVIEW_HOURS,
        "signals_reviewed": total,
        "min_signals_required": MIN_SIGNALS,
        "summary": {
            "total_signals": total,
            "wins": int(wins),
            "losses": int(losses),
            "win_rate": round(win_rate, 4),
            "avg_pnl_pct": round(mean_return, 4),
            "sharpe": round(sharpe, 4),
            "sortino": round(sortino, 4),
            "max_drawdown": round(max_drawdown, 4),
            "factor_status": factor_status,
        },
        "by_symbol": by_symbol,
        "by_signal": by_signal,
        "recent_results": results[-20:],
    }

    _write_outputs(report)
    return report


def _write_outputs(report: dict):
    """写入 review_report.json 和 review_summary.txt"""
    REVIEW_JSON.parent.mkdir(parents=True, exist_ok=True)

    # JSON
    with open(REVIEW_JSON, "w") as f:
        json.dump(report, f, indent=2, ensure_ascii=False)

    # TXT 摘要
    s = report.get("summary", {})
    lines = [
        "=" * 50,
        f"  复盘报告  |  {datetime.now().strftime('%Y-%m-%d %H:%M')}",
        "=" * 50,
        f"  信号数:       {s.get('total_signals', 0)}",
        f"  胜率:         {s.get('win_rate', 0)*100:.1f}%",
        f"  平均盈亏:     {s.get('avg_pnl_pct', 0)*100:+.2f}%",
        f"  Sharpe:       {s.get('sharpe', 0):.2f}",
        f"  Sortino:      {s.get('sortino', 0):.2f}",
        f"  最大回撤:     {s.get('max_drawdown', 0)*100:.1f}%",
        f"  因子状态:     {s.get('factor_status', '?')}",
        "=" * 50,
        "  按标的:",
    ]

    for sym, d in report.get("by_symbol", {}).items():
        lines.append(f"    {sym:12s}  {d['signals']}笔 胜率{d['win_rate']*100:.0f}% 均盈亏{d['avg_pnl_pct']*100:+.1f}%")

    lines.append("=" * 50)

    with open(REVIEW_TXT, "w") as f:
        f.write("\n".join(lines) + "\n")

    print("\n".join(lines))


if __name__ == "__main__":
    run_review()
