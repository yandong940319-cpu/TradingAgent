"""
Layer 1 — Data Orchestrator

统一数据协调层，根据市场类型自动选择数据源。
"""

from enum import Enum

from layers.data.binance_data import BinanceDataAgent
from layers.data.ashare_data import AShareDataAgent
from layers.data.usstock_data import USStockDataAgent


class MarketType(Enum):
    CRYPTO = "crypto"
    ASHARE = "ashare"
    USSTOCK = "usstock"


def detect_market(symbol: str) -> MarketType:
    """根据标的代码自动判断市场类型"""
    symbol = symbol.upper()
    # 加密货币
    if symbol.endswith("USDT") or symbol.endswith("BTC") or symbol.endswith("ETH"):
        return MarketType.CRYPTO
    # A股
    if symbol.startswith("SH.") or symbol.startswith("SZ.") or symbol.startswith("BJ."):
        return MarketType.ASHARE
    # 美股（默认）
    return MarketType.USSTOCK


class DataOrchestrator:
    """数据协调器 — 根据市场类型派发到对应数据源"""

    def __init__(self, binance_key: str = "", binance_secret: str = ""):
        self.binance = BinanceDataAgent(binance_key, binance_secret)
        self.ashare = AShareDataAgent()
        self.usstock = USStockDataAgent()

    def get_agent(self, symbol: str):
        """根据标的返回对应的数据 Agent"""
        market = detect_market(symbol)
        if market == MarketType.CRYPTO:
            return self.binance
        elif market == MarketType.ASHARE:
            return self.ashare
        else:
            return self.usstock

    async def collect(self, symbol: str, timeframe: str = "1h") -> dict:
        """采集指定标的数据"""
        agent = self.get_agent(symbol)
        result = await agent.analyze({"symbol": symbol, "timeframe": timeframe})
        return {
            "symbol": symbol,
            "market": detect_market(symbol).value,
            "timeframe": timeframe,
            "data": result.to_json(),
            "metadata": result.metadata,
        }

    def get_market_type(self, symbol: str) -> str:
        return detect_market(symbol).value
