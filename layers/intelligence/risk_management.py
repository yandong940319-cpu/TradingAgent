"""
Layer 2 — Risk Management Agent

风控检查，两层结构：
  1. 硬规则层（先于任何 LLM，直接拒绝）
  2. AI 风控层（仅当硬规则通过时执行）
"""

from core.agent import BaseAgent
from core.protocols import AgentOutput, Signal, SystemState
from core.risk_config import (
    MAX_DAILY_LOSS, MAX_POSITION_SIZE, MAX_LEVERAGE,
    MAX_CONSECUTIVE_LOSSES, MIN_TRADE_INTERVAL_SECONDS,
    REJECT_REASONS,
)


class RiskManagementAgent(BaseAgent):
    """风险管理 Agent — 硬规则 + AI 双层风控"""

    def __init__(self):
        super().__init__("Risk Manager", "risk_manager")
        self.max_daily_loss = MAX_DAILY_LOSS
        self.max_position_size = MAX_POSITION_SIZE
        self.max_leverage = MAX_LEVERAGE
        self.max_consecutive_losses = MAX_CONSECUTIVE_LOSSES
        self.min_trade_interval = MIN_TRADE_INTERVAL_SECONDS

    def supported_states(self) -> list[SystemState]:
        return [SystemState.RISK_CHECK]

    async def analyze(self, context: dict) -> AgentOutput:
        signal = context.get("signal", {})

        # ── Step 1: 硬规则检查（不经过任何 LLM） ──
        hard_veto = self._check_hard_rules(context)
        if hard_veto:
            return AgentOutput(
                symbol=context.get("symbol", ""),
                timeframe=context.get("timeframe", "1h"),
                signal=Signal.NO_TRADE,
                confidence=1.0,
                uncertainty=0.0,
                trade_allowed=False,
                reason_codes=[hard_veto],
            )

        # ── Step 2: AI 风控检查（仅硬规则通过时） ──
        return AgentOutput(
            symbol=context.get("symbol", ""),
            timeframe=context.get("timeframe", "1h"),
            signal=Signal.NO_TRADE,
            confidence=0.8,
            uncertainty=0.2,
            trade_allowed=self._check_ai_risk(context),
            reason_codes=self._get_reasons(context),
        )

    # ────────────────────────────────────────────
    #  硬规则（不经过 LLM，直接拒绝）
    # ────────────────────────────────────────────

    def _check_hard_rules(self, context: dict) -> str | None:
        """
        逐条检查所有硬规则。
        返回 None = 通过，返回 str = 拒绝原因码。
        """
        # 1. 单日最大亏损
        daily_pnl = context.get("daily_pnl", 0.0)
        if daily_pnl < -self.max_daily_loss:
            return "MAX_DAILY_LOSS"

        # 2. 单笔最大仓位
        proposed_size = context.get("proposed_position_size", 0.0)
        if proposed_size > self.max_position_size:
            return "MAX_POSITION_SIZE"

        # 3. 最大杠杆
        leverage = context.get("leverage", 0.0)
        if leverage > self.max_leverage:
            return "MAX_LEVERAGE"

        # 4. 连续亏损次数
        consecutive_losses = context.get("consecutive_losses", 0)
        if consecutive_losses >= self.max_consecutive_losses:
            return "MAX_CONSECUTIVE_LOSSES"

        # 5. 最小交易间隔
        last_trade_time = context.get("last_trade_time", 0)
        import time
        if last_trade_time > 0 and (time.time() - last_trade_time) < self.min_trade_interval:
            return "MIN_TRADE_INTERVAL"

        return None  # 所有硬规则通过

    # ────────────────────────────────────────────
    #  AI 风控（仅硬规则通过时执行）
    # ────────────────────────────────────────────

    def _check_ai_risk(self, context: dict) -> bool:
        """
        AI 风控检查。如果硬规则已通过，进一步评估 AI 建议的 veto。
        """
        risk = context.get("risk_analysis", {})
        ai_veto = risk.get("veto", False)
        return not ai_veto

    def _get_reasons(self, context: dict) -> list[str]:
        reasons = []
        risk = context.get("risk_analysis", {})
        ai_veto = risk.get("veto", False)
        if ai_veto:
            reasons.append("AI_VETO")
        else:
            reasons.append("HARD_RULES_PASSED")
        return reasons or ["RISK_PASSED"]
