"""
Layer 1 — Data: 美股数据源 (yfinance)

负责美股日线/分钟线、财报数据。
"""

from datetime import datetime, timedelta

from core.agent import BaseAgent
from core.protocols import AgentOutput, Signal, SystemState


class USStockDataAgent(BaseAgent):
    """美股数据采集 Agent"""

    def __init__(self):
        super().__init__("US Stock Data", "usstock_data")

    def supported_states(self) -> list[SystemState]:
        return [SystemState.WAIT_DATA, SystemState.ANALYZE]

    async def analyze(self, context: dict) -> AgentOutput:
        symbol = context.get("symbol", "SPY")
        tf = context.get("timeframe", "1d")

        klines = self.get_klines(symbol, tf)

        if not klines:
            return AgentOutput(
                symbol=symbol, timeframe=tf,
                signal=Signal.NO_TRADE, confidence=0, uncertainty=1,
                reason_codes=["USSTOCK_DATA_FAILED"],
            )

        return AgentOutput(
            symbol=symbol, timeframe=tf,
            signal=Signal.NEUTRAL,
            confidence=0.8,
            uncertainty=0.2,
            reason_codes=["DATA_READY"],
            metadata={
                "klines_count": len(klines),
                "recent_data": klines[-5:] if len(klines) >= 5 else klines,
            },
        )

    def get_klines(self, symbol: str, timeframe: str = "1d",
                   period: str = "3mo") -> list[dict]:
        """
        获取美股K线
        symbol: SPY, AAPL, TSLA 等
        timeframe: 1d=日线, 1h=小时, 5m=5分钟, 15m=15分钟
        """
        import yfinance as yf
        import time

        interval_map = {"1d": "1d", "1h": "1h", "5m": "5m", "15m": "15m", "1wk": "1wk"}
        interval = interval_map.get(timeframe, "1d")
        period_map = {"1d": "1mo", "1h": "5d", "5m": "1d", "15m": "5d", "1wk": "6mo"}
        period = period_map.get(timeframe, "3mo")

        # yfinance 重试（限流时等待后重试）
        max_retries = 3
        for attempt in range(max_retries):
            try:
                ticker = yf.Ticker(symbol)
                df = ticker.history(period=period, interval=interval)
                if df.empty:
                    raise ValueError("Empty data")
                records = []
                for idx, row in df.iterrows():
                    records.append({
                        "date": str(idx),
                        "open": float(row["Open"]),
                        "high": float(row["High"]),
                        "low": float(row["Low"]),
                        "close": float(row["Close"]),
                        "volume": int(row["Volume"]),
                    })
                return records
            except Exception as e:
                print(f"[USStockData] yfinance attempt {attempt+1}/{max_retries} failed: {e}")
                if attempt < max_retries - 1:
                    time.sleep(3 * (attempt + 1))  # 递增等待
                continue

        # 所有重试失败后尝试 akshare
        return self._fallback_akshare(symbol, timeframe)

    def _fallback_akshare(self, symbol: str, timeframe: str) -> list[dict]:
        """使用 akshare 作为美股数据降级方案"""
        try:
            import akshare as ak
            # akshare 美股用 'US' 前缀
            us_symbol = symbol if symbol.startswith(('^', '=')) else symbol
            df = ak.stock_us_hist(symbol=us_symbol, period="daily")
            if df.empty:
                return []
            records = []
            for _, row in df.iterrows():
                records.append({
                    "date": str(row.get("日期", "")),
                    "open": float(row.get("开盘", 0)),
                    "high": float(row.get("最高", 0)),
                    "low": float(row.get("最低", 0)),
                    "close": float(row.get("收盘", 0)),
                    "volume": int(row.get("成交量", 0)),
                })
            return records
        except Exception as e2:
            print(f"[USStockData] akshare also failed: {e2}")
            return []

    def get_fundamentals(self, symbol: str) -> dict:
        """获取基本面数据"""
        import yfinance as yf
        try:
            ticker = yf.Ticker(symbol)
            info = ticker.info
            return {
                "market_cap": info.get("marketCap", 0),
                "pe_ratio": info.get("trailingPE", 0),
                "eps": info.get("trailingEps", 0),
                "dividend_yield": info.get("dividendYield", 0),
                "sector": info.get("sector", ""),
            }
        except Exception as e:
            print(f"[USStockData] Fundamentals Error: {e}")
            return {}
