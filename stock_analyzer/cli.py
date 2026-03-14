"""Command-line interface for the stock analyzer."""

from __future__ import annotations

import argparse
import logging
import sys

from . import __version__
from .config import Config
from .pipeline import Pipeline


def main(argv: list[str] | None = None) -> int:
    """CLI entry point."""
    parser = argparse.ArgumentParser(
        description="AI-driven stock intelligent analysis system",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""\
examples:
  %(prog)s                         Analyze stocks from .env config
  %(prog)s -s 600519,000858        Analyze specific stocks
  %(prog)s -s AAPL --source yfinance  Analyze US stock
  %(prog)s --dry-run               Technical analysis only (no AI)
""",
    )
    parser.add_argument(
        "-s", "--stocks",
        help="Comma-separated stock codes (overrides .env)",
    )
    parser.add_argument(
        "--env",
        default=".env",
        help="Path to .env file (default: .env)",
    )
    parser.add_argument(
        "--source",
        choices=["akshare", "yfinance"],
        help="Data source (overrides .env)",
    )
    parser.add_argument(
        "--dry-run",
        action="store_true",
        help="Skip AI analysis and notifications",
    )
    parser.add_argument(
        "--report-dir",
        help="Report output directory (default: reports)",
    )
    parser.add_argument(
        "-v", "--verbose",
        action="store_true",
        help="Enable debug logging",
    )
    parser.add_argument(
        "--version",
        action="version",
        version=f"%(prog)s {__version__}",
    )

    args = parser.parse_args(argv)

    # Setup logging
    log_level = logging.DEBUG if args.verbose else logging.INFO
    logging.basicConfig(
        level=log_level,
        format="%(asctime)s [%(levelname)s] %(name)s: %(message)s",
        datefmt="%H:%M:%S",
    )

    # Load config
    config = Config.from_env(args.env)

    # CLI overrides
    if args.stocks:
        config.stock_codes = [
            c.strip() for c in args.stocks.replace("，", ",").split(",") if c.strip()
        ]
    if args.source:
        config.data_source = args.source
    if args.report_dir:
        config.report_dir = args.report_dir
    if args.dry_run:
        config.ai.api_key = ""  # disable AI

    # Validate
    errors = config.validate()
    for err in errors:
        logging.warning("Config: %s", err)

    if not config.stock_codes:
        logging.error("No stock codes provided. Use -s or set STOCK_CODES in .env")
        return 1

    # Run pipeline
    pipeline = Pipeline(config)
    result = pipeline.run()

    # Summary
    print(f"\n{'='*50}")
    print(f"Analysis complete: {result.success_count} success, {result.fail_count} failed")
    if result.report_path:
        print(f"Report saved to: {result.report_path}")
    if result.errors:
        print("Errors:")
        for code, err in result.errors.items():
            print(f"  {code}: {err}")
    print(f"{'='*50}")

    return 0 if result.fail_count == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
