"""
Layer 3 — Governance: CIO Agent

最终仲裁者，综合所有 Agent 输出做最终决策。
"""

from core.agent import BaseAgent
from core.protocols import AgentOutput, Signal, SystemState


class CIOAgent(BaseAgent):
    """CIO Agent — 最终决策仲裁者"""

    def __init__(self):
        super().__init__("CIO", "cio_agent")

    def supported_states(self) -> list[SystemState]:
        return [SystemState.CIO_REVIEW]

    async def analyze(self, context: dict) -> AgentOutput:
        signal = context.get("signal", {})
        risk_result = context.get("risk", {})
        debate = context.get("debate", {})

        decision = self._make_decision(signal, risk_result, debate)

        return AgentOutput(
            symbol=context.get("symbol", ""),
            timeframe=context.get("timeframe", "1h"),
            signal=decision["signal"],
            confidence=decision["confidence"],
            uncertainty=1.0 - decision["confidence"],
            trade_allowed=decision["trade_allowed"],
            trade_priority=decision["priority"],
            reason_codes=decision["reasons"],
            metadata={"cio_decision": decision},
        )

    def _make_decision(self, signal: dict, risk: dict, debate: dict) -> dict:
        """CIO 决策逻辑"""
        # 默认 NO_TRADE
        decision = {
            "signal": Signal.NO_TRADE,
            "confidence": 0.0,
            "trade_allowed": False,
            "priority": 0,
            "reasons": [],
        }

        # 1. 风控 veto
        if not risk.get("trade_allowed", False):
            decision["reasons"].append("RISK_VETO")
            return decision

        # 2. 综合辩论结果
        bull_conf = debate.get("bull", {}).get("confidence", 0)
        bear_conf = debate.get("bear", {}).get("confidence", 0)
        risk_level = debate.get("risk", {}).get("confidence", 0)

        net_bias = bull_conf - bear_conf

        # 3. 高于风险阈值才允许交易
        if risk_level > 0.7:
            decision["reasons"].append("RISK_TOO_HIGH")
            return decision

        # 4. 信号方向决定
        signal_dir = signal.get("signal", "NO_TRADE")
        signal_conf = signal.get("confidence", 0)

        if signal_dir in ["LONG", "SHORT"] and signal_conf > 0.6 and abs(net_bias) > 0.2:
            decision["signal"] = Signal.LONG if net_bias > 0 else Signal.SHORT
            decision["confidence"] = (signal_conf + abs(net_bias)) / 2
            decision["trade_allowed"] = True
            decision["priority"] = min(int(decision["confidence"] * 10), 10)
            decision["reasons"].append("CIO_APPROVED")

        return decision
