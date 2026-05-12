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
from layers.intelligence.multi_tf_signal import compute_signal, klines_to_df, resample_to_3day


class BacktestEngine:
    """回测引擎 — 在历史数据上运行 Agent 流水线"""

    def __init__(self, data_agent=None):
        self.data_agent = data_agent
        self.trades = []
        self.equity_curve = []

    async def run(self, symbol: str, start_date: str = "", end_date: str = "",
                  timeframe: str = "15m", initial_capital: float = 10000, days: int = 0) -> dict:
        """执行回测"""
        print(f"[Backtest] Starting backtest for {symbol}")

        # 1. 获取历史数据（主周期 + 多时间框架）
        klines = await self._fetch_historical(symbol, timeframe, days=days)
        if not klines:
            return {"error": "No data fetched"}

        print(f"[Backtest] Fetched {len(klines)} klines")

        # 拉取多时间框架数据
        self.all_data = {}
        mtf_tfs = {"15m": "15m", "1h": "1h", "4h": "4h", "1d": "1d", "1w": "1w"}
        for name, tf in mtf_tfs.items():
            raw = await self._fetch_historical(symbol, tf, days=days)
            self.all_data[name] = klines_to_df(raw)

        daily_df = self.all_data.get("1d", pd.DataFrame())

        # 2. 逐根 K 线运行流水线
        capital = initial_capital
        position = 0.0  # 0~1 仓位比例
        trade_log = []
        equity = [{"time": klines[0]["date" if "date" in klines[0] else "time"], "equity": capital}]
        self._symbol = symbol
        entry_price = 0.0     # 开仓价
        entry_index = -1      # 开仓时的 K 线索引
        peak_pnl    = 0.0     # 持仓期间最高盈利
        STOP_LOSS       = 0.015  # 1.5% 硬止损，任何情况都触发
        TRAILING_START  = 0.005  # 盈利超过 0.5% 启动追踪止损
        TRAILING_STEP   = 0.005 # 追踪止损回撤 0.5% 触发
        MIN_HOLD_BARS   = 768   # 最少持仓 K 线数（15m × 768 = 8天）
        TAKE_PROFIT     = 0.04  # 固定止盈 4%

        for i in range(len(klines)):
            k = klines[i]
            price = float(k.get("close", k.get(4, 0)))

            # ── 退出检查（追踪止损，无 AI_EXIT） ──
            if position != 0 and entry_price > 0:
                hold_bars = i - entry_index
                pnl = (price - entry_price) / entry_price
                if position < 0:
                    pnl = -pnl

                # 更新最高盈利点
                peak_pnl = max(peak_pnl, pnl)

                should_exit = False
                exit_reason = ""

                # 第一级：硬止损——任何时候都触发
                # 动态止损：持仓超过20根且有盈利时收紧保护
                if hold_bars > 20 and pnl > 0:
                    effective_stop = pnl - 0.01  # 最多回吐 1%
                else:
                    effective_stop = -STOP_LOSS  # 正常 2% 止损

                if pnl <= effective_stop:
                    should_exit = True
                    exit_reason = "HARD_STOP"

                # 第二级：追踪止损——盈利超过 1% 后，回撤 0.5% 触发
                elif peak_pnl >= TRAILING_START and (peak_pnl - pnl) >= TRAILING_STEP:
                    should_exit = True
                    exit_reason = "TRAILING_STOP"

                # 第三级：最少持仓满足后，固定止盈
                elif hold_bars >= MIN_HOLD_BARS and pnl >= TAKE_PROFIT:
                    should_exit = True
                    exit_reason = "TAKE_PROFIT"

                # 完全移除 AI_EXIT

                if should_exit:
                    action = "CLOSE_LONG" if position > 0 else "CLOSE_SHORT"
                    trade_log.append({
                        "time": k.get("date", k.get("time", "")),
                        "action": action,
                        "price": price,
                        "position": 0,
                        "signal": exit_reason,
                        "hold_days": hold_bars,
                        "exit_reason": exit_reason,
                    })
                    position = 0
                    # 重置 peak_pnl
                    # 让 equity.append 在下面执行

            # ── 开仓逻辑（仅在无持仓时） ──
            if position == 0:
                # 每96根15m才检查一次信号（= 每根日线）
                if i % 96 != 0:
                    continue
                peak_pnl = 0.0  # 重置追踪止损基线
                # 找当前 K 线对应的日线索引
                bar_time = k.get("time", k.get(0, 0))
                daily_idx = -1
                if not daily_df.empty:
                    matched = daily_df[daily_df["time"] <= bar_time].index
                    if len(matched):
                        daily_idx = int(matched[-1])
                signal = self._simulate_pipeline(symbol, daily_idx)

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
                                 start: str = "", end: str = "", days: int = 0) -> list:
        """获取 5 年历史 K 线数据（分页拉取）"""
        import time as _time
        import requests
        base = "https://api.binance.com"

        # 计算数据毫秒时间戳
        end_ms = int(_time.time() * 1000)
        if days and days > 0:
            start_ms = end_ms - int(days * 24 * 3600 * 1000)
        else:
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

    def _get_mtf_signal_at(self, symbol: str, all_data: dict, current_idx: int) -> str:
        """
        在历史某个位置，用当时能看到的数据计算多时间框架信号。
        all_data: {"1d": df, "4h": df, "1h": df, "15m": df, "1w": df}
        current_idx: 当前是日线数据的第几根
        返回: "LONG" / "SHORT" / "NO_TRADE"
        """
        MIN_BARS = 60  # 至少需要60根K线才能计算

        # 截取到当前时间点之前的数据（不能用未来数据）
        df_daily = all_data.get("1d", pd.DataFrame())
        if df_daily.empty or current_idx < MIN_BARS:
            return "NO_TRADE"

        # 用当前时间点的时间戳过滤各时间框架
        current_time = df_daily["time"].iloc[current_idx]

        def slice_df(df):
            if df.empty:
                return df
            return df[df["time"] <= current_time].tail(100).reset_index(drop=True)

        df_daily_slice  = slice_df(all_data.get("1d", pd.DataFrame()))
        df_weekly_slice = slice_df(all_data.get("1w", pd.DataFrame()))
        df_4h_slice     = slice_df(all_data.get("4h", pd.DataFrame()))
        df_1h_slice     = slice_df(all_data.get("1h", pd.DataFrame()))
        df_15m_slice    = slice_df(all_data.get("15m", pd.DataFrame()))
        df_3day_slice   = resample_to_3day(df_daily_slice)

        try:
            result = compute_signal(
                df_weekly=df_weekly_slice,
                df_3day=df_3day_slice,
                df_daily=df_daily_slice,
                df_4h=df_4h_slice,
                df_1h=df_1h_slice,
                df_15m=df_15m_slice,
            )
            return result.signal
        except Exception:
            return "NO_TRADE"

    def _simulate_pipeline(self, symbol: str, current_idx: int) -> str:
        return self._get_mtf_signal_at(symbol, self.all_data, current_idx)

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
