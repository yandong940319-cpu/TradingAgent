"""
AI Quant Hedge Fund OS — 系统状态机

管理 Agent 协作的生命周期流转。
"""

from enum import Enum
from datetime import datetime
from typing import Optional
from core.protocols import SystemState, SystemMode


class StateMachine:
    """系统状态机 — 管理 Agent 协作流程"""

    def __init__(self):
        self.current_state = SystemState.WAIT_DATA
        self.previous_state: Optional[SystemState] = None
        self.system_mode = SystemMode.NORMAL
        self.state_history: list[dict] = []
        self.error_count = 0
        self.max_errors_before_stop = 3

    def transition(self, target_state: SystemState) -> bool:
        """尝试状态转换"""
        if not self._can_transition(target_state):
            return False

        self.previous_state = self.current_state
        self.current_state = target_state
        self.state_history.append({
            "from": self.previous_state.value if self.previous_state else None,
            "to": self.current_state.value,
            "timestamp": datetime.now().isoformat(),
        })
        return True

    def _can_transition(self, target: SystemState) -> bool:
        """检查是否可以转换到目标状态"""
        transitions = {
            SystemState.WAIT_DATA: [SystemState.ANALYZE],
            SystemState.ANALYZE: [SystemState.DEBATE],
            SystemState.DEBATE: [SystemState.GENERATE_SIGNAL],
            SystemState.GENERATE_SIGNAL: [SystemState.RISK_CHECK],
            SystemState.RISK_CHECK: [SystemState.CIO_REVIEW, SystemState.WAIT_DATA],
            SystemState.CIO_REVIEW: [SystemState.EXECUTION, SystemState.WAIT_DATA],
            SystemState.EXECUTION: [SystemState.POST_ANALYSIS],
            SystemState.POST_ANALYSIS: [SystemState.REFLECTION],
            SystemState.REFLECTION: [SystemState.MEMORY_UPDATE],
            SystemState.MEMORY_UPDATE: [SystemState.WEIGHT_REBALANCE],
            SystemState.WEIGHT_REBALANCE: [SystemState.WAIT_DATA],
            SystemState.EMERGENCY_STOP: [SystemState.WAIT_DATA],
        }
        return target in transitions.get(self.current_state, [])

    def emergency_stop(self):
        """紧急停止系统"""
        self.system_mode = SystemMode.SAFE_MODE
        self.transition(SystemState.EMERGENCY_STOP)

    def record_error(self):
        """记录错误，触发应急机制"""
        self.error_count += 1
        if self.error_count >= self.max_errors_before_stop:
            self.emergency_stop()

    def get_status(self) -> dict:
        return {
            "current_state": self.current_state.value,
            "system_mode": self.system_mode.value,
            "error_count": self.error_count,
            "total_transitions": len(self.state_history),
        }
