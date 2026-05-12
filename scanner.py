#!/usr/bin/env python3
"""
AI Quant Fund OS — 实时扫描器（多周期信号融合）

对每个标的分别扫描 15m / 30m / 1h / 2h / 4h / 6h / 8h / 12h 八个周期，
仅当至少三个周期信号一致（同为 LONG 或同为 SHORT）时才发出通知。
"""

import sys, os, json, asyncio, time
from pathlib import Path
sys.path.insert(0, str(Path(__file__).parent))

from layers.data.orchestrator import DataOrchestrator
from core.signal_tracker import log_signal, save_stats
from layers.intelligence.multi_tf_signal import compute_signal, klines_to_df, resample_to_3day
from core.feishu_notify import send_dm


SYMBOLS = ["BTCUSDT", "SOLUSDT"]
TIMEFRAMES = ["15m", "30m", "1h", "2h", "4h", "6h", "8h", "12h"]
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
    至少三个周期信号一致（同为 LONG 或同为 SHORT）时才通过。

    tf_results: [
        {"timeframe": "15m", "signal": "LONG", "confidence": 0.8, "reason": "..."},
        ...
    ]

    返回: {"fusion": "LONG"/"SHORT"/"NO_TRADE", "confidence": float, "details": str}
    """
    if not tf_results:
        return {"fusion": "NO_TRADE", "confidence": 0, "details": "无周期数据"}

    MIN_AGREE = 3  # 至少三个周期一致才发信号

    # 统计 LONG / SHORT / NO_TRADE 数量
    long_count = sum(1 for r in tf_results if r["signal"] == "LONG")
    short_count = sum(1 for r in tf_results if r["signal"] == "SHORT")

    details = " | ".join(
        f"{r['timeframe']}={r['signal']}({r.get('confidence',0):.0%})"
        for r in tf_results
    )

    if long_count >= MIN_AGREE and short_count >= MIN_AGREE:
        # 两边都超过阈值——矛盾信号，不发
        return {"fusion": "NO_TRADE", "confidence": 0, "details": f"矛盾: {details}"}

    if long_count >= MIN_AGREE:
        matched = [r for r in tf_results if r["signal"] == "LONG"]
        avg_conf = sum(r.get("confidence", 0) for r in matched) / len(matched)
        return {
            "fusion": "LONG",
            "confidence": round(avg_conf, 3),
            "details": f"LONG={long_count}/{len(tf_results)} | {details}",
        }

    if short_count >= MIN_AGREE:
        matched = [r for r in tf_results if r["signal"] == "SHORT"]
        avg_conf = sum(r.get("confidence", 0) for r in matched) / len(matched)
        return {
            "fusion": "SHORT",
            "confidence": round(avg_conf, 3),
            "details": f"SHORT={short_count}/{len(tf_results)} | {details}",
        }

    # 不足 3 个周期一致
    return {"fusion": "NO_TRADE", "confidence": 0, "details": f"不足{MIN_AGREE}: {details}"}


async def scan_symbol(symbol: str, dc: DataOrchestrator) -> dict:
    """多时间框架技术指标扫描"""
    current_price = 0
    try:
        # 取 15m K 线获取当前价格
        klines = dc.binance.get_klines(symbol, "15m", limit=5)
        if klines:
            last = klines[-1]
            current_price = float(last.get("close", last.get(4, 0)))

        # 用多时间框架指标计算信号
        mtf_result = await get_mtf_signal(dc, symbol)
        signal = mtf_result.signal
        conf = mtf_result.confidence
        reason = mtf_result.reason

        log(f"  {symbol}: ${current_price:.2f} → {signal} (conf={conf:.2f}) [{reason[:80]}]")

        # 构建与原有融合格式兼容的结果
        result = {
            "symbol": symbol,
            "price": current_price,
            "fusion": signal,
            "confidence": conf,
            "fusion_details": reason,
            "timeframe_results": [{"timeframe": "mtf", "signal": signal, "confidence": conf, "reason": reason}],
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

    except Exception as e:
        log(f"  {symbol}: 错误 {e}")
        result = {
            "symbol": symbol,
            "price": current_price,
            "fusion": "NO_TRADE",
            "confidence": 0,
            "fusion_details": f"ERROR: {e}",
            "timeframe_results": [],
            "time": time.strftime("%Y-%m-%d %H:%M:%S"),
        }

    return result


async def get_mtf_signal(dc, symbol):
    """拉取多时间框架数据，计算信号"""
    timeframes = {
        "weekly": "1w",
        "daily":  "1d",
        "h4":     "4h",
        "h1":     "1h",
        "m15":    "15m",
    }
    klines_map = {}
    for name, tf in timeframes.items():
        raw = dc.binance.get_klines(symbol, tf, limit=100)
        klines_map[name] = klines_to_df(raw)

    df_3day = resample_to_3day(klines_map["daily"])

    result = compute_signal(
        df_weekly=klines_map["weekly"],
        df_3day=df_3day,
        df_daily=klines_map["daily"],
        df_4h=klines_map["h4"],
        df_1h=klines_map["h1"],
        df_15m=klines_map["m15"],
    )
    return result


async def run_scanner():
    DATA_DIR.mkdir(exist_ok=True)
    CACHE_DIR.mkdir(exist_ok=True)

    dc = DataOrchestrator(
        binance_key=os.getenv("BINANCE_API_KEY", ""),
        binance_secret=os.getenv("BINANCE_API_SECRET", ""),
    )
    signals_found = []

    # 逐个标的扫描（避免并行调用过多导致限流）
    for symbol in SYMBOLS:
        log(f"═══ 扫描 {symbol} ═══")
        result = await scan_symbol(symbol, dc)

        # 保存每个标的的多周期详情
        cache_file = CACHE_DIR / f"{symbol}.json"
        with open(cache_file, "w") as f:
            json.dump(result, f, indent=2, ensure_ascii=False)

        # 仅记录融合信号（至少 3 个周期一致）
        if result["fusion"] in ("LONG", "SHORT"):
            signals_found.append(result)
            log_signal(
                symbol=result["symbol"],
                signal=result["fusion"],
                price=result["price"],
                confidence=result.get("confidence", 0),
                fusion_details=result.get("fusion_details", ""),
                source="scanner",
            )
            # 飞书私聊推送
            price_str = f"${result['price']:,.2f}" if result['price'] > 0 else "?"
            direction = result['fusion']
            direction_emoji = "🟢" if direction == "LONG" else "🔴"
            conf = result.get('confidence', 0)
            conf_bar = "█" * int(conf * 10) + "░" * (10 - int(conf * 10))

            # 从多时间框架结果里提取详情
            tf_result = result.get("timeframe_results", [{}])[0]
            trend = tf_result.get("trend_state", "?") if isinstance(tf_result, dict) else "?"
            trigger = tf_result.get("trigger_type", "?") if isinstance(tf_result, dict) else "?"

            msg = (
                f"{direction_emoji} {direction} 信号 | {result['symbol']}\n"
                f"{'━' * 28}\n"
                f"价格:   {price_str}\n"
                f"置信度: {conf_bar} {conf:.0%}\n"
                f"趋势:   {trend}\n"
                f"触发:   {trigger}\n"
                f"{'━' * 28}\n"
                f"原因: {result.get('fusion_details', '')[:150]}\n"
                f"时间: {result['time']}"
            )
            send_dm(msg)
            log(f"  ✅ {symbol} 融合通过: {result['fusion']} ({result.get('fusion_details','')[:80]})")
        else:
            log(f"  {symbol} 融合未通过: {result.get('fusion_details','')[:120]}")

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

    # 保存当日统计（用于 MIN_AGREE 验证）
    stats = save_stats()
    log(f"📊 今日信号统计: {stats.get('total', 0)} 次 (LONG={stats.get('LONG', 0)}, SHORT={stats.get('SHORT', 0)})")

    # 运行复盘
    try:
        from layers.intelligence.review_agent import run_review
        run_review()
        log("📋 复盘完成")
    except Exception as e:
        log(f"⚠️ 复盘失败: {e}")


if __name__ == "__main__":
    asyncio.run(run_scanner())
