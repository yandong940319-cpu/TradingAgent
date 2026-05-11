#!/usr/bin/env python3
"""
AI Quant Fund OS — 实时扫描器（多周期信号融合）

对每个标的分别扫描 15m / 30m / 1h / 4h 四个周期，
仅当四个周期信号一致（全 LONG 或全 SHORT）时才发出通知。
"""

import sys, os, json, asyncio, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from layers.data.orchestrator import DataOrchestrator
from core.deepseek_client import DeepSeekClient


SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TIMEFRAMES = ["15m", "30m", "1h", "4h"]         # 分析的周期列表
DATA_DIR = Path(__file__).parent / "scanner_data"
CACHE_DIR = DATA_DIR / "multi_tf"                # 多周期缓存目录


def log(msg):
    t = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{t}] {msg}")


def build_klines_summary(klines: list, max_rows: int = 5) -> str:
    """取最近 N 根 K 线，构建文本摘要供 AI 分析"""
    recent = klines[-max_rows:]
    lines = []
    for k in recent:
        o = float(k.get("open", k.get(1, 0)))
        h = float(k.get("high", k.get(2, 0)))
        l = float(k.get("low", k.get(3, 0)))
        c = float(k.get("close", k.get(4, 0)))
        v = float(k.get("volume", k.get(5, 0)))
        lines.append(f"O={o:.2f} H={h:.2f} L={l:.2f} C={c:.2f} V={v:.0f}")
    return "\n".join(lines)


def fuse_signals(tf_results: list) -> dict:
    """
    多周期信号融合。
    只有所有周期信号一致（全 LONG 或全 SHORT）时才通过。

    tf_results: [
        {"timeframe": "15m", "signal": "LONG", "confidence": 0.8, "reason": "..."},
        ...
    ]

    返回: {"fusion": "LONG"/"SHORT"/"NO_TRADE", "confidence": float, "details": str}
    """
    if not tf_results:
        return {"fusion": "NO_TRADE", "confidence": 0, "details": "无周期数据"}

    # 提取各周期信号
    signals = [r["signal"] for r in tf_results]
    unique = set(signals)

    # 融合逻辑
    if len(unique) == 1:
        single = unique.pop()
        if single in ("LONG", "SHORT"):
            avg_conf = sum(r.get("confidence", 0) for r in tf_results) / len(tf_results)
            min_conf = min(r.get("confidence", 0) for r in tf_results)
            details = " + ".join(
                f"{r['timeframe']}={r['signal']}({r.get('confidence',0):.0%})"
                for r in tf_results
            )
            return {
                "fusion": single,
                "confidence": round(avg_conf, 3),
                "min_confidence": round(min_conf, 3),
                "details": details,
            }

    # 信号不一致或全 NO_TRADE
    details = " | ".join(
        f"{r['timeframe']}={r['signal']}({r.get('confidence',0):.0%})"
        for r in tf_results
    )
    return {"fusion": "NO_TRADE", "confidence": 0, "details": f"不一致: {details}"}


async def scan_symbol(symbol: str, dc: DataOrchestrator, ai: DeepSeekClient) -> dict:
    """对一个标的扫描所有周期，返回融合结果"""
    tf_results = []
    current_price = 0

    for tf in TIMEFRAMES:
        try:
            # 取 50 根 K 线（近期数据够 AI 分析即可）
            klines = dc.binance.get_klines(symbol, tf, limit=50)
            if not klines:
                log(f"  {symbol} {tf}: 无数据")
                tf_results.append({
                    "timeframe": tf, "signal": "NO_TRADE",
                    "confidence": 0, "reason": "NO_DATA",
                })
                continue

            last = klines[-1]
            price = float(last.get("close", last.get(4, 0)))
            if tf == TIMEFRAMES[0]:
                current_price = price

            summary = build_klines_summary(klines)
            result = await asyncio.to_thread(ai.scan_signal, f"{symbol}({tf})", summary)

            signal = result.get("signal", "NO_TRADE")
            conf = result.get("confidence", 0)
            reason = result.get("reason", "")

            log(f"  {symbol} {tf}: ${price:.2f} → {signal} (conf={conf:.2f}) {reason[:50]}")

            tf_results.append({
                "timeframe": tf,
                "signal": signal,
                "confidence": conf,
                "price": price,
                "reason": reason,
            })

        except Exception as e:
            log(f"  {symbol} {tf}: 错误 {e}")
            tf_results.append({
                "timeframe": tf, "signal": "NO_TRADE",
                "confidence": 0, "reason": f"ERROR: {e}",
            })

    # 融合
    fusion = fuse_signals(tf_results)

    result = {
        "symbol": symbol,
        "price": current_price,
        "timeframe_results": tf_results,
        "fusion": fusion["fusion"],
        "confidence": fusion.get("confidence", 0),
        "fusion_details": fusion.get("details", ""),
        "time": time.strftime("%Y-%m-%d %H:%M:%S"),
    }

    log(f"  {symbol} 融合 → {fusion['fusion']} (conf={fusion.get('confidence',0):.2f}) [{fusion.get('details','')}]")
    return result


async def run_scanner():
    DATA_DIR.mkdir(exist_ok=True)
    CACHE_DIR.mkdir(exist_ok=True)

    dc = DataOrchestrator(
        binance_key=os.getenv("BINANCE_API_KEY", ""),
        binance_secret=os.getenv("BINANCE_API_SECRET", ""),
    )
    ai = DeepSeekClient()
    signals_found = []

    # 逐个标的扫描（避免并行调用过多导致限流）
    for symbol in SYMBOLS:
        log(f"═══ 扫描 {symbol} ═══")
        result = await scan_symbol(symbol, dc, ai)

        # 保存每个标的的多周期详情
        cache_file = CACHE_DIR / f"{symbol}.json"
        with open(cache_file, "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        # 仅记录融合信号（所有周期一致）
        if result["fusion"] in ("LONG", "SHORT"):
            signals_found.append(result)
            log(f"  ✅ {symbol} 多周期信号一致: {result['fusion']}")
        else:
            log(f"  {symbol} 周期不一致，不发出信号")

    # 保存整体扫描结果
    scan_result = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "signals": signals_found,
        "all_results": [{
            "symbol": s["symbol"],
            "fusion": s["fusion"],
            "confidence": s.get("confidence", 0),
            "fusion_details": s.get("fusion_details", ""),
            "time": s["time"],
        } for s in [
            json.load(open(CACHE_DIR / f"{sym}.json"))
            for sym in SYMBOLS
            if (CACHE_DIR / f"{sym}.json").exists()
        ]],
    }

    with open(DATA_DIR / "last_scan.json", "w") as f:
        json.dump(scan_result, f, indent=2, ensure_ascii=False)

    # 有融合信号时写 pending
    if signals_found:
        with open(DATA_DIR / "pending_signals.json", "w") as f:
            json.dump(signals_found, f, indent=2, ensure_ascii=False)
        log(f"✅ 检测到 {len(signals_found)} 个融合信号，已保存到本地")
    else:
        log("无融合信号（所有标的周期不一致）")


if __name__ == "__main__":
    asyncio.run(run_scanner())
