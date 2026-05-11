"""
Layer 1 — Data: A股数据源 (Baostock + akshare)

负责 A 股日线/分钟线、资金流向、情绪指标。
"""

import pandas as pd
from datetime import datetime, timedelta

from core.agent import BaseAgent
from core.protocols import AgentOutput, Signal, SystemState


class AShareDataAgent(BaseAgent):
    """A股数据采集 Agent"""

    def __init__(self):
        super().__init__("A-Share Data", "ashare_data")
        self._bs_connected = False

    def supported_states(self) -> list[SystemState]:
        return [SystemState.WAIT_DATA, SystemState.ANALYZE]

    def _ensure_login(self):
        if not self._bs_connected:
            import baostock as bs
            lg = bs.login()
            self._bs_connected = lg.error_code == "0"

    async def analyze(self, context: dict) -> AgentOutput:
        symbol = context.get("symbol", "sh.600000")
        tf = context.get("timeframe", "d")

        klines = self.get_klines(symbol, tf)

        if not klines:
            return AgentOutput(
                symbol=symbol, timeframe=tf,
                signal=Signal.NO_TRADE, confidence=0, uncertainty=1,
                reason_codes=["ASHARE_DATA_FAILED"],
            )

        return AgentOutput(
            symbol=symbol, timeframe=tf,
            signal=Signal.NEUTRAL,
            confidence=0.8,
            uncertainty=0.2,
            reason_codes=["DATA_READY"],
            metadata={
                "klines_count": len(klines),
                "recent_data": klines[-5:] if len(klines) >= 5 else klines,
            },
        )

    def get_klines(self, symbol: str, timeframe: str = "d",
                   count: int = 100) -> list[dict]:
        """
        获取A股K线
        symbol格式: sh.600000 / sz.000001
        timeframe: d=日线, w=周, m=月, 5=5分钟, 15=15分钟
        """
        self._ensure_login()
        import baostock as bs

        # Baostock 时间格式
        end_date = datetime.now().strftime("%Y-%m-%d")
        start_date = (datetime.now() - timedelta(days=count * 2)).strftime("%Y-%m-%d")

        freq_map = {"d": "d", "w": "w", "m": "m", "5": "5", "15": "15"}
        freq = freq_map.get(timeframe, "d")

        try:
            rs = bs.query_history_k_data_plus(
                symbol,
                "date,open,high,low,close,volume,amount,turn",
                start_date=start_date, end_date=end_date,
                frequency=freq, adjustflag="2"  # 后复权
            )
            rows = []
            while rs.next():
                row = rs.get_row_data()
                if row[0]:  # 有日期
                    rows.append({
                        "date": row[0], "open": float(row[1]), "high": float(row[2]),
                        "low": float(row[3]), "close": float(row[4]),
                        "volume": float(row[5]), "amount": float(row[6]),
                        "turnover": float(row[7]) if row[7] else 0,
                    })
            return rows[-count:]
        except Exception as e:
            print(f"[AShareData] Error: {e}")
            return []

    def __del__(self):
        if self._bs_connected:
            import baostock as bs
            bs.logout()
