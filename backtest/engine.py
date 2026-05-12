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

        for i in range(len(klines)):
            k = klines[i]
            price = float(k.get("close", k.get(4, 0)))

            # 每根 K 线运行分析流水线（传全部历史 K 线做上下文）
            signal = await self._simulate_pipeline(k, history=klines[:i + 1])

            # 根据信号调整仓位
            if signal == "LONG" and position < 0.5:
                position = 0.2
                trade_log.append({
                    "time": k.get("date", k.get("time", "")),
                    "action": "BUY",
                    "price": price,
                    "position": position,
                    "signal": signal,
                })
            elif signal == "SHORT" and position > -0.3:
                position = -0.1
                trade_log.append({
                    "time": k.get("date", k.get("time", "")),
                    "action": "SELL",
                    "price": price,
                    "position": position,
                    "signal": signal,
                })
            elif signal == "NO_TRADE" and abs(position) > 0:
                # 平仓
                if position > 0:
                    trade_log.append({
                        "time": k.get("date", k.get("time", "")),
                        "action": "CLOSE_LONG",
                        "price": price,
                        "position": 0,
                        "signal": signal,
                    })
                elif position < 0:
                    trade_log.append({
                        "time": k.get("date", k.get("time", "")),
                        "action": "CLOSE_SHORT",
                        "price": price,
                        "position": 0,
                        "signal": signal,
                    })
                position = 0

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
        """获取历史 K 线数据"""
        if self.data_agent:
            # 使用数据 Agent 获取
            try:
                if hasattr(self.data_agent, 'get_klines'):
                    # Binance 模式
                    result = self.data_agent.get_klines(symbol, tf, limit=1000)
                    if result:
                        return result
            except:
                pass

        # 降级: 直接从 Binance API 获取
        import requests
        base = "https://api.binance.com"
        params = {"symbol": symbol.upper(), "interval": tf, "limit": 1000}
        try:
            resp = requests.get(f"{base}/api/v3/klines", params=params, timeout=15)
            if resp.status_code == 200:
                return [{0: k[0], 1: k[1], 2: k[2], 3: k[3], 4: k[4], 5: k[5],
                         "time": k[0], "open": float(k[1]), "high": float(k[2]),
                         "low": float(k[3]), "close": float(k[4]), "volume": float(k[5])}
                        for k in resp.json()]
        except Exception as e:
            print(f"[Backtest] Fetch error: {e}")
        return []

    async def _simulate_pipeline(self, kline: dict, history: list = None) -> str:
        """调用 DeepSeek Agent，基于最近 20 根 K 线返回信号"""
        from core.deepseek_client import DeepSeekClient

        # 用最近20根K线构建上下文
        recent = (history or [kline])[-20:]
        lines = []
        for k in recent:
            t = k.get("date", k.get("time", ""))
            c = float(k.get("close", k.get(4, 0)))
            h = float(k.get("high",  k.get(2, c)))
            l = float(k.get("low",   k.get(3, c)))
            v = float(k.get("volume",k.get(5, 0)))
            lines.append(f"time={t} H={h:.0f} L={l:.0f} C={c:.0f} V={v:.0f}")

        summary = "\n".join(lines)
        ai = DeepSeekClient()
        result = await asyncio.to_thread(ai.scan_signal, self._symbol, summary, len(recent))
        return result.get("signal", "NO_TRADE")

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
