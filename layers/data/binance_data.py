"""
Layer 1 — Data: 加密货币数据源 (Binance)

负责 5m/15m/1h K线、订单簿、24h ticker 数据采集。
"""

import hashlib
import hmac
import time
import json
from datetime import datetime, timedelta
from typing import Optional

import requests

from core.agent import BaseAgent
from core.protocols import AgentOutput, Signal, SystemState


class BinanceDataAgent(BaseAgent):
    """币安数据采集 Agent"""

    def __init__(self, api_key: str = "", api_secret: str = ""):
        super().__init__("Binance Data", "binance_data")
        self.base_url = "https://api.binance.com"
        self.api_key = api_key
        self.api_secret = api_secret
        self.session = requests.Session()
        self.session.headers.update({"X-MBX-APIKEY": self.api_key})

    def supported_states(self) -> list[SystemState]:
        return [SystemState.WAIT_DATA, SystemState.ANALYZE]

    def set_credentials(self, api_key: str, api_secret: str):
        self.api_key = api_key
        self.api_secret = api_secret
        self.session.headers.update({"X-MBX-APIKEY": self.api_key})

    async def analyze(self, context: dict) -> AgentOutput:
        symbol = context.get("symbol", "BTCUSDT")
        tf = context.get("timeframe", "1h")

        klines = self.get_klines(symbol, tf, limit=100)
        ticker = self.get_ticker_24h(symbol)

        if not klines:
            return AgentOutput(
                symbol=symbol, timeframe=tf,
                signal=Signal.NO_TRADE, confidence=0, uncertainty=1,
                reason_codes=["BINANCE_DATA_FAILED"],
            )

        return AgentOutput(
            symbol=symbol, timeframe=tf,
            signal=Signal.NEUTRAL,
            confidence=0.8,
            uncertainty=0.2,
            expected_volatility=float(ticker.get("priceChangePercent", 0)) / 100 if ticker else 0,
            reason_codes=["DATA_READY"],
            metadata={
                "close": ticker.get("lastPrice", 0),
                "volume_24h": ticker.get("volume", 0),
                "high_24h": ticker.get("highPrice", 0),
                "low_24h": ticker.get("lowPrice", 0),
                "klines_count": len(klines),
                "klines": klines[-10:],  # 最近10根
            },
        )

    def get_klines(self, symbol: str, interval: str = "1h",
                   limit: int = 100, start_time: Optional[int] = None) -> list:
        """获取K线数据"""
        params = {"symbol": symbol.upper(), "interval": interval, "limit": limit}
        if start_time:
            params["startTime"] = start_time
        try:
            resp = self.session.get(f"{self.base_url}/api/v3/klines", params=params, timeout=10)
            if resp.status_code == 200:
                return [
                    {
                        "time": k[0], "open": float(k[1]), "high": float(k[2]),
                        "low": float(k[3]), "close": float(k[4]), "volume": float(k[5]),
                    }
                    for k in resp.json()
                ]
        except Exception as e:
            print(f"[BinanceData] Error: {e}")
        return []

    def get_ticker_24h(self, symbol: str) -> dict:
        """获取24小时ticker"""
        try:
            resp = self.session.get(
                f"{self.base_url}/api/v3/ticker/24hr",
                params={"symbol": symbol.upper()}, timeout=10
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            print(f"[BinanceData] Ticker Error: {e}")
        return {}

    def get_orderbook(self, symbol: str, limit: int = 20) -> dict:
        """获取订单簿"""
        try:
            resp = self.session.get(
                f"{self.base_url}/api/v3/depth",
                params={"symbol": symbol.upper(), "limit": limit}, timeout=10
            )
            if resp.status_code == 200:
                return resp.json()
        except Exception as e:
            print(f"[BinanceData] Orderbook Error: {e}")
        return {}
