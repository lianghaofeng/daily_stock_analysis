"""Data models for the stock analysis system."""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime
from enum import Enum
from typing import Optional


class Market(Enum):
    """Stock market type."""

    CN = "cn"  # A-share
    HK = "hk"  # Hong Kong
    US = "us"  # US market


class Trend(Enum):
    """Price trend direction."""

    BULLISH = "bullish"
    BEARISH = "bearish"
    NEUTRAL = "neutral"


class SignalStrength(Enum):
    """Signal strength level."""

    STRONG = "strong"
    MODERATE = "moderate"
    WEAK = "weak"
    NONE = "none"


class Sentiment(Enum):
    """Market sentiment."""

    VERY_BULLISH = "very_bullish"
    BULLISH = "bullish"
    NEUTRAL = "neutral"
    BEARISH = "bearish"
    VERY_BEARISH = "very_bearish"

    @classmethod
    def from_score(cls, score: int) -> Sentiment:
        if score >= 80:
            return cls.VERY_BULLISH
        if score >= 60:
            return cls.BULLISH
        if score >= 40:
            return cls.NEUTRAL
        if score >= 20:
            return cls.BEARISH
        return cls.VERY_BEARISH


@dataclass(frozen=True)
class StockCode:
    """Validated stock code with market info.

    Supports formats:
    - A-share: 6-digit code (600519, 000001)
    - HK: 5-digit code (00700, 09988)
    - US: 1-5 letter ticker (AAPL, MSFT)
    """

    code: str
    market: Market
    name: str = ""

    @classmethod
    def parse(cls, raw: str, name: str = "") -> StockCode:
        """Parse and validate a stock code string."""
        raw = raw.strip().upper()
        if not raw:
            raise ValueError("Stock code cannot be empty")

        # US stock: all letters
        if raw.isalpha():
            if len(raw) > 5:
                raise ValueError(f"Invalid US stock ticker: {raw}")
            return cls(code=raw, market=Market.US, name=name)

        # Numeric codes
        if not raw.isdigit():
            raise ValueError(f"Invalid stock code: {raw}")

        if len(raw) == 6:
            return cls(code=raw, market=Market.CN, name=name)
        if len(raw) == 5:
            return cls(code=raw, market=Market.HK, name=name)

        raise ValueError(f"Invalid stock code length: {raw}")

    @property
    def display(self) -> str:
        if self.name:
            return f"{self.name}({self.code})"
        return self.code


@dataclass
class StockQuote:
    """Real-time stock quote."""

    code: str
    name: str
    price: float
    change_pct: float  # percentage
    volume: float  # in shares
    turnover: float  # in currency
    high: float
    low: float
    open: float
    prev_close: float
    timestamp: datetime = field(default_factory=datetime.now)

    @property
    def volume_ratio(self) -> float:
        """Approximate volume ratio (current vs average)."""
        if self.prev_close <= 0:
            return 1.0
        return self.volume / max(self.turnover / self.prev_close, 1)


@dataclass
class OHLCV:
    """Single candlestick data point."""

    date: date
    open: float
    high: float
    low: float
    close: float
    volume: float
    turnover: float = 0.0


@dataclass
class TechnicalIndicators:
    """Computed technical indicators for a stock."""

    ma5: float = 0.0
    ma10: float = 0.0
    ma20: float = 0.0
    ma60: float = 0.0

    macd: float = 0.0
    macd_signal: float = 0.0
    macd_hist: float = 0.0

    rsi_6: float = 50.0
    rsi_14: float = 50.0

    # Bollinger Bands
    boll_upper: float = 0.0
    boll_mid: float = 0.0
    boll_lower: float = 0.0

    @property
    def ma_bullish(self) -> bool:
        """MA5 > MA10 > MA20 bullish alignment."""
        return self.ma5 > self.ma10 > self.ma20 > 0

    @property
    def ma_bearish(self) -> bool:
        """MA5 < MA10 < MA20 bearish alignment."""
        return 0 < self.ma5 < self.ma10 < self.ma20

    @property
    def macd_golden_cross(self) -> bool:
        return self.macd > self.macd_signal and self.macd_hist > 0

    @property
    def rsi_overbought(self) -> bool:
        return self.rsi_14 > 70

    @property
    def rsi_oversold(self) -> bool:
        return self.rsi_14 < 30


@dataclass
class TrendAnalysis:
    """Result of technical trend analysis."""

    trend: Trend
    signal_strength: SignalStrength
    indicators: TechnicalIndicators
    buy_signal: bool = False
    sell_signal: bool = False
    support_price: float = 0.0
    resistance_price: float = 0.0
    deviation_rate: float = 0.0  # price deviation from MA20
    reasons: list[str] = field(default_factory=list)


@dataclass
class AIAnalysis:
    """Result from AI analysis."""

    summary: str
    sentiment: Sentiment
    sentiment_score: int  # 0-100
    operation_advice: str
    buy_price: Optional[float] = None
    sell_price: Optional[float] = None
    stop_loss: Optional[float] = None
    target_price: Optional[float] = None
    risk_level: str = ""
    checklist: list[str] = field(default_factory=list)


@dataclass
class AnalysisReport:
    """Complete analysis report for one stock."""

    stock: StockCode
    quote: Optional[StockQuote]
    trend: TrendAnalysis
    ai_analysis: Optional[AIAnalysis]
    news_summary: str = ""
    timestamp: datetime = field(default_factory=datetime.now)
    success: bool = True
    error: str = ""

    @property
    def sentiment_label(self) -> str:
        if self.ai_analysis:
            return self.ai_analysis.sentiment.value.replace("_", " ").title()
        return "N/A"


@dataclass
class MarketOverview:
    """Daily market overview."""

    date: date
    indices: dict[str, float] = field(default_factory=dict)  # name -> change%
    summary: str = ""
    hot_sectors: list[str] = field(default_factory=list)
