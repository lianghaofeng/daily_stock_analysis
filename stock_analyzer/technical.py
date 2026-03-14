"""Technical analysis — compute indicators and generate signals."""

from __future__ import annotations

import logging
from typing import Optional

from .constants import (
    BOLL_PERIOD,
    BOLL_STD_DEV,
    DEVIATION_DANGER_THRESHOLD,
    MA_FAST,
    MA_LONG,
    MA_MID,
    MA_SLOW,
    MACD_FAST,
    MACD_SIGNAL,
    MACD_SLOW,
    RSI_FAST,
    RSI_STANDARD,
    VOLUME_HEAVY_INCREASE,
    VOLUME_HEAVY_SHRINK,
    VOLUME_LIGHT_INCREASE,
    VOLUME_LIGHT_SHRINK,
    VOLUME_NORMAL_HIGH,
)
from .models import OHLCV, SignalStrength, Trend, TechnicalIndicators, TrendAnalysis

logger = logging.getLogger(__name__)


def analyze_trend(history: list[OHLCV]) -> TrendAnalysis:
    """Perform full technical analysis on historical data."""
    if len(history) < MA_SLOW:
        return TrendAnalysis(
            trend=Trend.NEUTRAL,
            signal_strength=SignalStrength.NONE,
            indicators=TechnicalIndicators(),
            reasons=["Insufficient data for analysis"],
        )

    closes = [bar.close for bar in history]
    volumes = [bar.volume for bar in history]

    indicators = _compute_indicators(closes)
    current_price = closes[-1]

    trend = _determine_trend(indicators)
    deviation = _deviation_rate(current_price, indicators.ma20)
    buy_signal, sell_signal, reasons = _generate_signals(
        indicators, deviation, closes, volumes
    )
    signal_strength = _assess_strength(indicators, buy_signal, sell_signal)
    support = _find_support(closes)
    resistance = _find_resistance(closes)

    return TrendAnalysis(
        trend=trend,
        signal_strength=signal_strength,
        indicators=indicators,
        buy_signal=buy_signal,
        sell_signal=sell_signal,
        support_price=support,
        resistance_price=resistance,
        deviation_rate=deviation,
        reasons=reasons,
    )


def _compute_indicators(closes: list[float]) -> TechnicalIndicators:
    """Compute all technical indicators from close prices."""
    return TechnicalIndicators(
        ma5=_sma(closes, MA_FAST),
        ma10=_sma(closes, MA_MID),
        ma20=_sma(closes, MA_SLOW),
        ma60=_sma(closes, MA_LONG) if len(closes) >= MA_LONG else 0.0,
        macd=_ema(closes, MACD_FAST) - _ema(closes, MACD_SLOW),
        macd_signal=_macd_signal(closes),
        macd_hist=_macd_histogram(closes),
        rsi_6=_rsi(closes, RSI_FAST),
        rsi_14=_rsi(closes, RSI_STANDARD),
        boll_upper=_bollinger(closes, BOLL_PERIOD, BOLL_STD_DEV, "upper"),
        boll_mid=_sma(closes, BOLL_PERIOD),
        boll_lower=_bollinger(closes, BOLL_PERIOD, BOLL_STD_DEV, "lower"),
    )


def _determine_trend(ind: TechnicalIndicators) -> Trend:
    """Determine trend from indicator alignment."""
    if ind.ma_bullish and ind.macd_golden_cross:
        return Trend.BULLISH
    if ind.ma_bearish and not ind.macd_golden_cross:
        return Trend.BEARISH
    return Trend.NEUTRAL


def _deviation_rate(price: float, ma20: float) -> float:
    """Calculate price deviation from MA20."""
    if ma20 <= 0:
        return 0.0
    return (price - ma20) / ma20


def _generate_signals(
    ind: TechnicalIndicators,
    deviation: float,
    closes: list[float],
    volumes: list[float],
) -> tuple[bool, bool, list[str]]:
    """Generate buy/sell signals with reasons."""
    reasons: list[str] = []
    buy = False
    sell = False

    # Trend alignment
    if ind.ma_bullish:
        reasons.append("均线多头排列 (MA5>MA10>MA20)")
    elif ind.ma_bearish:
        reasons.append("均线空头排列 (MA5<MA10<MA20)")

    # MACD
    if ind.macd_golden_cross:
        reasons.append("MACD 金叉")
    else:
        reasons.append("MACD 死叉")

    # RSI
    if ind.rsi_oversold:
        reasons.append("RSI 超卖区间")
    elif ind.rsi_overbought:
        reasons.append("RSI 超买区间")

    # Deviation check
    if abs(deviation) > DEVIATION_DANGER_THRESHOLD:
        if deviation > 0:
            reasons.append(f"偏离率 {deviation:.1%} 过高，注意追高风险")
        else:
            reasons.append(f"偏离率 {deviation:.1%} 过低，可能超跌")

    # Volume analysis
    vol_ratio = _volume_ratio(volumes)
    if vol_ratio is not None:
        reasons.append(f"量比 {vol_ratio:.2f} — {_volume_desc(vol_ratio)}")

    # Buy conditions: bullish alignment + MACD golden + deviation safe
    if (
        ind.ma_bullish
        and ind.macd_golden_cross
        and deviation < DEVIATION_DANGER_THRESHOLD
        and not ind.rsi_overbought
    ):
        buy = True
        reasons.append("综合买入信号触发")

    # Sell conditions: bearish alignment or RSI overbought + deviation high
    if ind.ma_bearish or (
        ind.rsi_overbought and deviation > DEVIATION_DANGER_THRESHOLD
    ):
        sell = True
        reasons.append("综合卖出信号触发")

    return buy, sell, reasons


def _assess_strength(
    ind: TechnicalIndicators, buy: bool, sell: bool
) -> SignalStrength:
    """Assess overall signal strength."""
    score = 0

    if ind.ma_bullish:
        score += 2
    elif ind.ma_bearish:
        score -= 2

    if ind.macd_golden_cross:
        score += 1
    else:
        score -= 1

    if ind.rsi_oversold:
        score += 1
    elif ind.rsi_overbought:
        score -= 1

    abs_score = abs(score)
    if abs_score >= 3:
        return SignalStrength.STRONG
    if abs_score >= 2:
        return SignalStrength.MODERATE
    if abs_score >= 1:
        return SignalStrength.WEAK
    return SignalStrength.NONE


def _find_support(closes: list[float], lookback: int = 20) -> float:
    """Find recent support level (lowest low in lookback period)."""
    recent = closes[-lookback:] if len(closes) >= lookback else closes
    return min(recent)


def _find_resistance(closes: list[float], lookback: int = 20) -> float:
    """Find recent resistance level (highest high in lookback period)."""
    recent = closes[-lookback:] if len(closes) >= lookback else closes
    return max(recent)


# === Calculation helpers ===


def _sma(data: list[float], period: int) -> float:
    """Simple Moving Average of last `period` values."""
    if len(data) < period:
        return 0.0
    return sum(data[-period:]) / period


def _ema(data: list[float], period: int) -> float:
    """Exponential Moving Average."""
    if len(data) < period:
        return 0.0

    multiplier = 2 / (period + 1)
    ema_val = sum(data[:period]) / period  # SMA for seed

    for price in data[period:]:
        ema_val = (price - ema_val) * multiplier + ema_val

    return ema_val


def _macd_signal(closes: list[float]) -> float:
    """MACD signal line (EMA of MACD line)."""
    if len(closes) < MACD_SLOW + MACD_SIGNAL:
        return 0.0

    # Compute MACD line for each point
    macd_values: list[float] = []
    for i in range(MACD_SLOW, len(closes) + 1):
        segment = closes[:i]
        macd_val = _ema(segment, MACD_FAST) - _ema(segment, MACD_SLOW)
        macd_values.append(macd_val)

    if len(macd_values) < MACD_SIGNAL:
        return 0.0

    return _ema(macd_values, MACD_SIGNAL)


def _macd_histogram(closes: list[float]) -> float:
    """MACD histogram (MACD - Signal)."""
    macd_line = _ema(closes, MACD_FAST) - _ema(closes, MACD_SLOW)
    signal = _macd_signal(closes)
    return macd_line - signal


def _rsi(closes: list[float], period: int) -> float:
    """Relative Strength Index."""
    if len(closes) < period + 1:
        return 50.0

    changes = [closes[i] - closes[i - 1] for i in range(1, len(closes))]
    recent = changes[-period:]

    gains = [c for c in recent if c > 0]
    losses = [-c for c in recent if c < 0]

    avg_gain = sum(gains) / period if gains else 0.0
    avg_loss = sum(losses) / period if losses else 0.0

    if avg_loss == 0:
        return 100.0
    rs = avg_gain / avg_loss
    return 100.0 - (100.0 / (1.0 + rs))


def _bollinger(
    closes: list[float], period: int, num_std: float, band: str
) -> float:
    """Bollinger Band value."""
    if len(closes) < period:
        return 0.0

    recent = closes[-period:]
    mean = sum(recent) / period
    variance = sum((x - mean) ** 2 for x in recent) / period
    std = variance**0.5

    if band == "upper":
        return mean + num_std * std
    return mean - num_std * std


def _volume_ratio(volumes: list[float], period: int = 5) -> Optional[float]:
    """Recent volume vs average volume ratio."""
    if len(volumes) < period + 1:
        return None
    recent_avg = sum(volumes[-period:]) / period
    prev_avg = sum(volumes[-period * 2 : -period]) / period if len(volumes) >= period * 2 else recent_avg
    if prev_avg <= 0:
        return None
    return recent_avg / prev_avg


def _volume_desc(ratio: float) -> str:
    """Human-readable volume description."""
    if ratio < VOLUME_HEAVY_SHRINK:
        return "严重缩量"
    if ratio < VOLUME_LIGHT_SHRINK:
        return "缩量"
    if ratio < VOLUME_NORMAL_HIGH:
        return "正常"
    if ratio < VOLUME_LIGHT_INCREASE:
        return "温和放量"
    if ratio < VOLUME_HEAVY_INCREASE:
        return "放量"
    return "巨量"
