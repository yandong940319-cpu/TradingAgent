"""
AI Quant Hedge Fund OS — 主入口

系统启动和编排。
"""

import asyncio
import json
import sys
import os
from pathlib import Path
from datetime import datetime

# 添加项目根目录到路径
sys.path.insert(0, str(Path(__file__).parent))

from core.engine import OrchestrationEngine
from core.protocols import SystemState, SystemMode

# Layer 1 — Data
from layers.data.orchestrator import DataOrchestrator
from layers.data.binance_data import BinanceDataAgent
from layers.data.ashare_data import AShareDataAgent
from layers.data.usstock_data import USStockDataAgent

# Layer 2 - Intelligence
from layers.intelligence.regime_detection import RegimeDetectionAgent
from layers.intelligence.debate import BullAgent, BearAgent, RiskAgent, DebateCoordinator
from layers.intelligence.adversarial_reflection import AdversarialAgent, ReflectionAgent
from layers.intelligence.risk_management import RiskManagementAgent
from layers.intelligence.portfolio_manager import PortfolioManagerAgent

# Layer 3 - Governance
from layers.governance.cio import CIOAgent
from layers.governance.killswitch_reliability import KillSwitch, ReliabilityEngine
from layers.governance.alpha_lifecycle import AlphaLifecycleEngine

# Layer 4 - Execution
from layers.execution.execution_agents import (
    SmartExecutionAgent, SlippageSimulationAgent,
    LiquidityAnalyzer, ExchangeHealthMonitor,
)


class AIQuantFundOS:
    """AI Quant Hedge Fund Operating System"""

    def __init__(self, config_path: str = None):
        self.config = self._load_config(config_path)
        self.engine = OrchestrationEngine(self.config)
        self.kill_switch = KillSwitch()
        self.reliability = ReliabilityEngine()
        self.alpha_lifecycle = AlphaLifecycleEngine()

        # Layer 1 — 数据层
        binance_key = os.getenv("BINANCE_API_KEY", "")
        binance_secret = os.getenv("BINANCE_API_SECRET", "")
        self.data_orchestrator = DataOrchestrator(binance_key, binance_secret)

        # 初始化 Agents
        self._init_agents()

    def _load_config(self, path: str = None) -> dict:
        default_config = {
            "system": {
                "name": "AI Quant Hedge Fund OS",
                "version": "1.0.0",
                "default_timeframe": "1h",
            },
            "risk": {
                "max_daily_loss": 0.05,
                "max_position_size": 0.2,
                "max_leverage": 1.0,
            },
        }
        if path and Path(path).exists():
            with open(path) as f:
                default_config.update(json.load(f))
        return default_config

    def _init_agents(self):
        """注册所有 Agent 到编排引擎"""

        # Layer 2 — Intelligence
        self.engine.register_agent(RegimeDetectionAgent())
        self.engine.register_agent(BullAgent())
        self.engine.register_agent(BearAgent())
        self.engine.register_agent(RiskAgent())
        self.engine.register_agent(AdversarialAgent())
        self.engine.register_agent(ReflectionAgent())
        self.engine.register_agent(RiskManagementAgent())
        self.engine.register_agent(PortfolioManagerAgent())

        # Layer 3 — Governance (CIO)
        self.engine.set_cio(CIOAgent())

        # Layer 4 — Execution
        self.engine.register_agent(SmartExecutionAgent())
        self.engine.register_agent(SlippageSimulationAgent())
        self.engine.register_agent(LiquidityAnalyzer())
        self.engine.register_agent(ExchangeHealthMonitor())

    async def analyze(self, symbol: str, timeframe: str = "1h") -> dict:
        """分析一个标的"""
        # 先检查熔断状态
        mode = self.kill_switch.check_triggers({"volatility": 0.3, "api_healthy": True})
        if mode != SystemMode.NORMAL:
            return {"error": f"SYSTEM_IN_{mode.value}"}

        # 采集数据
        data = await self.data_orchestrator.collect(symbol, timeframe)
        self.engine.current_context = data

        # 执行流水线
        result = await self.engine.run_pipeline(symbol, timeframe)
        result["data"] = data
        return result

    async def quick_data(self, symbol: str, timeframe: str = "1h") -> dict:
        """仅采集数据，不执行分析流水线"""
        return await self.data_orchestrator.collect(symbol, timeframe)

    def get_system_status(self) -> dict:
        return {
            "mode": self.kill_switch.mode.value,
            "state": self.engine.state_machine.get_status(),
            "health": self.reliability.get_system_health(),
            "agents": {aid: agent.to_dict() for aid, agent in self.engine.agents.items()},
            "alpha_count": len(self.alpha_lifecycle.alphas),
        }

    def emergency_stop(self):
        """紧急停止"""
        self.kill_switch._activate(SystemMode.SAFE_MODE, "MANUAL_TRIGGER")
        self.engine.emergency_stop()


async def main():
    """系统入口"""
    os = AIQuantFundOS()

    print("=" * 60)
    print("  AI Quant Hedge Fund Operating System")
    print("  v1.0.0 — Survival First")
    print("=" * 60)
    print()

    # 展示系统状态
    status = os.get_system_status()
    print(f"System Mode: {status['mode']}")
    print(f"Active Agents: {len(status['agents'])}")
    print(f"Agent List:")
    for aid, info in status['agents'].items():
        print(f"  - {info['name']} ({aid}): rel={info['reliability']}")

    print()
    print("System initialized. Ready for analysis.")
    print()


if __name__ == "__main__":
    asyncio.run(main())
