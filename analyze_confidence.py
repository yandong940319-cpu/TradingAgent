#!/usr/bin/env python3
"""
信心分布分析 — 回测各信号的信度分布
"""

import sys, os, json, asyncio
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from layers.data.orchestrator import DataOrchestrator
from core.deepseek_client import DeepSeekClient


async def analyze_confidence(symbol: str = "BTCUSDT", days: int = 365):
    """分析指定标的历史信号信心分布"""
    dc = DataOrchestrator(
        binance_key=os.getenv("BINANCE_API_KEY", ""),
        binance_secret=os.getenv("BINANCE_API_SECRET", ""),
    )
    ai = DeepSeekClient()

    print(f"📊 DeepSeek AI 信心分布分析: {symbol} 过去 {days} 天")
    print("=" * 60)

    klines = dc.binance.get_klines(symbol, "1d", limit=days)
    if not klines:
        print("❌ 无法获取历史数据")
        return

    print(f"📈 共 {len(klines)} 根日线")

    # 分批分析，每批 30 天
    batch_size = 30
    records = []
    for start in range(0, len(klines), batch_size):
        batch = klines[start:start + batch_size]
        summary_lines = []
        for k in batch:
            t = k.get("time", "")
            o = float(k.get("open", k.get(1, 0)))
            h = float(k.get("high", k.get(2, 0)))
            l = float(k.get("low", k.get(3, 0)))
            c = float(k.get("close", k.get(4, 0)))
            v = float(k.get("volume", k.get(5, 0)))
            summary_lines.append(f"D={str(t)[:10]} O={o:.0f} H={h:.0f} L={l:.0f} C={c:.0f} V={v:.0f}")

        summary = "\n".join(summary_lines)
        result = await asyncio.to_thread(ai.scan_signal, symbol, summary)

        for k in batch:
            t = str(k.get("time", ""))[:10]
            c = float(k.get("close", k.get(4, 0)))
            records.append({
                "time": t,
                "close": c,
                "signal": result.get("signal", "NO_TRADE"),
                "confidence": result.get("confidence", 0),
            })

        print(f"  batch {start//batch_size + 1}/{(len(klines)-1)//batch_size + 1}: {result.get('signal','?')} ({result.get('confidence',0):.2f})")
        await asyncio.sleep(0.5)  # 限流

    # 统计
    signals_only = [r for r in records if r["signal"] != "NO_TRADE"]

    # 统计分布
    signals_only = [r for r in records if r["signal"] != "NO_TRADE"]
    total_signals = len(signals_only)
    total_days = len(records)
    no_trade_days = total_days - total_signals

    print(f"\n📊 总天数: {total_days}")
    print(f"📊 有信号天数: {total_signals} ({total_signals/total_days*100:.1f}%)")
    print(f"📊 无信号天数: {no_trade_days} ({no_trade_days/total_days*100:.1f}%)")

    # 信心区间分布
    bins = [(0, 0.15, "0~0.15"), (0.15, 0.3, "0.15~0.3"),
            (0.3, 0.45, "0.3~0.45"), (0.45, 0.6, "0.45~0.6"),
            (0.6, 1.0, "0.6~1.0")]
    
    print(f"\n📊 信心分布（仅包含信号日）:")
    for lo, hi, label in bins:
        count = sum(1 for r in signals_only if lo <= r["confidence"] < hi)
        pct = count / total_signals * 100 if total_signals > 0 else 0
        bar = "█" * int(pct / 2)
        print(f"  {label}: {count:4d} 次 ({pct:5.1f}%) {bar}")

    # 信号方向分布
    longs = sum(1 for r in signals_only if r["signal"] == "LONG")
    shorts = sum(1 for r in signals_only if r["signal"] == "SHORT")
    print(f"\n📊 信号方向:")
    print(f"  🟢 LONG:  {longs} ({longs/total_signals*100:.1f}%)" if total_signals > 0 else "")
    print(f"  🔴 SHORT: {shorts} ({shorts/total_signals*100:.1f}%)" if total_signals > 0 else "")

    # 平均信心与中位
    avg_conf = sum(r["confidence"] for r in signals_only) / total_signals if total_signals > 0 else 0
    confs = sorted([r["confidence"] for r in signals_only]) if signals_only else [0]
    median_conf = confs[len(confs)//2]
    print(f"\n📊 平均信心: {avg_conf:.3f}")
    print(f"📊 中位信心: {median_conf:.3f}")

    # 保存结果
    result = {
        "symbol": symbol,
        "days": total_days,
        "total_signals": total_signals,
        "signal_rate_pct": round(total_signals/total_days*100, 1),
        "long_pct": round(longs/total_signals*100, 1) if total_signals > 0 else 0,
        "short_pct": round(shorts/total_signals*100, 1) if total_signals > 0 else 0,
        "avg_confidence": round(avg_conf, 3),
        "distribution": []
    }
    for lo, hi, label in bins:
        count = sum(1 for r in signals_only if lo <= r["confidence"] < hi)
        result["distribution"].append({
            "range": label,
            "count": count,
            "pct": round(count/total_signals*100, 1) if total_signals > 0 else 0,
        })

    # 写文件供 dashboard 读取
    output_dir = Path(__file__).parent / "scanner_data"
    output_dir.mkdir(exist_ok=True)
    with open(output_dir / "confidence_analysis.json", "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)
    print(f"\n✅ 结果已保存")

    return result


if __name__ == "__main__":
    asyncio.run(analyze_confidence("BTCUSDT", 365))
