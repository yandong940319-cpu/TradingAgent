"""
AI Quant Fund OS — 回测引擎

基于历史 K 线数据运行 Agent 流水线，计算回测指标。
"""

import asyncio
import time
from datetime import datetime, timedelta
from typing import Optional
import pandas as pd
from pathlib import Path


class BacktestEngine:
    """回测引擎 — 在历史数据上运行 Agent 流水线"""

    def __init__(self, data_agent=None):
        self.data_agent = data_agent
        self.trades = []
        self.equity_curve = []

    async def run(self, symbol: str, start_date: str, end_date: str,
                  timeframe: str = "1d", initial_capital: float = 10000) -> dict:
        """执行回测"""
        print(f"[Backtest] Starting backtest for {symbol} ({start_date} ~ {end_date})")

        # 1. 获取历史数据
        klines = await self._fetch_historical(symbol, timeframe, start_date, end_date)
        if not klines:
            return {"error": "No data fetched"}

        print(f"[Backtest] Fetched {len(klines)} klines")

        # 2. 逐根 K 线运行流水线
        capital = initial_capital
        position = 0.0  # 0~1 仓位比例
        trade_log = []
        equity = [{"time": klines[0]["date" if "date" in klines[0] else "time"], "equity": capital}]
        self._symbol = symbol
        entry_price = 0.0    # 开仓价
        entry_index = -1     # 开仓时的 K 线索引
        STOP_LOSS     = 0.02 # 2% 硬止损，任何情况都触发
        TAKE_PROFIT   = 0.04 # 4% 止盈
        MIN_HOLD_DAYS = 3    # 最少持仓天数，但止损例外

        for i in range(len(klines)):
            k = klines[i]
            price = float(k.get("close", k.get(4, 0)))

            # ── 三级退出检查（先于新信号） ──
            if position != 0 and entry_price > 0:
                hold_days = i - entry_index
                pnl = (price - entry_price) / entry_price
                if position < 0:
                    pnl = -pnl

                should_exit = False
                exit_reason = ""

                # 第一级：硬止损——无条件触发，不受持仓天数限制
                if pnl <= -STOP_LOSS:
                    should_exit = True
                    exit_reason = "HARD_STOP"

                # 第二级：止盈——无条件触发
                elif pnl >= TAKE_PROFIT:
                    should_exit = True
                    exit_reason = "TAKE_PROFIT"

                # 第三级：持仓满最少天数后，AI 才能介入平仓
                elif hold_days >= MIN_HOLD_DAYS:
                    signal = await self._simulate_pipeline(k, history=klines[:i + 1])
                    expected_dir = "LONG" if position > 0 else "SHORT"
                    if signal == "NO_TRADE" or signal != expected_dir:
                        should_exit = True
                        exit_reason = "AI_EXIT"

                if should_exit:
                    action = "CLOSE_LONG" if position > 0 else "CLOSE_SHORT"
                    trade_log.append({
                        "time": k.get("date", k.get("time", "")),
                        "action": action,
                        "price": price,
                        "position": 0,
                        "signal": exit_reason,
                        "hold_days": hold_days,
                        "exit_reason": exit_reason,
                    })
                    position = 0
                    # 跳过本根 K 线的开仓逻辑（但不跳过权益计算）
                    # 让 equity.append 在下面执行

            # ── 开仓逻辑（仅在无持仓时） ──
            if position == 0:
                signal = await self._simulate_pipeline(k, history=klines[:i + 1])

                if signal == "LONG":
                    position = 0.2
                    entry_price = price
                    entry_index = i
                    trade_log.append({
                        "time": k.get("date", k.get("time", "")),
                        "action": "BUY",
                        "price": price,
                        "position": position,
                        "signal": signal,
                    })
                elif signal == "SHORT":
                    position = -0.1
                    entry_price = price
                    entry_index = i
                    trade_log.append({
                        "time": k.get("date", k.get("time", "")),
                        "action": "SELL",
                        "price": price,
                        "position": position,
                        "signal": signal,
                    })

            # 计算当前权益
            if i > 0:
                prev_price = float(klines[i-1].get("close", klines[i-1].get(4, 0)))
                if position != 0:
                    ret = (price - prev_price) / prev_price * position
                    capital *= (1 + ret)

            equity.append({
                "time": k.get("date", k.get("time", "")),
                "equity": capital,
            })

        # 3. 计算指标
        result = self._calculate_metrics(capital, initial_capital, trade_log, equity)
        result["trades"] = trade_log

        # 保存回测结果为 CSV（配对开平仓，计算每笔盈亏）
        if trade_log:
            rows = []
            open_trade = None
            for t in trade_log:
                action = t["action"]
                if action in ("BUY", "SELL"):
                    open_trade = t.copy()
                    open_trade["symbol"] = symbol
                elif action in ("CLOSE_LONG", "CLOSE_SHORT") and open_trade:
                    entry_price = float(open_trade["price"])
                    exit_price  = float(t["price"])
                    pnl_pct = (exit_price - entry_price) / entry_price * 100
                    if open_trade["signal"] == "SHORT":
                        pnl_pct = -pnl_pct
                    rows.append({
                        "time":        open_trade["time"],
                        "symbol":      symbol,
                        "signal":      open_trade["signal"],
                        "entry_price": round(entry_price, 4),
                        "exit_price":  round(exit_price, 4),
                        "pnl_pct":     round(pnl_pct, 3),
                        "outcome":     "WIN" if pnl_pct > 0 else "LOSS",
                        "position":    open_trade["position"],
                        "hold_days":   t.get("hold_days", 0),
                        "exit_reason": t.get("exit_reason", ""),
                    })
                    open_trade = None
            if rows:
                out_path = Path(__file__).parent.parent / "scanner_data" / "backtest_trades.csv"
                out_path.parent.mkdir(exist_ok=True)
                pd.DataFrame(rows).to_csv(out_path, index=False)
                print(f"[Backtest] {len(rows)} trades saved → {out_path}")

        result["equity_curve"] = equity
        result["total_klines"] = len(klines)

        print(f"[Backtest] Done: final=${capital:.0f}, trades={len(trade_log)}")
        return result

    async def _fetch_historical(self, symbol: str, tf: str,
                                 start: str, end: str) -> list:
        """获取 5 年历史 K 线数据（分页拉取）"""
        import time as _time
        import requests
        base = "https://api.binance.com"

        # 计算 5 年前的毫秒时间戳
        end_ms = int(_time.time() * 1000)
        start_ms = end_ms - int(5 * 365.25 * 24 * 3600 * 1000)

        all_klines = []
        while start_ms < end_ms:
            params = {
                "symbol": symbol.upper(),
                "interval": tf,
                "limit": 1000,
                "startTime": start_ms,
            }
            try:
                resp = requests.get(f"{base}/api/v3/klines", params=params, timeout=15)
                if resp.status_code != 200:
                    print(f"[Backtest] API error {resp.status_code}: {resp.text[:100]}")
                    break
                klines = resp.json()
                if not klines:
                    break
                parsed = [
                    {0: k[0], 1: k[1], 2: k[2], 3: k[3], 4: k[4], 5: k[5],
                     "time": k[0], "open": float(k[1]), "high": float(k[2]),
                     "low": float(k[3]), "close": float(k[4]), "volume": float(k[5])}
                    for k in klines
                ]
                all_klines.extend(parsed)
                # 下一页从最后一根 K 线的下一毫秒开始
                start_ms = klines[-1][0] + 1
                if len(klines) < 1000:
                    break  # 没有更多数据了
            except Exception as e:
                print(f"[Backtest] Fetch error: {e}")
                break

        print(f"[Backtest] Fetched {len(all_klines)} klines ({symbol} {tf})")
        return all_klines

    async def _simulate_pipeline(self, kline: dict, history: list = None) -> str:
        """两阶段架构：经典指标过滤 → LLM 审查"""
        recent = (history or [kline])[-210:]  # 用 210 根以支持 MA200 计算
        closes = [float(k.get("close", k.get(4, 0))) for k in recent]
        volumes = [float(k.get("volume", k.get(5, 0))) for k in recent]

        # ── 第一阶段：经典指标生成信号 ──────────────────
        # RSI(14) 序列
        rsi_list = []
        for i in range(14, len(closes)):
            chunk = closes[i - 14:i + 1]
            gains = [chunk[j] - chunk[j - 1] for j in range(1, len(chunk)) if chunk[j] > chunk[j - 1]]
            losses = [abs(chunk[j] - chunk[j - 1]) for j in range(1, len(chunk)) if chunk[j] <= chunk[j - 1]]
            avg_g = sum(gains) / 14 if len(gains) >= 14 else 0.001
            avg_l = sum(losses) / 14 if len(losses) >= 14 else 0.001
            rsi_list.append(100 - (100 / (1 + avg_g / avg_l)))
        rsi = rsi_list[-1] if rsi_list else 50

        # RSI 相对均值
        import statistics
        rsi_ma = statistics.mean(rsi_list[-20:]) if len(rsi_list) >= 20 else (rsi if rsi_list else 50)

        # MA5 / MA10 / MA20 / MA50 / MA200
        ma5   = sum(closes[-5:])   / 5   if len(closes) >= 5   else closes[-1]
        ma10  = sum(closes[-10:])  / 10  if len(closes) >= 10  else closes[-1]
        ma20  = sum(closes[-20:])  / 20  if len(closes) >= 20  else closes[-1]
        ma50  = sum(closes[-50:])  / 50  if len(closes) >= 50  else None
        ma200 = sum(closes[-200:]) / 200 if len(closes) >= 200 else None
        price = closes[-1]

        # 前一根的 MA5 / MA10（用于金叉死叉判断）
        prev_ma5  = sum(closes[-6:-1])  / 5  if len(closes) >= 6  else ma5
        prev_ma10 = sum(closes[-11:-1]) / 10 if len(closes) >= 11 else ma10

        # 成交量比
        vol_ratio = (sum(volumes[-3:]) / 3) / (sum(volumes[-10:]) / 10) if len(volumes) >= 10 else 1.0

        # ── Regime 检测层：MA50 < MA200 → 熊市，不做多 ──
        if ma50 is not None and ma200 is not None:
            if ma50 < ma200:
                # 死叉状态：MA50 在 MA200 下方 = 熊市，不做多
                return "NO_TRADE"

        # ── 规则：金叉/超卖 → MA20 + 成交量过滤 ──
        rsi_low  = rsi < rsi_ma * 0.95
        rsi_high = rsi > rsi_ma * 1.05

        golden_cross = prev_ma5 < prev_ma10 and ma5 > ma10
        death_cross  = prev_ma5 > prev_ma10 and ma5 < ma10

        if (golden_cross or rsi_low) and price > ma20 and vol_ratio > 1.0:
            candidate = "LONG"
        elif (death_cross or rsi_high) and price < ma20 and vol_ratio > 1.0:
            return "NO_TRADE"  # BTC 牛市结构下暂停空单
        else:
            return "NO_TRADE"

        # ── 第二阶段：LLM 审查候选信号 ──────────────────
        from core.deepseek_client import DeepSeekClient
        summary = "\n".join(
            f"C={c:.0f} V={v:.0f}" for c, v in zip(closes[-10:], volumes[-10:])
        )
        prompt_data = {
            "symbol":    self._symbol,
            "candidate": candidate,
            "rsi":       round(rsi, 1),
            "ma5":       round(ma5, 1),
            "ma20":      round(ma20, 1),
            "vol_ratio": round(vol_ratio, 2),
            "recent_10": summary,
        }
        ai = DeepSeekClient()
        result = await asyncio.to_thread(ai.validate_signal, prompt_data)
        return result.get("decision", "NO_TRADE")

    def _calculate_metrics(self, final: float, initial: float,
                           trades: list, equity: list) -> dict:
        """计算回测指标"""
        total_return = (final - initial) / initial * 100

        # 胜率
        wins = 0
        for t in trades:
            if "CLOSE" in t.get("action", "") and t.get("price", 0) > 0:
                wins += 1
        win_rate = wins / max(1, len(trades)) * 100 if trades else 0

        # 最大回撤
        peak = initial
        max_dd = 0
        for e in equity:
            eq = e["equity"]
            if eq > peak:
                peak = eq
            dd = (peak - eq) / peak * 100
            if dd > max_dd:
                max_dd = dd

        # 夏普比（简化）
        returns = []
        for i in range(1, len(equity)):
            r = (equity[i]["equity"] - equity[i-1]["equity"]) / equity[i-1]["equity"]
            returns.append(r)
        avg_ret = sum(returns) / max(1, len(returns))
        std_ret = (sum((r - avg_ret)**2 for r in returns) / max(1, len(returns))) ** 0.5
        sharpe = (avg_ret / max(0.001, std_ret)) * (252 ** 0.5) if std_ret > 0 else 0

        return {
            "total_return_pct": round(total_return, 2),
            "final_equity": round(final, 2),
            "total_trades": len(trades),
            "win_rate_pct": round(win_rate, 1),
            "max_drawdown_pct": round(max_dd, 2),
            "sharpe_ratio": round(sharpe, 2),
            "avg_return_pct": round(avg_ret * 100, 4),
        }
