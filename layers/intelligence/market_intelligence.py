"""
Layer 2 — Market Intelligence Agent

采集免费第三方数据源（Fear & Greed、加密新闻 RSS），
输出综合市场情绪评分，辅助 Bull/Bear/Risk Agent 的决策。

依赖: feedparser, requests (已在 requirements.txt)
数据源: alternative.me (F&G), CoinTelegraph RSS, CoinDesk RSS, Bitcoin Magazine RSS
"""

from core.agent import BaseAgent
from core.protocols import AgentOutput, Signal, SystemState, MarketRegime
from core.market_data_sources import collect_market_sentiment


class MarketIntelligenceAgent(BaseAgent):
    """
    市场情报 Agent

    职责：
    1. 采集 Fear & Greed Index（实时）
    2. 采集加密新闻头条（CoinTelegraph/CoinDesk/Bitcoin Magazine）
    3. 输出综合市场情绪评分
    4. 数据注入 context，供 Bull/Bear/Risk Agent 使用
    """

    def __init__(self):
        super().__init__("Market Intelligence", "market_intelligence")

    def supported_states(self) -> list[SystemState]:
        return [SystemState.ANALYZE]

    async def analyze(self, context: dict) -> AgentOutput:
        symbol = context.get("symbol", "BTCUSDT")
        tf = context.get("timeframe", "1h")

        # 采集所有免费数据源
        sentiment = collect_market_sentiment(symbol)

        fng = sentiment["fear_greed"]
        score = sentiment["sentiment_score"]
        news_count = sentiment["news_count"]
        confidence = sentiment["confidence"]

        # 根据情绪分数映射信号
        if score > 0.3:
            signal = Signal.LONG
            regime = self._classify_regime(score)
        elif score < -0.3:
            signal = Signal.SHORT
            regime = self._classify_regime(score)
        else:
            signal = Signal.NEUTRAL
            regime = MarketRegime.RANGING

        # 构建原因码
        reasons = [f"FNG_{fng.get('value', 50)}"]
        if news_count > 0:
            reasons.append(f"NEWS_{news_count}")

        # 提取新闻标题摘要
        headlines = sentiment.get("news_headlines", [])[:5]
        news_summary = [
            {"title": h["title"], "source": h["source"], "published": h["published"]}
            for h in headlines
        ] if headlines else []

        return AgentOutput(
            symbol=symbol,
            timeframe=tf,
            signal=signal,
            confidence=confidence,
            uncertainty=round(1 - confidence, 2),
            market_regime=regime,
            expected_volatility=self._estimate_volatility(score),
            reason_codes=reasons,
            metadata={
                "fear_greed": fng,
                "sentiment_score": score,
                "news_headlines": news_summary,
                "data_sources": ["alternative.me", "cointelegraph", "coindesk", "bitcoinmagazine"],
            },
        )

    # ────────────────────────────
    #  辅助方法
    # ────────────────────────────

    @staticmethod
    def _classify_regime(score: float) -> MarketRegime:
        """情绪分数 → 市场状态"""
        if score > 0.7:
            return MarketRegime.TRENDING_BULL
        elif score > 0.3:
            return MarketRegime.RANGING
        elif score < -0.7:
            return MarketRegime.TRENDING_BEAR
        elif score < -0.3:
            return MarketRegime.RANGING
        else:
            return MarketRegime.RANGING

    @staticmethod
    def _estimate_volatility(score: float) -> float:
        """情绪分数 → 预期波动率"""
        # 极端情绪 → 高波动
        return round(abs(score) * 0.5, 2)
