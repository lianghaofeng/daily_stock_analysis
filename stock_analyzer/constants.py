"""Named constants — no magic numbers."""

# === Technical Analysis ===

# Moving average periods
MA_FAST = 5
MA_MID = 10
MA_SLOW = 20
MA_LONG = 60

# RSI periods
RSI_FAST = 6
RSI_STANDARD = 14

# RSI thresholds
RSI_OVERBOUGHT = 70
RSI_OVERSOLD = 30

# MACD parameters
MACD_FAST = 12
MACD_SLOW = 26
MACD_SIGNAL = 9

# Bollinger Band parameters
BOLL_PERIOD = 20
BOLL_STD_DEV = 2

# Deviation rate threshold — avoid chasing highs
DEVIATION_DANGER_THRESHOLD = 0.05  # 5%

# Volume ratio thresholds
VOLUME_HEAVY_SHRINK = 0.5
VOLUME_LIGHT_SHRINK = 0.8
VOLUME_NORMAL_HIGH = 1.2
VOLUME_LIGHT_INCREASE = 2.0
VOLUME_HEAVY_INCREASE = 3.0

# === Data Fetching ===

# Default historical data days
DEFAULT_HISTORY_DAYS = 120

# === AI Analysis ===

# Sentiment score ranges
SENTIMENT_VERY_BULLISH = 80
SENTIMENT_BULLISH = 60
SENTIMENT_NEUTRAL = 40
SENTIMENT_BEARISH = 20

# API retry config
API_MAX_RETRIES = 3
API_BASE_DELAY = 2.0  # seconds
API_MAX_DELAY = 30.0  # seconds

# Temperature range
TEMPERATURE_MIN = 0.0
TEMPERATURE_MAX = 2.0
TEMPERATURE_DEFAULT = 0.7

# === Report ===

# Checklist markers
CHECK_PASS = "✅"
CHECK_WARN = "⚠️"
CHECK_FAIL = "❌"
