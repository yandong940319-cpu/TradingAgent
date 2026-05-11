#!/usr/bin/env python3
"""
AI Quant Fund OS — 实时扫描器

每分钟扫描 BTC/ETH/SOL，检测交易机会，通过飞书通知。
"""

import sys, os, json, asyncio, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from layers.data.orchestrator import DataOrchestrator
from core.deepseek_client import DeepSeekClient


SYMBOLS = ["BTCUSDT", "ETHUSDT", "SOLUSDT"]
TIMEFRAME = "15m"
DATA_DIR = Path(__file__).parent / "scanner_data"


def log(msg):
    t = time.strftime("%Y-%m-%d %H:%M:%S")
    print(f"[{t}] {msg}")


async def run_scanner():
    DATA_DIR.mkdir(exist_ok=True)

    # 初始化数据层
    dc = DataOrchestrator(
        binance_key=os.getenv("BINANCE_API_KEY", ""),
        binance_secret=os.getenv("BINANCE_API_SECRET", ""),
    )

    signals_found = []

    for symbol in SYMBOLS:
        try:
            log(f"扫描 {symbol}...")

            # 采集数据
            data = await dc.collect(symbol, TIMEFRAME)
            meta = data.get("metadata", {})
            price = meta.get("close", 0)

            # 用 DeepSeek AI 分析
            klines = dc.binance.get_klines(symbol, TIMEFRAME, limit=50)
            if not klines:
                log(f"  {symbol}: 无数据")
                continue

            # 构建 K 线摘要供 AI 分析
            last_5 = klines[-5:]
            summary_lines = []
            for k in last_5:
                t = k.get("time", "")
                o = k.get("open", k.get(1, 0))
                h = k.get("high", k.get(2, 0))
                l = k.get("low", k.get(3, 0))
                c = k.get("close", k.get(4, 0))
                v = k.get("volume", k.get(5, 0))
                summary_lines.append(f"time={t} O={float(o):.2f} H={float(h):.2f} L={float(l):.2f} C={float(c):.2f} V={float(v):.0f}")
            klines_summary = "\n".join(summary_lines)
            current_price = float(last_5[-1].get("close", last_5[-1].get(4, 0)))

            # 调用 DeepSeek 分析
            ai = DeepSeekClient()
            result = await asyncio.to_thread(ai.scan_signal, symbol, klines_summary)

            signal = result.get("signal", "NO_TRADE")
            confidence = result.get("confidence", 0)
            reason = result.get("reason", "")

            log(f"  {symbol}: \${current_price:.2f} → {signal} (conf={confidence:.2f}) {reason[:40]}")

            if signal != "NO_TRADE":
                signals_found.append({
                    "symbol": symbol,
                    "signal": signal,
                    "price": current_price,
                    "confidence": confidence,
                    "reason": reason,
                    "time": time.strftime("%Y-%m-%d %H:%M:%S"),
                })

        except Exception as e:
            log(f"  {symbol}: 错误 {e}")

    # 保存扫描结果
    result = {
        "timestamp": time.strftime("%Y-%m-%d %H:%M:%S"),
        "signals": signals_found,
    }
    with open(DATA_DIR / "last_scan.json", "w") as f:
        json.dump(result, f, indent=2, ensure_ascii=False)

    # 保存结果到文件（供 Dashboard 读取）
    if signals_found:
        with open(DATA_DIR / "pending_signals.json", "w") as f:
            json.dump(signals_found, f, indent=2, ensure_ascii=False)
        log(f"✅ 检测到 {len(signals_found)} 个信号，已保存到本地")
    else:
        log("无交易信号")


if __name__ == "__main__":
    asyncio.run(run_scanner())
