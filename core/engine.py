"""
AI Quant Hedge Fund OS — 核心编排引擎

协调所有 Agent 的生命周期执行。
"""

import asyncio
from typing import Optional
from datetime import datetime

from core.protocols import SystemState, SystemMode, AgentOutput, Signal
from core.state_machine import StateMachine
from core.agent import BaseAgent
from core.tool_governance import ToolGovernor
from memory.memory_store import MemoryStore


class OrchestrationEngine:
    """系统核心编排引擎"""

    def __init__(self, config: dict = None):
        self.config = config or {}
        self.state_machine = StateMachine()
        self.memory = MemoryStore()
        self.tool_governor = ToolGovernor()
        self.agents: dict[str, BaseAgent] = {}
        self.current_context: dict = {}
        self.cio: Optional[BaseAgent] = None
        self.kill_switch_active = False

    def register_agent(self, agent: BaseAgent):
        """注册一个 Agent 到系统"""
        self.agents[agent.agent_id] = agent

    def set_cio(self, agent: BaseAgent):
        """设置 CIO Agent"""
        self.cio = agent
        self.register_agent(agent)

    async def run_pipeline(self, symbol: str, timeframe: str) -> dict:
        """执行一次完整的分析-决策流水线"""
        if self.kill_switch_active:
            return {"error": "KILL_SWITCH_ACTIVE", "mode": self.state_machine.system_mode.value}

        self.current_context = {"symbol": symbol, "timeframe": timeframe}

        # 1. WAIT_DATA → 收集数据
        self.state_machine.transition(SystemState.WAIT_DATA)
        data = await self._collect_data(symbol, timeframe)

        # 2. ANALYZE → 分析
        self.state_machine.transition(SystemState.ANALYZE)
        analysis = await self._run_analysis(data)

        # 3. DEBATE → 多方辩论
        self.state_machine.transition(SystemState.DEBATE)
        debate_result = await self._run_debate(data)

        # 4. GENERATE_SIGNAL → 生成信号
        self.state_machine.transition(SystemState.GENERATE_SIGNAL)
        signal = await self._generate_signal(analysis, debate_result)

        # 5. RISK_CHECK → 风控检查
        self.state_machine.transition(SystemState.RISK_CHECK)
        risk_result = await self._risk_check(signal)

        if not risk_result.get("trade_allowed", False):
            self.state_machine.transition(SystemState.WAIT_DATA)
            return {"signal": "NO_TRADE", "reason": risk_result.get("reason", "RISK_REJECTED")}

        # 6. CIO_REVIEW → CIO 仲裁
        self.state_machine.transition(SystemState.CIO_REVIEW)
        final_decision = await self._cio_review(signal, risk_result)
        if not final_decision.get("approved", False):
            return {"signal": "NO_TRADE", "reason": "CIO_REJECTED", "details": final_decision}

        # 7. EXECUTION → 执行
        self.state_machine.transition(SystemState.EXECUTION)
        execution_result = await self._execute(final_decision)

        # 8. POST_ANALYSIS → 后分析
        self.state_machine.transition(SystemState.POST_ANALYSIS)
        await self._post_analysis(execution_result)

        # 9. REFLECTION → 反思
        self.state_machine.transition(SystemState.REFLECTION)
        await self._run_reflection(execution_result)

        # 10. MEMORY_UPDATE → 记忆更新
        self.state_machine.transition(SystemState.MEMORY_UPDATE)
        await self._update_memory(execution_result)

        # 11. WEIGHT_REBALANCE → 权重再平衡
        self.state_machine.transition(SystemState.WEIGHT_REBALANCE)
        await self._rebalance_weights()

        # 回到等待
        self.state_machine.transition(SystemState.WAIT_DATA)

        return {
            "signal": final_decision.get("signal", "NO_TRADE"),
            "confidence": final_decision.get("confidence", 0),
            "state": self.state_machine.get_status(),
        }

    async def _collect_data(self, symbol: str, timeframe: str) -> dict:
        """Layer 1: 数据采集"""
        data = {"symbol": symbol, "timeframe": timeframe, "timestamp": datetime.now().isoformat()}
        for aid, agent in self.agents.items():
            if "data" in aid.lower():
                try:
                    result = await agent.analyze({"symbol": symbol, "timeframe": timeframe})
                    data[aid] = result.to_json() if hasattr(result, 'to_json') else str(result)
                except Exception as e:
                    data[aid] = {"error": str(e)}
        return data

    async def _run_analysis(self, data: dict) -> dict:
        return {"status": "analyzed", "data_points": len(data)}

    async def _run_debate(self, data: dict) -> dict:
        return {"bull_case": {}, "bear_case": {}, "risk_case": {}}

    async def _generate_signal(self, analysis: dict, debate: dict) -> AgentOutput:
        return AgentOutput(
            symbol=self.current_context.get("symbol", ""),
            timeframe=self.current_context.get("timeframe", ""),
            signal=Signal.NO_TRADE,
            confidence=0.0,
            uncertainty=1.0,
        )

    async def _risk_check(self, signal: AgentOutput) -> dict:
        return {"trade_allowed": True, "risk_score": 0.5}

    async def _cio_review(self, signal: AgentOutput, risk: dict) -> dict:
        return {"approved": True, "signal": signal.signal.value, "confidence": signal.confidence}

    async def _execute(self, decision: dict) -> dict:
        return {"executed": True, "timestamp": datetime.now().isoformat()}

    async def _post_analysis(self, result: dict) -> None:
        pass

    async def _run_reflection(self, result: dict) -> None:
        pass

    async def _update_memory(self, result: dict) -> None:
        pass

    async def _rebalance_weights(self) -> None:
        pass

    def emergency_stop(self):
        """紧急停止"""
        self.kill_switch_active = True
        self.state_machine.emergency_stop()

    def resume(self):
        """恢复系统"""
        self.kill_switch_active = False
        self.state_machine.system_mode = SystemMode.NORMAL
