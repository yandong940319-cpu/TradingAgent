"""
layers/intelligence/multi_tf_signal.py
多时间框架交易信号指标
输出: LONG / SHORT / NO_TRADE
"""

import pandas as pd
import numpy as np
from dataclasses import dataclass
from typing import Literal, Optional


@dataclass
class SignalResult:
    signal: str        # LONG / SHORT / NO_TRADE
    confidence: float
    trigger_type: str
    trend_state: str
    structure_signal: str
    entry_trigger: str
    reason: str

    def to_dict(self):
        return {
            "signal": self.signal,
            "confidence": self.confidence,
            "trigger_type": self.trigger_type,
            "trend_state": self.trend_state,
            "structure_signal": self.structure_signal,
            "entry_trigger": self.entry_trigger,
            "reason": self.reason,
        }


def klines_to_df(klines: list) -> pd.DataFrame:
    """把get_klines()返回的list[dict]转成DataFrame"""
    if not klines:
        return pd.DataFrame()
    df = pd.DataFrame(klines)
    for col in ["open", "high", "low", "close", "volume"]:
        df[col] = pd.to_numeric(df[col], errors="coerce")
    df["time"] = pd.to_numeric(df["time"], errors="coerce")
    df = df.sort_values("time").reset_index(drop=True)
    return df


def resample_to_3day(df_daily: pd.DataFrame) -> pd.DataFrame:
    """把日线DataFrame resample成3日线"""
    if df_daily.empty:
        return df_daily
    df = df_daily.copy()
    df["dt"] = pd.to_datetime(df["time"], unit="ms")
    df = df.set_index("dt")
    df_3d = df.resample("3D").agg({
        "open": "first",
        "high": "max",
        "low": "min",
        "close": "last",
        "volume": "sum",
        "time": "first",
    }).dropna().reset_index(drop=True)
    return df_3d


def compute_ema(series: pd.Series, period: int) -> pd.Series:
    return series.ewm(span=period, adjust=False).mean()


def detect_trend(df: pd.DataFrame) -> str:
    """EMA13 vs EMA34判断趋势，返回 BULL/BEAR/FLAT"""
    if len(df) < 34:
        return "FLAT"
    ema13 = compute_ema(df["close"], 13)
    ema34 = compute_ema(df["close"], 34)
    last13, last34 = ema13.iloc[-1], ema34.iloc[-1]
    prev13, prev34 = ema13.iloc[-3], ema34.iloc[-3]
    above = last13 > last34
    momentum = (last13 - prev13) - (last34 - prev34)
    if above and momentum > 0:
        return "BULL"
    elif not above and momentum < 0:
        return "BEAR"
    return "FLAT"


def get_trend_state(df_weekly: pd.DataFrame, df_3day: pd.DataFrame) -> str:
    """综合周线+3日线，返回 BULL/BEAR/MIXED/FLAT"""
    tw = detect_trend(df_weekly)
    t3 = detect_trend(df_3day)
    if tw == "BULL" and t3 == "BULL":
        return "BULL"
    if tw == "BEAR" and t3 == "BEAR":
        return "BEAR"
    if tw == "FLAT" and t3 == "FLAT":
        return "FLAT"
    return "MIXED"


def find_pivot_levels(df: pd.DataFrame, window: int = 5) -> list:
    """找支撑阻力位（局部极值），返回价格列表"""
    if len(df) < window * 2 + 1:
        return []
    highs = df["high"].values
    lows = df["low"].values
    levels = []
    for i in range(window, len(df) - window):
        if highs[i] == max(highs[i-window:i+window+1]):
            levels.append(float(highs[i]))
        if lows[i] == min(lows[i-window:i+window+1]):
            levels.append(float(lows[i]))
    if not levels:
        return []
    levels = sorted(set(levels))
    merged = [levels[0]]
    for lv in levels[1:]:
        if (lv - merged[-1]) / merged[-1] > 0.01:
            merged.append(lv)
    current = float(df["close"].iloc[-1])
    merged.sort(key=lambda x: abs(x - current))
    return merged[:6]


def detect_breakout_retest(df: pd.DataFrame, tolerance: float = 0.005) -> Optional[str]:
    """检测突破回测结构，返回 LONG/SHORT/None"""
    if len(df) < 20:
        return None
    levels = find_pivot_levels(df.iloc[:-5])
    if not levels:
        return None
    current_close = float(df["close"].iloc[-1])
    recent_high = float(df["high"].iloc[-10:].max())
    recent_low = float(df["low"].iloc[-10:].min())
    lookback = df["close"].iloc[-8:-3]
    for level in levels:
        lo, hi = level * (1 - tolerance), level * (1 + tolerance)
        if lo <= current_close <= hi:
            if recent_high > level * 1.005 and (lookback > level * 1.003).any():
                return "LONG"
            if recent_low < level * 0.995 and (lookback < level * 0.997).any():
                return "SHORT"
    return None


def compute_macd(df: pd.DataFrame):
    """返回 macd, signal_line, histogram"""
    ema12 = compute_ema(df["close"], 12)
    ema26 = compute_ema(df["close"], 26)
    macd = ema12 - ema26
    sig = compute_ema(macd, 9)
    hist = macd - sig
    return macd, sig, hist


def detect_macd_divergence(df: pd.DataFrame) -> Optional[str]:
    """检测MACD背驰，返回 LONG/SHORT/None"""
    if len(df) < 50:
        return None
    _, _, hist = compute_macd(df)
    closes = df["close"].values
    window = 5
    n = len(closes)
    peaks, troughs = [], []
    for i in range(window, n - window):
        if closes[i] == max(closes[i-window:i+window+1]):
            peaks.append((i, closes[i], float(hist.iloc[i])))
        if closes[i] == min(closes[i-window:i+window+1]):
            troughs.append((i, closes[i], float(hist.iloc[i])))
    if len(peaks) >= 2:
        p1, p2 = peaks[-2], peaks[-1]
        if p2[1] > p1[1] and p2[2] < p1[2] and closes[-1] > p1[1] * 0.97:
            return "SHORT"
    if len(troughs) >= 2:
        t1, t2 = troughs[-2], troughs[-1]
        if t2[1] < t1[1] and t2[2] > t1[2] and closes[-1] < t1[1] * 1.03:
            return "LONG"
    return None


def detect_candle_pattern(df: pd.DataFrame) -> Optional[str]:
    """识别K线形态，返回 LONG/SHORT/None"""
    if len(df) < 3:
        return None
    last = df.iloc[-1]
    prev = df.iloc[-2]
    o, h, l, c = float(last["open"]), float(last["high"]), float(last["low"]), float(last["close"])
    body = abs(c - o)
    upper = h - max(c, o)
    lower = min(c, o) - l
    rng = h - l if h != l else 0.0001
    # 锤子线 → LONG
    if lower > 2 * body and upper < body and body / rng > 0.1:
        return "LONG"
    # 吞没阳线 → LONG
    po, pc = float(prev["open"]), float(prev["close"])
    if c > o and pc < po and o < pc and c > po:
        return "LONG"
    # 射击之星 → SHORT
    if upper > 2 * body and lower < body and body / rng > 0.1:
        return "SHORT"
    # 吞没阴线 → SHORT
    if c < o and pc > po and o > pc and c < po:
        return "SHORT"
    return None


def detect_entry_trigger(df_1h: pd.DataFrame, df_15m: pd.DataFrame) -> Optional[str]:
    """15m K线形态 + MACD位置 + 成交量放大 确认入场"""
    if len(df_15m) < 30:
        return None

    candle = detect_candle_pattern(df_15m)
    if candle is None:
        return None

    _, _, hist = compute_macd(df_15m)
    last_h = float(hist.iloc[-1])
    prev_h = float(hist.iloc[-2])
    golden = prev_h < 0 and last_h > 0
    death = prev_h > 0 and last_h < 0

    # 成交量确认：入场K线成交量必须大于前20根均量的1.2倍
    volumes = df_15m["volume"].astype(float)
    avg_vol = volumes.iloc[-21:-1].mean()
    last_vol = volumes.iloc[-1]
    volume_confirm = (avg_vol > 0) and (last_vol >= avg_vol * 1.2)

    if not volume_confirm:
        return None

    if candle == "LONG" and (last_h > 0 or golden):
        return "LONG"
    if candle == "SHORT" and (last_h < 0 or death):
        return "SHORT"
    return None


def compute_signal(
    df_weekly: pd.DataFrame,
    df_3day: pd.DataFrame,
    df_daily: pd.DataFrame,
    df_4h: pd.DataFrame,
    df_1h: pd.DataFrame,
    df_15m: pd.DataFrame,
) -> SignalResult:
    """主函数：输入六个时间框架DataFrame，输出SignalResult"""

    # 第一层：趋势
    trend_state = get_trend_state(df_weekly, df_3day)

    # 第二层：结构
    br_4h = detect_breakout_retest(df_4h)
    br_daily = detect_breakout_retest(df_daily)
    structure_breakout = br_4h or br_daily

    div_daily = detect_macd_divergence(df_daily)
    div_4h = detect_macd_divergence(df_4h)
    structure_divergence = div_daily or div_4h

    if structure_breakout and structure_divergence:
        if structure_breakout == structure_divergence:
            structure_signal = structure_breakout
            trigger_type = "BOTH"
        else:
            structure_signal = "NONE"
            trigger_type = "CONFLICT"
    elif structure_breakout:
        structure_signal = structure_breakout
        trigger_type = "BREAKOUT_RETEST"
    elif structure_divergence:
        structure_signal = structure_divergence
        trigger_type = "MACD_DIVERGENCE"
    else:
        structure_signal = "NONE"
        trigger_type = "NONE"

    # 第三层：入场
    entry_trigger = detect_entry_trigger(df_1h, df_15m)

    # 聚合
    signal = "NO_TRADE"
    confidence = 0.0
    reasons = []

    if structure_signal == "NONE" or trigger_type == "CONFLICT":
        reasons.append(f"结构无信号(趋势={trend_state})")
    elif entry_trigger is None:
        reasons.append(f"结构={structure_signal}，小级别无触发")
    elif structure_signal != entry_trigger:
        reasons.append(f"结构={structure_signal} vs 触发={entry_trigger}，方向冲突")
    else:
        direction = structure_signal
        if trend_state == "BULL" and direction == "LONG":
            confidence += 0.5
            reasons.append("周线+3日线多头顺势做多")
        elif trend_state == "BEAR" and direction == "SHORT":
            confidence += 0.5
            reasons.append("周线+3日线空头顺势做空")
        elif trend_state == "MIXED":
            confidence += 0.3
            reasons.append("趋势分歧，极值反转")
        elif trend_state == "FLAT":
            confidence += 0.2
            reasons.append("趋势不明")
        else:
            confidence += 0.15
            reasons.append(f"逆势信号(趋势={trend_state})")

        if trigger_type == "BOTH":
            confidence += 0.35
            reasons.append("突破回测+MACD背驰双确认")
        elif trigger_type in ("BREAKOUT_RETEST", "MACD_DIVERGENCE"):
            confidence += 0.25
            reasons.append(trigger_type)

        confidence += 0.15
        reasons.append("15m触发")
        confidence = min(confidence, 1.0)

        if confidence >= 0.45:
            signal = direction
        else:
            reasons.append(f"置信度{confidence:.2f}不足0.45，观望")

    return SignalResult(
        signal=signal,
        confidence=round(confidence, 2),
        trigger_type=trigger_type,
        trend_state=trend_state,
        structure_signal=structure_signal,
        entry_trigger=entry_trigger or "NONE",
        reason=" | ".join(reasons),
    )
