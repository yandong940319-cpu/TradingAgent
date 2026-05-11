"""
复盘 Agent — 读取回测 CSV，输出胜率 / Sharpe / 因子状态
"""
import json
import statistics
from pathlib import Path

import pandas as pd

ROOT       = Path(__file__).parent.parent.parent
TRADES_CSV = ROOT / "scanner_data" / "backtest_trades.csv"
REPORT_OUT = ROOT / "scanner_data" / "review_report.json"
SUMMARY_OUT= ROOT / "scanner_data" / "review_summary.txt"


def calc_stats(df: pd.DataFrame) -> dict:
    if df.empty:
        return {}
    pnls     = df["pnl_pct"].tolist()
    wins     = df[df["outcome"] == "WIN"]
    win_rate = round(len(wins) / len(df), 3)
    avg_pnl  = round(statistics.mean(pnls), 3)
    std_pnl  = statistics.stdev(pnls) if len(pnls) > 1 else 1
    sharpe   = round(avg_pnl / std_pnl, 3)
    downside = [p for p in pnls if p < 0]
    std_down = statistics.stdev(downside) if len(downside) > 1 else 1
    sortino  = round(avg_pnl / std_down, 3)

    # 最大回撤
    equity = 10000.0
    peak   = equity
    max_dd = 0.0
    for p in pnls:
        equity *= (1 + p / 100)
        peak    = max(peak, equity)
        dd      = (peak - equity) / peak * 100
        max_dd  = max(max_dd, dd)

    return {
        "total":        len(df),
        "wins":         len(wins),
        "losses":       len(df) - len(wins),
        "win_rate":     win_rate,
        "avg_pnl":      avg_pnl,
        "sharpe":       sharpe,
        "sortino":      sortino,
        "max_drawdown": round(max_dd, 2),
        "best_trade":   round(max(pnls), 3),
        "worst_trade":  round(min(pnls), 3),
    }


def factor_verdict(overall: dict) -> str:
    wr = overall.get("win_rate", 0)
    sh = overall.get("sharpe", 0)
    if wr >= 0.55 and sh >= 0.5:
        return "VALID"
    elif wr >= 0.45:
        return "MARGINAL"
    return "INVALID"


def run_review():
    if not TRADES_CSV.exists():
        print("[ReviewAgent] backtest_trades.csv 不存在，请先跑回测")
        return

    df = pd.read_csv(TRADES_CSV)
    if df.empty:
        print("[ReviewAgent] 无交易记录")
        return

    overall  = calc_stats(df)
    by_sym   = {s: calc_stats(g) for s, g in df.groupby("symbol")}
    by_dir   = {s: calc_stats(g) for s, g in df.groupby("signal")}
    verdict  = factor_verdict(overall)

    report = {
        "generated_at": pd.Timestamp.now().isoformat(),
        "factor_status": verdict,
        "overall":      overall,
        "by_symbol":    by_sym,
        "by_direction": by_dir,
    }

    REPORT_OUT.write_text(json.dumps(report, indent=2, ensure_ascii=False))

    # 人类可读摘要
    lines = [
        "=" * 45,
        f"  复盘报告  因子状态: {verdict}",
        "=" * 45,
        f"总交易: {overall['total']} 笔",
        f"胜率:   {overall['win_rate']*100:.1f}%  "
        f"({overall['wins']}W / {overall['losses']}L)",
        f"均盈亏: {overall['avg_pnl']:+.2f}%",
        f"Sharpe: {overall['sharpe']}  Sortino: {overall['sortino']}",
        f"最大回撤: {overall['max_drawdown']}%",
        f"最佳: {overall['best_trade']:+.2f}%  "
        f"最差: {overall['worst_trade']:+.2f}%",
        "-" * 45,
    ]
    for sym, s in by_sym.items():
        lines.append(f"{sym}: 胜率 {s['win_rate']*100:.0f}%  "
                     f"Sharpe {s['sharpe']}  trades {s['total']}")
    lines.append("=" * 45)
    summary = "\n".join(lines)

    SUMMARY_OUT.write_text(summary, encoding="utf-8")
    print(summary)
    print(f"\n[ReviewAgent] 报告已写入 {REPORT_OUT}")


if __name__ == "__main__":
    run_review()
