"""AI-powered stock analysis using Gemini or OpenAI-compatible APIs."""

from __future__ import annotations

import json
import logging
import time
from typing import Optional

from .config import AIConfig
from .constants import API_MAX_DELAY
from .models import (
    AIAnalysis,
    OHLCV,
    Sentiment,
    StockCode,
    StockQuote,
    TrendAnalysis,
)

logger = logging.getLogger(__name__)

SYSTEM_PROMPT = """你是一位专业的股票分析师，擅长技术分析和基本面分析。
你的任务是基于提供的技术指标和市场数据，给出客观、专业的分析报告。

要求：
1. 用中文回复
2. 严格按照 JSON 格式输出
3. 给出明确的操作建议（买入/持有/卖出/观望）
4. 提供具体的买卖价位
5. 评估风险等级
6. 使用检查清单标记各项条件状态

JSON 输出格式：
{
    "summary": "核心分析结论（2-3句话）",
    "sentiment_score": 0-100的整数,
    "operation_advice": "买入/持有/卖出/观望",
    "buy_price": 建议买入价或null,
    "sell_price": 建议卖出价或null,
    "stop_loss": 止损价或null,
    "target_price": 目标价或null,
    "risk_level": "低/中/高",
    "checklist": ["✅ 条件1描述", "⚠️ 条件2描述", "❌ 条件3描述"]
}"""


class AIAnalyzer:
    """AI-powered stock analyzer with retry and fallback."""

    def __init__(self, config: AIConfig) -> None:
        self._config = config
    def analyze(
        self,
        stock: StockCode,
        trend: TrendAnalysis,
        history: list[OHLCV],
        quote: Optional[StockQuote] = None,
        news: str = "",
    ) -> Optional[AIAnalysis]:
        """Run AI analysis and return structured result."""
        prompt = self._build_prompt(stock, trend, history, quote, news)
        response = self._call_api(prompt)
        if not response:
            return None
        return self._parse_response(response, stock)

    def _build_prompt(
        self,
        stock: StockCode,
        trend: TrendAnalysis,
        history: list[OHLCV],
        quote: Optional[StockQuote],
        news: str,
    ) -> str:
        """Build analysis prompt from stock data."""
        parts: list[str] = []
        ind = trend.indicators

        parts.append(f"# 分析请求: {stock.display}")
        parts.append("")

        # Price data
        parts.append("## 技术指标")
        if history:
            latest = history[-1]
            parts.append(f"- 最新收盘价: {latest.close:.2f}")
            parts.append(f"- 最新成交量: {latest.volume:.0f}")

        parts.append(f"- MA5: {ind.ma5:.2f}")
        parts.append(f"- MA10: {ind.ma10:.2f}")
        parts.append(f"- MA20: {ind.ma20:.2f}")
        parts.append(f"- MACD: {ind.macd:.4f}")
        parts.append(f"- MACD Signal: {ind.macd_signal:.4f}")
        parts.append(f"- MACD Histogram: {ind.macd_hist:.4f}")
        parts.append(f"- RSI(6): {ind.rsi_6:.1f}")
        parts.append(f"- RSI(14): {ind.rsi_14:.1f}")
        parts.append(f"- 布林上轨: {ind.boll_upper:.2f}")
        parts.append(f"- 布林中轨: {ind.boll_mid:.2f}")
        parts.append(f"- 布林下轨: {ind.boll_lower:.2f}")
        parts.append("")

        # Trend summary
        parts.append("## 趋势分析")
        parts.append(f"- 趋势方向: {trend.trend.value}")
        parts.append(f"- 信号强度: {trend.signal_strength.value}")
        parts.append(f"- 偏离率: {trend.deviation_rate:.2%}")
        parts.append(f"- 支撑位: {trend.support_price:.2f}")
        parts.append(f"- 阻力位: {trend.resistance_price:.2f}")
        if trend.buy_signal:
            parts.append("- **买入信号已触发**")
        if trend.sell_signal:
            parts.append("- **卖出信号已触发**")
        parts.append("")

        for reason in trend.reasons:
            parts.append(f"- {reason}")
        parts.append("")

        # Real-time quote
        if quote:
            parts.append("## 实时行情")
            parts.append(f"- 现价: {quote.price:.2f}")
            parts.append(f"- 涨跌幅: {quote.change_pct:.2f}%")
            parts.append(f"- 今日最高: {quote.high:.2f}")
            parts.append(f"- 今日最低: {quote.low:.2f}")
            parts.append("")

        # Recent K-lines
        if len(history) >= 5:
            parts.append("## 最近5日K线")
            for bar in history[-5:]:
                change = (
                    (bar.close - bar.open) / bar.open * 100 if bar.open else 0
                )
                parts.append(
                    f"- {bar.date}: 开{bar.open:.2f} 高{bar.high:.2f} "
                    f"低{bar.low:.2f} 收{bar.close:.2f} "
                    f"涨跌{change:+.2f}%"
                )
            parts.append("")

        # News
        if news:
            parts.append("## 相关新闻")
            parts.append(news)
            parts.append("")

        parts.append("请严格按照 JSON 格式输出分析结果。")
        return "\n".join(parts)

    def _call_api(self, prompt: str) -> Optional[str]:
        """Call AI API with retry logic."""
        last_error: Optional[Exception] = None

        for attempt in range(self._config.max_retries):
            try:
                if self._config.provider == "gemini":
                    return self._call_gemini(prompt)
                return self._call_openai(prompt)
            except Exception as e:
                last_error = e
                if attempt < self._config.max_retries - 1:
                    delay = min(
                        self._config.retry_delay * (2**attempt),
                        API_MAX_DELAY,
                    )
                    logger.warning(
                        "API call failed (attempt %d/%d): %s. Retrying in %.1fs",
                        attempt + 1,
                        self._config.max_retries,
                        e,
                        delay,
                    )
                    time.sleep(delay)

        logger.error("All API attempts failed: %s", last_error)
        return None

    def _call_gemini(self, prompt: str) -> str:
        """Call Google Gemini API."""
        import urllib.request
        import urllib.error

        url = (
            f"{self._config.base_url}/models/{self._config.model}"
            f":generateContent?key={self._config.api_key}"
        )

        payload = {
            "contents": [{"parts": [{"text": prompt}]}],
            "systemInstruction": {"parts": [{"text": SYSTEM_PROMPT}]},
            "generationConfig": {
                "temperature": self._config.temperature,
                "responseMimeType": "application/json",
            },
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={"Content-Type": "application/json"},
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        candidates = result.get("candidates", [])
        if not candidates:
            raise ValueError("Gemini returned no candidates")

        text = candidates[0]["content"]["parts"][0]["text"]
        return text

    def _call_openai(self, prompt: str) -> str:
        """Call OpenAI-compatible API."""
        import urllib.request

        url = f"{self._config.base_url}/chat/completions"

        payload = {
            "model": self._config.model,
            "messages": [
                {"role": "system", "content": SYSTEM_PROMPT},
                {"role": "user", "content": prompt},
            ],
            "temperature": self._config.temperature,
            "response_format": {"type": "json_object"},
        }

        data = json.dumps(payload).encode("utf-8")
        req = urllib.request.Request(
            url,
            data=data,
            headers={
                "Content-Type": "application/json",
                "Authorization": f"Bearer {self._config.api_key}",
            },
            method="POST",
        )

        with urllib.request.urlopen(req, timeout=60) as resp:
            result = json.loads(resp.read().decode("utf-8"))

        return result["choices"][0]["message"]["content"]

    def _parse_response(
        self, response: str, stock: StockCode
    ) -> Optional[AIAnalysis]:
        """Parse AI JSON response into AIAnalysis."""
        try:
            # Strip markdown code fences if present
            text = response.strip()
            if text.startswith("```"):
                text = text.split("\n", 1)[1]
            if text.endswith("```"):
                text = text.rsplit("```", 1)[0]
            text = text.strip()

            data = json.loads(text)

            score = int(data.get("sentiment_score", 50))
            score = max(0, min(100, score))

            return AIAnalysis(
                summary=data.get("summary", ""),
                sentiment=Sentiment.from_score(score),
                sentiment_score=score,
                operation_advice=data.get("operation_advice", "观望"),
                buy_price=_safe_float(data.get("buy_price")),
                sell_price=_safe_float(data.get("sell_price")),
                stop_loss=_safe_float(data.get("stop_loss")),
                target_price=_safe_float(data.get("target_price")),
                risk_level=data.get("risk_level", "中"),
                checklist=data.get("checklist", []),
            )

        except (json.JSONDecodeError, KeyError, TypeError) as e:
            logger.error(
                "Failed to parse AI response for %s: %s", stock.display, e
            )
            return None


def _safe_float(val: object) -> Optional[float]:
    """Safely convert to float, returning None on failure."""
    if val is None:
        return None
    try:
        return float(val)
    except (ValueError, TypeError):
        return None
