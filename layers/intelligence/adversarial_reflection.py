"""
Layer 2 — Intelligence: Adversarial & Reflection Agents

Adversarial: 找系统会怎么失败（降低 hallucination 的关键）
Reflection: 复盘错误交易，驱动进化
"""

from core.agent import BaseAgent
from core.protocols import (
    AgentOutput, Signal, SystemState,
    ReflectionOutput,
)


class AdversarialAgent(BaseAgent):
    """对抗 Agent — 职责不是赚钱，是找系统会怎么失败"""

    def __init__(self):
        super().__init__("Adversarial", "adversarial_agent")

    def supported_states(self) -> list[SystemState]:
        return [SystemState.DEBATE, SystemState.RISK_CHECK]

    async def analyze(self, context: dict) -> AgentOutput:
        """核心问题：为什么这笔交易可能失败"""
        return AgentOutput(
            symbol=context.get("symbol", ""),
            timeframe=context.get("timeframe", "1h"),
            signal=Signal.NO_TRADE,
            confidence=0.0,
            uncertainty=1.0,
            trade_allowed=False,
            reason_codes=self._find_failure_reasons(context),
        )

    def _find_failure_reasons(self, context: dict) -> list[str]:
        """查找潜在失败原因"""
        # TODO: 接入 DeepSeek 分析
        return ["ADVERSARIAL_CHECK_PENDING"]


class ReflectionAgent(BaseAgent):
    """反思 Agent — 系统长期进化核心"""

    def __init__(self):
        super().__init__("Reflection", "reflection_agent")
        self.reflection_history: list[ReflectionOutput] = []

    def supported_states(self) -> list[SystemState]:
        return [SystemState.REFLECTION]

    async def analyze(self, context: dict) -> AgentOutput:
        trade_result = context.get("trade_result", {})
        reflection = await self._reflect(trade_result)
        self.reflection_history.append(reflection)
        return AgentOutput(
            symbol=context.get("symbol", ""),
            timeframe="1h",
            signal=Signal.NEUTRAL,
            confidence=1.0 - abs(reflection.confidence_penalty),
            uncertainty=abs(reflection.confidence_penalty),
            reason_codes=[f"REFLECTION_{reflection.why_wrong}"],
            metadata={"reflection": str(reflection)},
        )

    async def _reflect(self, trade_result: dict) -> ReflectionOutput:
        """复盘错误交易"""
        # TODO: 接入 DeepSeek 进行深度复盘分析
        return ReflectionOutput(
            why_wrong="PENDING_ANALYSIS",
            confidence_penalty=0.0,
            future_weight_adjustment=0.0,
        )

    def get_adjustments(self) -> dict:
        """获取基于反思的权重调整建议"""
        if not self.reflection_history:
            return {"weight_adjustment": 0.0, "confidence_penalty": 0.0}
        avg_penalty = sum(r.confidence_penalty for r in self.reflection_history) / len(self.reflection_history)
        avg_weight = sum(r.future_weight_adjustment for r in self.reflection_history) / len(self.reflection_history)
        return {"weight_adjustment": avg_weight, "confidence_penalty": avg_penalty}
