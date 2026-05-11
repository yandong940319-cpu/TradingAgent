"""
AI Quant Hedge Fund OS — 硬风控规则配置

所有硬编码风控参数集中管理，不经过 LLM。
这些规则在 AI 调用之前执行，且不可被 AI 输出覆盖。
"""

# ── 仓位/资金风控 ──

# 单日最大亏损（百分比，0.05 = 5%）
# 触发条件: 当日已实现亏损 > 此值
MAX_DAILY_LOSS = 0.05

# 单笔最大仓位（占总投资组合的百分比）
MAX_POSITION_SIZE = 0.20

# 最大杠杆倍数（1.0 = 无杠杆）
MAX_LEVERAGE = 1.0

# 最大连续亏损次数后强制停止
MAX_CONSECUTIVE_LOSSES = 3

# 最小交易间隔（秒）
MIN_TRADE_INTERVAL_SECONDS = 300

# ── 基于市场数据的硬规则（不依赖记忆体，直接用实时 K 线） ──

# 最大波动率阈值（ATR/Close 百分比）
# 超过此值则硬拒绝——波动过大时不开仓
MAX_VOLATILITY_PCT = 0.08  # 8%

# 价格偏离均线最大比例
# 当前价格偏离 20 周期均线超过此值则硬拒绝
MAX_PRICE_DEVIATION_MA = 0.15  # 15%

# 相对强弱阈值（基于近期涨跌幅）
# 过去 N 根 K 线的累计涨跌幅超过此值 → 极端行情，不开仓
MAX_CUMULATIVE_RETURN_PCT = 0.20  # 20%

# ── 硬规则拒绝原因码 ──

REJECT_REASONS = {
    "MAX_DAILY_LOSS": "HARD_STOP: 当日亏损超过上限",
    "MAX_POSITION_SIZE": "HARD_STOP: 仓位超过上限",
    "MAX_LEVERAGE": "HARD_STOP: 杠杆超过上限",
    "MAX_CONSECUTIVE_LOSSES": "HARD_STOP: 连续亏损次数超过上限",
    "MIN_TRADE_INTERVAL": "HARD_STOP: 交易间隔过短",
    "MAX_VOLATILITY": "HARD_STOP: 市场波动率过高",
    "PRICE_DEVIATION": "HARD_STOP: 价格偏离均线过远",
    "EXTREME_RETURN": "HARD_STOP: 近期累计涨跌幅过大",
}
