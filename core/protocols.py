"""
AI Quant Hedge Fund OS — 核心协议定义

所有 Agent 通信必须遵循此协议。
"""

from dataclasses import dataclass, field
from typing import Optional
from enum import Enum

# ── 系统状态 ──

class SystemMode(Enum):
    SAFE_MODE = "SAFE_MODE"
    RISK_OFF = "RISK_OFF"
    READ_ONLY = "READ_ONLY"
    EXECUTION_DISABLED = "EXECUTION_DISABLED"
    NORMAL = "NORMAL"

class MarketRegime(Enum):
    TRENDING_BULL = "TRENDING_BULL"
    TRENDING_BEAR = "TRENDING_BEAR"
    RANGING = "RANGING"
    HIGH_VOLATILITY = "HIGH_VOLATILITY"
    LOW_VOLATILITY = "LOW_VOLATILITY"
    CRISIS = "CRISIS"
    UNKNOWN = "UNKNOWN"

class Signal(Enum):
    LONG = "LONG"
    SHORT = "SHORT"
    NEUTRAL = "NEUTRAL"
    NO_TRADE = "NO_TRADE"

class AlphaStatus(Enum):
    BIRTH = "BIRTH"
    PEAK = "PEAK"
    DECAYING = "DECAYING"
    DEPRECATED = "DEPRECATED"
    RETIRED = "RETIRED"

# ── Agent Contract Protocol ──

@dataclass
class AgentOutput:
    """所有 Agent 的统一输出格式"""
    symbol: str
    timeframe: str
    signal: Signal
    confidence: float          # 0-1
    uncertainty: float         # 0-1
    risk_reward_ratio: float = 0.0
    market_regime: MarketRegime = MarketRegime.UNKNOWN
    expected_volatility: float = 0.0
    signal_strength: float = 0.0
    alpha_decay_score: float = 0.0
    trade_priority: int = 0    # 1-10
    trade_allowed: bool = False
    reason_codes: list[str] = field(default_factory=list)
    metadata: dict = field(default_factory=dict)

    def to_json(self) -> dict:
        return {
            "symbol": self.symbol,
            "timeframe": self.timeframe,
            "signal": self.signal.value,
            "confidence": round(self.confidence, 2),
            "uncertainty": round(self.uncertainty, 2),
            "risk_reward_ratio": round(self.risk_reward_ratio, 2),
            "market_regime": self.market_regime.value,
            "expected_volatility": round(self.expected_volatility, 2),
            "signal_strength": round(self.signal_strength, 2),
            "alpha_decay_score": round(self.alpha_decay_score, 2),
            "trade_priority": self.trade_priority,
            "trade_allowed": self.trade_allowed,
            "reason_codes": self.reason_codes,
        }


@dataclass
class ReflectionOutput:
    """Reflection Agent 的输出"""
    why_wrong: str
    timing_issue: bool = False
    strategy_degradation: bool = False
    regime_shift: bool = False
    confidence_penalty: float = 0.0
    future_weight_adjustment: float = 0.0


@dataclass
class ReliabilityMetrics:
    """AI Reliability Engineering 指标"""
    consistency_score: float = 0.0
    regime_adaptation_score: float = 0.0
    false_positive_rate: float = 0.0
    overtrading_score: float = 0.0
    panic_reaction_score: float = 0.0
    hallucination_score: float = 0.0


@dataclass
class AlphaLifecycle:
    """Alpha 生命周期"""
    alpha_id: str
    peak_sharpe: float = 0.0
    current_sharpe: float = 0.0
    decay_score: float = 0.0
    status: AlphaStatus = AlphaStatus.BIRTH


# ── 系统状态机 ──

class SystemState(Enum):
    WAIT_DATA = "WAIT_DATA"
    ANALYZE = "ANALYZE"
    DEBATE = "DEBATE"
    GENERATE_SIGNAL = "GENERATE_SIGNAL"
    RISK_CHECK = "RISK_CHECK"
    CIO_REVIEW = "CIO_REVIEW"
    EXECUTION = "EXECUTION"
    POST_ANALYSIS = "POST_ANALYSIS"
    REFLECTION = "REFLECTION"
    MEMORY_UPDATE = "MEMORY_UPDATE"
    WEIGHT_REBALANCE = "WEIGHT_REBALANCE"
    EMERGENCY_STOP = "EMERGENCY_STOP"

    def __lt__(self, other):
        if not isinstance(other, SystemState):
            return NotImplemented
        order = list(SystemState)
        return order.index(self) < order.index(other)
