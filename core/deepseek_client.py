"""
AI Quant Fund OS — DeepSeek API 客户端

统一 AI 调用接口，所有 Agent 通过此模块调用 DeepSeek。
"""

import json
import os
from pathlib import Path
from typing import Optional
import requests


class DeepSeekClient:
    """DeepSeek API 客户端"""

    def __init__(self, api_key: str = None, base_url: str = "https://api.deepseek.com"):
        self.api_key = api_key or self._load_key()
        self.base_url = base_url
        self.model = "deepseek-chat"

    def _load_key(self) -> str:
        """从 .env 加载 API Key"""
        env_path = Path.home() / ".hermes" / ".env"
        if env_path.exists():
            with open(env_path) as f:
                for line in f:
                    line = line.strip()
                    if line.startswith("DEEPSEEK_API_KEY="):
                        return line.split("=", 1)[1].strip().strip('"').strip("'")
        # 环境变量兜底
        return os.getenv("DEEPSEEK_API_KEY", "")

    def chat(self, messages: list, temperature: float = 0.3,
             max_tokens: int = 1000) -> Optional[str]:
        """调用 DeepSeek Chat"""
        if not self.api_key:
            return None

        try:
            resp = requests.post(
                f"{self.base_url}/v1/chat/completions",
                headers={
                    "Authorization": f"Bearer {self.api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": self.model,
                    "messages": messages,
                    "temperature": temperature,
                    "max_tokens": max_tokens,
                },
                timeout=30,
            )
            if resp.status_code == 200:
                return resp.json()["choices"][0]["message"]["content"]
            else:
                print(f"[DeepSeek] API Error {resp.status_code}: {resp.text[:200]}")
                return None
        except Exception as e:
            print(f"[DeepSeek] Request failed: {e}")
            return None

    def analyze_regime(self, market_data: str) -> dict:
        """分析市场状态"""
        prompt = f"""分析以下市场数据，判断当前市场状态。
返回 JSON 格式（不要任何其他文字）：
{{"regime": "TRENDING_BULL/TRENDING_BEAR/RANGING/HIGH_VOLATILITY/CRISIS", "confidence": 0.0~1.0, "reason": "简短原因"}}

市场数据：
{market_data}
"""
        result = self.chat([
            {"role": "system", "content": "你是一个专业市场状态分析师。只返回JSON，不要其他文字。"},
            {"role": "user", "content": prompt},
        ], temperature=0.2)
        return self._parse_json(result, {"regime": "UNKNOWN", "confidence": 0.5, "reason": "API_FAILED"})

    def debate_bull(self, market_data: str) -> dict:
        """多方分析"""
        result = self.chat([
            {"role": "system", "content": "你是多方分析师，专门找做多理由。只返回JSON。"},
            {"role": "user", "content": f"""分析以下数据，找做多理由。
返回 JSON:
{{"signal": "LONG/NO_TRADE", "confidence": 0.0~1.0, "arguments": ["理由1","理由2"], "key_level": "关键价位"}}

数据：{market_data}
"""},
        ], temperature=0.3)
        return self._parse_json(result, {"signal": "NO_TRADE", "confidence": 0, "arguments": []})

    def debate_bear(self, market_data: str) -> dict:
        """空方分析"""
        result = self.chat([
            {"role": "system", "content": "你是空方分析师，专门找做空理由。只返回JSON。"},
            {"role": "user", "content": f"""分析以下数据，找做空理由。
返回 JSON:
{{"signal": "SHORT/NO_TRADE", "confidence": 0.0~1.0, "arguments": ["理由1","理由2"], "key_level": "关键价位"}}

数据：{market_data}
"""},
        ], temperature=0.3)
        return self._parse_json(result, {"signal": "NO_TRADE", "confidence": 0, "arguments": []})

    def analyze_risk(self, market_data: str) -> dict:
        """风险评估"""
        result = self.chat([
            {"role": "system", "content": "你是风控分析师，专门评估交易风险。只返回JSON。"},
            {"role": "user", "content": f"""评估以下数据的交易风险。
返回 JSON:
{{"risk_level": 0.0~1.0, "veto": true/false, "concerns": ["风险1","风险2"], "suggestion": "建议"}}

数据：{market_data}
"""},
        ], temperature=0.3)
        return self._parse_json(result, {"risk_level": 0.5, "veto": False, "concerns": []})

    def cio_decision(self, bull_analysis: dict, bear_analysis: dict,
                     risk_analysis: dict, regime: dict) -> dict:
        """CIO 最终决策"""
        context = f"""
多方分析: {json.dumps(bull_analysis, ensure_ascii=False)}
空方分析: {json.dumps(bear_analysis, ensure_ascii=False)}
风险评估: {json.dumps(risk_analysis, ensure_ascii=False)}
市场状态: {json.dumps(regime, ensure_ascii=False)}
"""
        result = self.chat([
            {"role": "system", "content": "你是CIO，做最终交易决策。只返回JSON。"},
            {"role": "user", "content": f"""基于以下多方、空方、风控、市场状态的分析，做最终决策。
返回 JSON:
{{"decision": "LONG/SHORT/NO_TRADE", "confidence": 0.0~1.0, "rationale": "决策理由", "position_size": "轻仓/半仓/重仓"}}

分析数据：
{context}
"""},
        ], temperature=0.2)
        return self._parse_json(result, {"decision": "NO_TRADE", "confidence": 0, "rationale": "API_FAILED", "position_size": "空仓"})

    def scan_signal(self, symbol: str, klines_summary: str, n_klines: int = 20) -> dict:
        """扫描信号（供 scanner / 回测使用）"""
        system_prompt = """你是一个严格的量化交易信号过滤器。

核心原则：
- 宁可不交易，不可乱交易
- 没有强烈确信就输出 NO_TRADE
- 只在满足全部条件时才输出 LONG 或 SHORT

输出 LONG 的条件（必须全部满足）：
1. 近期收盘价连续高于前5根均值
2. 成交量有放大迹象（近3根 > 前10根均量）
3. 无明显顶部形态（非连续大阳线后高位横盘）
4. confidence >= 0.65

输出 SHORT 的条件（必须全部满足）：
1. 近期收盘价连续低于前5根均值
2. 成交量有放大迹象
3. 无明显底部形态
4. confidence >= 0.65

其余所有情况输出 NO_TRADE。

只返回 JSON，不要任何解释文字。"""

        result = self.chat([
            {"role": "system", "content": system_prompt},
            {"role": "user", "content": f"""分析 {symbol} 最近 {n_klines} 根日线K线，判断当前是否有交易机会。

K线数据（从旧到新）：
{klines_summary}

必须返回以下格式：
{{"signal": "LONG/SHORT/NO_TRADE",
  "confidence": 0.0~1.0,
  "reason": "一句话说明核心理由",
  "regime": "BULL/BEAR/RANGING",
  "key_level": "关键价位"}}

再次强调：不确定就返回 NO_TRADE。"""},
        ], temperature=0.2, max_tokens=500)
        return self._parse_json(result, {"signal": "NO_TRADE", "confidence": 0, "reason": "API_FAILED"})

    def _parse_json(self, text: Optional[str], default: dict) -> dict:
        """解析 JSON 响应"""
        if not text:
            return default
        try:
            # 尝试提取 JSON 块
            if "```json" in text:
                text = text.split("```json")[1].split("```")[0]
            elif "```" in text:
                text = text.split("```")[1].split("```")[0]
            return json.loads(text.strip())
        except:
            try:
                return json.loads(text)
            except:
                return default
