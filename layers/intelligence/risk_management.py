"""
Layer 2 — Risk Management Agent

风控检查，拥有最终 veto 权限。
"""

from core.agent import BaseAgent
from core.protocols import AgentOutput, Signal, SystemState


class RiskManagementAgent(BaseAgent):
    """风险管理 Agent — 风控拥有最终 veto 权限"""

    def __init__(self):
        super().__init__("Risk Manager", "risk_manager")
        self.max_daily_loss = 0.05  # 5% 最大日亏损
        self.max_position_size = 0.2  # 20% 最大单笔仓位
        self.max_correlation = 0.7    # 最大相关性

    def supported_states(self) -> list[SystemState]:
        return [SystemState.RISK_CHECK]

    async def analyze(self, context: dict) -> AgentOutput:
        signal = context.get("signal", {})
        return AgentOutput(
            symbol=context.get("symbol", ""),
            timeframe=context.get("timeframe", "1h"),
            signal=Signal.NO_TRADE,
            confidence=0.8,
            uncertainty=0.2,
            trade_allowed=self._check_constraints(signal),
            reason_codes=self._get_reasons(signal),
        )

    def _check_constraints(self, signal: dict) -> bool:
        """检查所有风控约束"""
        # TODO: 实现真实检查
        return True

    def _get_reasons(self, signal: dict) -> list[str]:
        reasons = []
        # TODO: 添加具体风控原因
        return reasons or ["RISK_PASSED"]
