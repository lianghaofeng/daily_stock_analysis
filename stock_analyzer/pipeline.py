"""Main analysis pipeline — orchestrates data fetching, analysis, and reporting."""

from __future__ import annotations

import logging
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from typing import Optional

from .ai_analyzer import AIAnalyzer
from .config import Config
from .fetcher import BaseFetcher, create_fetcher
from .models import OHLCV, AnalysisReport, StockCode, StockQuote
from .notifier import send_all
from .reporter import generate_report, save_report
from .technical import analyze_trend

logger = logging.getLogger(__name__)


@dataclass
class PipelineResult:
    """Aggregated results from a pipeline run."""

    reports: list[AnalysisReport] = field(default_factory=list)
    report_path: str = ""
    errors: dict[str, str] = field(default_factory=dict)  # code -> error msg

    @property
    def success_count(self) -> int:
        return sum(1 for r in self.reports if r.success)

    @property
    def fail_count(self) -> int:
        return len(self.errors)


class Pipeline:
    """Stock analysis pipeline."""

    def __init__(self, config: Config) -> None:
        self._config = config
        self._fetcher: BaseFetcher = create_fetcher(config.data_source)
        self._ai = AIAnalyzer(config.ai) if config.ai.api_key else None

    def run(self, stock_codes: Optional[list[str]] = None) -> PipelineResult:
        """Run analysis for all configured stocks."""
        codes = stock_codes or self._config.stock_codes
        if not codes:
            logger.warning("No stock codes to analyze")
            return PipelineResult()

        stocks = self._parse_codes(codes)
        result = PipelineResult()

        logger.info("Starting analysis for %d stocks", len(stocks))

        # Concurrent analysis
        with ThreadPoolExecutor(max_workers=self._config.max_workers) as pool:
            futures = {
                pool.submit(self._analyze_one, stock): stock for stock in stocks
            }

            for future in as_completed(futures):
                stock = futures[future]
                try:
                    report = future.result()
                    result.reports.append(report)
                except Exception as e:
                    logger.error("Analysis failed for %s: %s", stock.display, e)
                    result.errors[stock.code] = str(e)

        # Sort by sentiment score (descending)
        result.reports.sort(
            key=lambda r: (
                r.ai_analysis.sentiment_score if r.ai_analysis else 0
            ),
            reverse=True,
        )

        # Generate and save report
        report_content = generate_report(result.reports)
        path = save_report(report_content, self._config.report_dir)
        result.report_path = str(path)

        # Send notifications
        send_all(self._config.notify, "每日股票决策仪表盘", report_content)

        logger.info(
            "Pipeline complete: %d success, %d failed",
            result.success_count,
            result.fail_count,
        )
        return result

    def analyze_single(self, code: str) -> AnalysisReport:
        """Analyze a single stock (for API/bot use)."""
        stock = StockCode.parse(code)
        return self._analyze_one(stock)

    def _analyze_one(self, stock: StockCode) -> AnalysisReport:
        """Full analysis for a single stock."""
        logger.info("Analyzing %s ...", stock.display)

        # Step 1: Fetch historical data
        history = self._fetch_history(stock)
        if not history:
            return AnalysisReport(
                stock=stock,
                quote=None,
                trend=analyze_trend([]),
                ai_analysis=None,
                success=False,
                error="Failed to fetch historical data",
            )

        # Step 2: Fetch real-time quote (non-fatal if missing)
        quote = self._fetch_quote(stock)

        # Step 3: Technical analysis
        trend = analyze_trend(history)

        # Step 4: AI analysis (optional)
        ai_result = None
        if self._ai:
            ai_result = self._ai.analyze(stock, trend, history, quote)
            if not ai_result:
                logger.warning("AI analysis returned no result for %s", stock.display)

        report = AnalysisReport(
            stock=stock,
            quote=quote,
            trend=trend,
            ai_analysis=ai_result,
        )

        logger.info(
            "Analysis done for %s — trend=%s signal=%s",
            stock.display,
            trend.trend.value,
            trend.signal_strength.value,
        )
        return report

    def _fetch_history(self, stock: StockCode) -> list[OHLCV]:
        """Fetch history with error handling."""
        try:
            return self._fetcher.fetch_history(stock, self._config.history_days)
        except Exception as e:
            logger.error("Failed to fetch history for %s: %s", stock.display, e)
            return []

    def _fetch_quote(self, stock: StockCode) -> Optional[StockQuote]:
        """Fetch quote with error handling (non-fatal)."""
        try:
            return self._fetcher.fetch_quote(stock)
        except Exception as e:
            logger.warning("Failed to fetch quote for %s: %s", stock.display, e)
            return None

    @staticmethod
    def _parse_codes(raw_codes: list[str]) -> list[StockCode]:
        """Parse and validate stock codes."""
        stocks: list[StockCode] = []
        for raw in raw_codes:
            try:
                stocks.append(StockCode.parse(raw))
            except ValueError as e:
                logger.warning("Skipping invalid code '%s': %s", raw, e)
        return stocks
