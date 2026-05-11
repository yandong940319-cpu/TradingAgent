"""
AI Quant Hedge Fund OS — Tool Governance Protocol

Agent 的工具治理协议，避免 Tool Chaos。
"""

from dataclasses import dataclass
from typing import Optional


@dataclass
class ToolConfig:
    """工具配置"""
    name: str
    retry: int = 2
    timeout_ms: int = 3000
    cache_ttl: int = 30  # seconds
    rate_limit_per_min: int = 60


ALLOWED_TOOLS = {
    "market_data_api": ToolConfig("market_data_api", retry=2, timeout_ms=3000),
    "onchain_scanner": ToolConfig("onchain_scanner", retry=2, timeout_ms=5000),
    "news_engine": ToolConfig("news_engine", retry=1, timeout_ms=5000),
    "orderbook_analyzer": ToolConfig("orderbook_analyzer", retry=2, timeout_ms=2000),
    "macro_indicator": ToolConfig("macro_indicator", retry=1, timeout_ms=5000),
    "sentiment_analyzer": ToolConfig("sentiment_analyzer", retry=2, timeout_ms=4000),
    "execution_engine": ToolConfig("execution_engine", retry=1, timeout_ms=1000),
}


class ToolGovernor:
    """工具治理器 — 管理 Agent 的工具调用"""

    def __init__(self):
        self.tool_cache = {}
        self.tool_calls = {}

    def check_rate_limit(self, tool_name: str) -> bool:
        """检查是否超过速率限制"""
        config = ALLOWED_TOOLS.get(tool_name)
        if not config:
            return False
        if tool_name not in self.tool_calls:
            self.tool_calls[tool_name] = []
        # 简化实现：实际应基于时间窗口
        return len(self.tool_calls[tool_name]) < config.rate_limit_per_min

    def get_tool(self, tool_name: str) -> Optional[ToolConfig]:
        """获取工具配置"""
        return ALLOWED_TOOLS.get(tool_name)

    def is_allowed(self, tool_name: str, agent_name: str) -> bool:
        """检查 Agent 是否有权使用此工具"""
        tool = self.get_tool(tool_name)
        if not tool:
            return False
        # 工具可用性检查
        return True
