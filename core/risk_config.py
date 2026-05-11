"""
AI Quant Hedge Fund OS — 硬风控规则配置

所有硬编码风控参数集中管理，不经过 LLM。
"""

# 单日最大亏损（百分比，0.05 = 5%）
MAX_DAILY_LOSS = 0.05

# 单笔最大仓位（占总投资组合的百分比）
MAX_POSITION_SIZE = 0.20

# 最大杠杆倍数（1.0 = 无杠杆）
MAX_LEVERAGE = 1.0

# 最大连续亏损次数后强制停止
MAX_CONSECUTIVE_LOSSES = 3

# 最小交易间隔（秒）
MIN_TRADE_INTERVAL_SECONDS = 300

# 硬规则拒绝原因码
REJECT_REASONS = {
    "MAX_DAILY_LOSS": "单日亏损超过上限，硬规则拒绝",
    "MAX_POSITION_SIZE": "仓位超过上限，硬规则拒绝",
    "MAX_LEVERAGE": "杠杆超过上限，硬规则拒绝",
    "MAX_CONSECUTIVE_LOSSES": "连续亏损次数超过上限，硬规则拒绝",
    "MIN_TRADE_INTERVAL": "交易间隔过短，硬规则拒绝",
}
