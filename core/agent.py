"""
AI Quant Hedge Fund OS — Agent 基类

所有 Agent 继承此基类，实现统一协议。
"""

from abc import ABC, abstractmethod
from typing import Optional
from datetime import datetime
from core.protocols import AgentOutput, SystemState


class BaseAgent(ABC):
    """所有 Agent 的基类"""

    def __init__(self, name: str, agent_id: str, config: dict = None):
        self.name = name
        self.agent_id = agent_id
        self.config = config or {}
        self.reliability_score = 1.0
        self.total_calls = 0
        self.successful_calls = 0
        self.last_output: Optional[AgentOutput] = None
        self.created_at = datetime.now()

    @abstractmethod
    async def analyze(self, context: dict) -> AgentOutput:
        """分析市场数据并返回 Agent 输出"""
        ...

    @abstractmethod
    def supported_states(self) -> list[SystemState]:
        """该 Agent 支持的系统状态列表"""
        ...

    def update_reliability(self, success: bool):
        """更新可靠性评分"""
        self.total_calls += 1
        if success:
            self.successful_calls += 1
        self.reliability_score = self.successful_calls / max(1, self.total_calls)

    def to_dict(self) -> dict:
        return {
            "name": self.name,
            "agent_id": self.agent_id,
            "reliability": round(self.reliability_score, 2),
            "total_calls": self.total_calls,
            "created_at": self.created_at.isoformat(),
        }
