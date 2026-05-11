"""
Layer 3 — Governance: Kill Switch & Reliability Engine

全局熔断和安全机制。
"""

from datetime import datetime, timedelta
from typing import Optional
from core.protocols import SystemMode, ReliabilityMetrics
from core.state_machine import SystemState


class KillSwitch:
    """全局熔断系统"""

    def __init__(self):
        self.mode = SystemMode.NORMAL
        self.triggers: list[dict] = []
        self.consecutive_losses = 0
        self.max_consecutive_losses = 3
        self.daily_loss_limit = 0.05  # 5%

    def check_triggers(self, market_data: dict) -> SystemMode:
        """检查是否触发熔断条件"""
        # 黑天鹅检测
        if self._is_black_swan(market_data):
            return self._activate(SystemMode.SAFE_MODE, "BLACK_SWAN")

        # 连续亏损
        if self.consecutive_losses >= self.max_consecutive_losses:
            return self._activate(SystemMode.RISK_OFF, "CONSECUTIVE_LOSSES")

        # API 异常
        if not market_data.get("api_healthy", True):
            return self._activate(SystemMode.READ_ONLY, "API_ANOMALY")

        # 极端波动
        if market_data.get("volatility", 0) > 0.8:
            return self._activate(SystemMode.EXECUTION_DISABLED, "EXTREME_VOLATILITY")

        return SystemMode.NORMAL

    def _is_black_swan(self, data: dict) -> bool:
        """黑天鹅事件检测"""
        return data.get("black_swan", False)

    def _activate(self, mode: SystemMode, reason: str) -> SystemMode:
        self.mode = mode
        self.triggers.append({
            "mode": mode.value,
            "reason": reason,
            "timestamp": datetime.now().isoformat(),
        })
        return mode

    def record_loss(self, amount: float):
        """记录亏损"""
        self.consecutive_losses += 1

    def reset(self):
        """重置熔断状态"""
        self.consecutive_losses = 0
        self.mode = SystemMode.NORMAL


class ReliabilityEngine:
    """AI Reliability Engineering — 可靠性引擎"""

    def __init__(self):
        self.metrics = ReliabilityMetrics()
        self.agent_scores: dict[str, ReliabilityMetrics] = {}
        self.long_term_stability: list[float] = []

    def update_agent_score(self, agent_id: str, success: bool):
        """更新 Agent 可靠性评分"""
        if agent_id not in self.agent_scores:
            self.agent_scores[agent_id] = ReliabilityMetrics()

        score = self.agent_scores[agent_id]
        if success:
            score.consistency_score = min(1.0, score.consistency_score + 0.05)
        else:
            score.consistency_score = max(0, score.consistency_score - 0.1)

    def get_agent_reliability(self, agent_id: str) -> float:
        """获取 Agent 的可靠性评分"""
        score = self.agent_scores.get(agent_id)
        return score.consistency_score if score else 0.5

    def get_system_health(self) -> dict:
        return {
            "avg_consistency": sum(s.consistency_score for s in self.agent_scores.values()) / max(1, len(self.agent_scores)),
            "active_agents": len(self.agent_scores),
        }
