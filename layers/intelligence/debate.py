"""
Layer 2 — Intelligence: Debate Agent

Bull vs Bear vs Risk 三方辩论机制，CIO 最终仲裁。
非简单多数投票，而是观点碰撞。
"""

from dataclasses import dataclass
from core.agent import BaseAgent
from core.protocols import AgentOutput, Signal, MarketRegime, SystemState


@dataclass
class DebatePosition:
    """辩论方立场"""
    side: str  # BULL / BEAR / RISK
    arguments: list[str]
    confidence: float
    key_levels: dict = None


class BullAgent(BaseAgent):
    """多方 Agent — 找做多理由"""

    def __init__(self):
        super().__init__("Bull", "bull_agent")

    def supported_states(self) -> list[SystemState]:
        return [SystemState.DEBATE]

    async def analyze(self, context: dict) -> AgentOutput:
        return self._build_output(context, Signal.LONG, 0.5, ["BULL_CASE_PENDING"])

    def _build_output(self, ctx: dict, signal: Signal, conf: float, reasons: list[str]) -> AgentOutput:
        return AgentOutput(
            symbol=ctx.get("symbol", ""), timeframe=ctx.get("timeframe", "1h"),
            signal=signal, confidence=conf, uncertainty=1-conf,
            reason_codes=reasons,
        )


class BearAgent(BaseAgent):
    """空方 Agent — 找做空理由"""

    def __init__(self):
        super().__init__("Bear", "bear_agent")

    def supported_states(self) -> list[SystemState]:
        return [SystemState.DEBATE]

    async def analyze(self, context: dict) -> AgentOutput:
        return self._build_output(context, Signal.SHORT, 0.5, ["BEAR_CASE_PENDING"])

    def _build_output(self, ctx: dict, signal: Signal, conf: float, reasons: list[str]) -> AgentOutput:
        return AgentOutput(
            symbol=ctx.get("symbol", ""), timeframe=ctx.get("timeframe", "1h"),
            signal=signal, confidence=conf, uncertainty=1-conf,
            reason_codes=reasons,
        )


class RiskAgent(BaseAgent):
    """风控 Agent — 专找交易会怎么失败"""

    def __init__(self):
        super().__init__("Risk Guardian", "risk_agent")

    def supported_states(self) -> list[SystemState]:
        return [SystemState.DEBATE, SystemState.RISK_CHECK]

    async def analyze(self, context: dict) -> AgentOutput:
        return AgentOutput(
            symbol=context.get("symbol", ""), timeframe=context.get("timeframe", "1h"),
            signal=Signal.NO_TRADE, confidence=0.3, uncertainty=0.7,
            reason_codes=["RISK_CHECK_PENDING"],
        )


class DebateCoordinator:
    """辩论协调器 — 组织 Bull vs Bear vs Risk 辩论"""

    def __init__(self, bull: BullAgent, bear: BearAgent, risk: RiskAgent):
        self.bull = bull
        self.bear = bear
        self.risk = risk

    async def debate(self, context: dict) -> dict:
        """执行三方辩论"""
        bull_result = await self.bull.analyze(context)
        bear_result = await self.bear.analyze(context)
        risk_result = await self.risk.analyze(context)

        return {
            "bull": bull_result.to_json(),
            "bear": bear_result.to_json(),
            "risk": risk_result.to_json(),
            "summary": self._summarize(bull_result, bear_result, risk_result),
        }

    def _summarize(self, bull: AgentOutput, bear: AgentOutput, risk: AgentOutput) -> dict:
        return {
            "bull_confidence": bull.confidence,
            "bear_confidence": bear.confidence,
            "risk_level": risk.confidence,
            "net_bias": bull.confidence - bear.confidence,
        }
