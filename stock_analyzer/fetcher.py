"""Stock data fetching with pluggable backends."""

from __future__ import annotations

import abc
import logging
from datetime import date, timedelta
from typing import Optional

from .constants import DEFAULT_HISTORY_DAYS
from .models import Market, OHLCV, StockCode, StockQuote

logger = logging.getLogger(__name__)


class BaseFetcher(abc.ABC):
    """Abstract base class for stock data fetchers."""

    @abc.abstractmethod
    def fetch_history(
        self, stock: StockCode, days: int = DEFAULT_HISTORY_DAYS
    ) -> list[OHLCV]:
        """Fetch historical OHLCV data."""

    @abc.abstractmethod
    def fetch_quote(self, stock: StockCode) -> Optional[StockQuote]:
        """Fetch real-time quote."""

    @property
    @abc.abstractmethod
    def name(self) -> str:
        """Data source name for logging."""


class AKShareFetcher(BaseFetcher):
    """Fetch data from AKShare (free, supports A-share and HK)."""

    @property
    def name(self) -> str:
        return "akshare"

    def fetch_history(
        self, stock: StockCode, days: int = DEFAULT_HISTORY_DAYS
    ) -> list[OHLCV]:
        try:
            import akshare as ak
        except ImportError:
            raise RuntimeError(
                "akshare is not installed. Run: pip install akshare"
            )

        end_date = date.today()
        start_date = end_date - timedelta(days=days)
        start_str = start_date.strftime("%Y%m%d")
        end_str = end_date.strftime("%Y%m%d")

        if stock.market == Market.CN:
            df = ak.stock_zh_a_hist(
                symbol=stock.code,
                period="daily",
                start_date=start_str,
                end_date=end_str,
                adjust="qfq",
            )
        elif stock.market == Market.HK:
            df = ak.stock_hk_hist(
                symbol=stock.code,
                period="daily",
                start_date=start_str,
                end_date=end_str,
                adjust="qfq",
            )
        else:
            raise ValueError(f"AKShare does not support market: {stock.market}")

        result: list[OHLCV] = []
        for _, row in df.iterrows():
            result.append(
                OHLCV(
                    date=_parse_date(row["日期"]),
                    open=float(row["开盘"]),
                    high=float(row["最高"]),
                    low=float(row["最低"]),
                    close=float(row["收盘"]),
                    volume=float(row["成交量"]),
                    turnover=float(row.get("成交额", 0)),
                )
            )

        logger.info(
            "Fetched %d records for %s from AKShare", len(result), stock.display
        )
        return result

    def fetch_quote(self, stock: StockCode) -> Optional[StockQuote]:
        try:
            import akshare as ak
        except ImportError:
            return None

        try:
            if stock.market != Market.CN:
                return None

            df = ak.stock_zh_a_spot_em()
            row = df[df["代码"] == stock.code]
            if row.empty:
                return None

            r = row.iloc[0]
            return StockQuote(
                code=stock.code,
                name=str(r.get("名称", stock.code)),
                price=float(r["最新价"]),
                change_pct=float(r["涨跌幅"]),
                volume=float(r["成交量"]),
                turnover=float(r["成交额"]),
                high=float(r["最高"]),
                low=float(r["最低"]),
                open=float(r["今开"]),
                prev_close=float(r["昨收"]),
            )
        except Exception as e:
            logger.warning("Failed to fetch quote for %s: %s", stock.code, e)
            return None


class YFinanceFetcher(BaseFetcher):
    """Fetch data from Yahoo Finance (free, supports US stocks)."""

    @property
    def name(self) -> str:
        return "yfinance"

    def fetch_history(
        self, stock: StockCode, days: int = DEFAULT_HISTORY_DAYS
    ) -> list[OHLCV]:
        try:
            import yfinance as yf
        except ImportError:
            raise RuntimeError(
                "yfinance is not installed. Run: pip install yfinance"
            )

        ticker = self._to_yf_symbol(stock)
        data = yf.download(ticker, period=f"{days}d", progress=False)

        if data.empty:
            logger.warning("No data returned for %s", stock.display)
            return []

        result: list[OHLCV] = []
        for idx, row in data.iterrows():
            result.append(
                OHLCV(
                    date=idx.date(),
                    open=float(row["Open"]),
                    high=float(row["High"]),
                    low=float(row["Low"]),
                    close=float(row["Close"]),
                    volume=float(row["Volume"]),
                )
            )

        logger.info(
            "Fetched %d records for %s from yfinance", len(result), stock.display
        )
        return result

    def fetch_quote(self, stock: StockCode) -> Optional[StockQuote]:
        try:
            import yfinance as yf
        except ImportError:
            return None

        try:
            ticker = yf.Ticker(self._to_yf_symbol(stock))
            info = ticker.info
            if not info or "regularMarketPrice" not in info:
                return None

            return StockQuote(
                code=stock.code,
                name=info.get("shortName", stock.code),
                price=float(info["regularMarketPrice"]),
                change_pct=float(info.get("regularMarketChangePercent", 0)),
                volume=float(info.get("regularMarketVolume", 0)),
                turnover=0.0,
                high=float(info.get("regularMarketDayHigh", 0)),
                low=float(info.get("regularMarketDayLow", 0)),
                open=float(info.get("regularMarketOpen", 0)),
                prev_close=float(info.get("regularMarketPreviousClose", 0)),
            )
        except Exception as e:
            logger.warning("Failed to fetch quote for %s: %s", stock.code, e)
            return None

    @staticmethod
    def _to_yf_symbol(stock: StockCode) -> str:
        if stock.market == Market.US:
            return stock.code
        if stock.market == Market.CN:
            suffix = ".SS" if stock.code.startswith("6") else ".SZ"
            return stock.code + suffix
        if stock.market == Market.HK:
            return stock.code + ".HK"
        return stock.code


def create_fetcher(source: str) -> BaseFetcher:
    """Factory function to create the appropriate data fetcher."""
    fetchers = {
        "akshare": AKShareFetcher,
        "yfinance": YFinanceFetcher,
    }
    cls = fetchers.get(source.lower())
    if cls is None:
        available = ", ".join(fetchers.keys())
        raise ValueError(
            f"Unknown data source '{source}'. Available: {available}"
        )
    return cls()


def _parse_date(val: object) -> date:
    """Parse various date formats to date object."""
    if isinstance(val, date):
        return val
    s = str(val).split(" ")[0]
    for fmt in ("%Y-%m-%d", "%Y%m%d", "%Y/%m/%d"):
        try:
            from datetime import datetime

            return datetime.strptime(s, fmt).date()
        except ValueError:
            continue
    raise ValueError(f"Cannot parse date: {val}")
