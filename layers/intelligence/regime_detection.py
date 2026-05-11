"""
Layer 2 — Intelligence: Regime Detection Agent

检测当前市场状态（震荡/趋势/高波动/危机）。
"""

from datetime import datetime
from core.agent import BaseAgent
from core.protocols import AgentOutput, Signal, MarketRegime, SystemState


class RegimeDetectionAgent(BaseAgent):
    """市场状态检测 Agent"""

    def __init__(self, config: dict = None):
        super().__init__("Regime Detector", "regime_detector", config)

    def supported_states(self) -> list[SystemState]:
        return [SystemState.ANALYZE, SystemState.GENERATE_SIGNAL]

    async def analyze(self, context: dict) -> AgentOutput:
        symbol = context.get("symbol", "UNKNOWN")
        tf = context.get("timeframe", "1h")

        # 调用 AI 判断市场状态
        regime = await self._detect_regime(symbol, tf)

        return AgentOutput(
            symbol=symbol,
            timeframe=tf,
            signal=Signal.NEUTRAL,
            confidence=0.7,
            uncertainty=0.3,
            market_regime=regime,
            reason_codes=[f"REGIME_{regime.value}"],
        )

    async def _detect_regime(self, symbol: str, tf: str) -> MarketRegime:
        """通过 DeepSeek API 判断市场状态"""
        # TODO: 接入 DeepSeek API 进行实时判断
        # 临时返回默认值
        return MarketRegime.UNKNOWN
