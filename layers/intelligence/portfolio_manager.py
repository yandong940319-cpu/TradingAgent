"""
Layer 2 — Portfolio Manager Agent

负责动态仓位、现金管理、风险预算、相关性控制、杠杆管理。
"""

from core.agent import BaseAgent
from core.protocols import AgentOutput, Signal, SystemState


class PortfolioManagerAgent(BaseAgent):
    """投资组合管理 Agent"""

    def __init__(self):
        super().__init__("Portfolio Manager", "portfolio_manager")
        self.cash_ratio = 0.3        # 30% 现金
        self.max_leverage = 1.0      # 无杠杆
        self.positions: dict = {}    # 当前持仓

    def supported_states(self) -> list[SystemState]:
        return [SystemState.GENERATE_SIGNAL, SystemState.WEIGHT_REBALANCE]

    async def analyze(self, context: dict) -> AgentOutput:
        symbol = context.get("symbol", "")
        signal = context.get("signal", {})

        # 计算仓位
        position_size = self._calculate_position(signal)
        # 检查相关性
        correlation_ok = self._check_correlation(symbol)

        return AgentOutput(
            symbol=symbol,
            timeframe=context.get("timeframe", "1h"),
            signal=Signal.LONG if position_size > 0 else Signal.NO_TRADE,
            confidence=signal.get("confidence", 0) if correlation_ok else 0,
            uncertainty=0.3,
            trade_allowed=correlation_ok and position_size > 0,
            trade_priority=self._calc_priority(signal),
            reason_codes=["PORTFOLIO_CHECKED"],
            metadata={
                "position_size": position_size,
                "cash_ratio": self.cash_ratio,
                "correlation_ok": correlation_ok,
            },
        )

    def _calculate_position(self, signal: dict) -> float:
        """基于信号计算仓位大小"""
        confidence = signal.get("confidence", 0)
        if confidence < 0.3:
            return 0.0
        return min(confidence * self.max_leverage, 1.0 - self.cash_ratio)

    def _check_correlation(self, symbol: str) -> bool:
        """检查与现有持仓的相关性"""
        return True  # TODO: 实现真实相关性检查

    def _calc_priority(self, signal: dict) -> int:
        return min(int(signal.get("confidence", 0) * 10), 10)
