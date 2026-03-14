"""Report generation — markdown dashboard output."""

from __future__ import annotations

import logging
from datetime import datetime
from pathlib import Path
from typing import Optional

from .constants import CHECK_FAIL, CHECK_PASS, CHECK_WARN
from .models import AnalysisReport, MarketOverview, Trend

logger = logging.getLogger(__name__)


def generate_report(reports: list[AnalysisReport], market: Optional[MarketOverview] = None) -> str:
    """Generate a full markdown dashboard report."""
    parts: list[str] = []
    now = datetime.now().strftime("%Y-%m-%d %H:%M")

    parts.append(f"# 📊 每日股票决策仪表盘")
    parts.append(f"*生成时间: {now}*")
    parts.append("")

    # Market overview
    if market:
        parts.append(_format_market(market))
        parts.append("")

    # Summary table
    parts.append("## 总览")
    parts.append("")
    parts.append("| 股票 | 趋势 | 信号 | 情绪 | 操作建议 |")
    parts.append("|------|------|------|------|----------|")
    for r in reports:
        if not r.success:
            parts.append(f"| {r.stock.display} | ❌ 分析失败 | - | - | - |")
            continue
        trend_icon = _trend_icon(r.trend.trend)
        advice = r.ai_analysis.operation_advice if r.ai_analysis else "-"
        parts.append(
            f"| {r.stock.display} | {trend_icon} {r.trend.trend.value} "
            f"| {r.trend.signal_strength.value} "
            f"| {r.sentiment_label} "
            f"| **{advice}** |"
        )
    parts.append("")

    # Detailed reports per stock
    for r in reports:
        if not r.success:
            continue
        parts.append(_format_stock_detail(r))
        parts.append("")

    parts.append("---")
    parts.append("*本报告由 AI 生成，仅供参考，不构成投资建议。*")

    return "\n".join(parts)


def save_report(content: str, report_dir: str) -> Path:
    """Save report to file and return the path."""
    dir_path = Path(report_dir)
    dir_path.mkdir(parents=True, exist_ok=True)

    filename = f"report_{datetime.now().strftime('%Y%m%d_%H%M%S')}.md"
    file_path = dir_path / filename
    file_path.write_text(content, encoding="utf-8")

    logger.info("Report saved to %s", file_path)
    return file_path


def _format_market(market: MarketOverview) -> str:
    """Format market overview section."""
    lines = ["## 市场概览", ""]

    if market.indices:
        for name, change in market.indices.items():
            icon = "🔴" if change < 0 else "🟢"
            lines.append(f"- {icon} {name}: {change:+.2f}%")
        lines.append("")

    if market.hot_sectors:
        lines.append(f"**热门板块**: {', '.join(market.hot_sectors)}")
        lines.append("")

    if market.summary:
        lines.append(market.summary)

    return "\n".join(lines)


def _format_stock_detail(report: AnalysisReport) -> str:
    """Format detailed analysis for one stock."""
    lines: list[str] = []
    r = report
    ind = r.trend.indicators
    ai = r.ai_analysis

    lines.append(f"## {r.stock.display}")
    lines.append("")

    # AI Summary
    if ai:
        lines.append(f"**{ai.summary}**")
        lines.append("")
        lines.append(f"- 操作建议: **{ai.operation_advice}**")
        lines.append(f"- 情绪评分: {ai.sentiment_score}/100 ({r.sentiment_label})")
        lines.append(f"- 风险等级: {ai.risk_level}")
        lines.append("")

        # Price targets
        prices: list[str] = []
        if ai.buy_price is not None:
            prices.append(f"买入价: {ai.buy_price:.2f}")
        if ai.target_price is not None:
            prices.append(f"目标价: {ai.target_price:.2f}")
        if ai.stop_loss is not None:
            prices.append(f"止损价: {ai.stop_loss:.2f}")
        if ai.sell_price is not None:
            prices.append(f"卖出价: {ai.sell_price:.2f}")
        if prices:
            lines.append("**价位参考**: " + " | ".join(prices))
            lines.append("")

    # Technical indicators
    lines.append("### 技术指标")
    lines.append(f"- 均线: MA5={ind.ma5:.2f} MA10={ind.ma10:.2f} MA20={ind.ma20:.2f}")
    lines.append(f"- MACD: {ind.macd:.4f} (Signal: {ind.macd_signal:.4f})")
    lines.append(f"- RSI(14): {ind.rsi_14:.1f}")
    lines.append(f"- 偏离率: {r.trend.deviation_rate:.2%}")
    lines.append(f"- 支撑/阻力: {r.trend.support_price:.2f} / {r.trend.resistance_price:.2f}")
    lines.append("")

    # Signals
    lines.append("### 信号")
    for reason in r.trend.reasons:
        lines.append(f"- {reason}")
    lines.append("")

    # Checklist
    if ai and ai.checklist:
        lines.append("### 检查清单")
        for item in ai.checklist:
            lines.append(f"- {item}")
        lines.append("")

    return "\n".join(lines)


def _trend_icon(trend: Trend) -> str:
    if trend == Trend.BULLISH:
        return "📈"
    if trend == Trend.BEARISH:
        return "📉"
    return "➡️"
