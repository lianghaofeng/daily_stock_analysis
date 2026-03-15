"""Configuration management with validation."""

from __future__ import annotations

import os
from dataclasses import dataclass, field
from pathlib import Path
from typing import Optional

from .constants import API_BASE_DELAY, API_MAX_RETRIES, TEMPERATURE_DEFAULT


@dataclass
class AIConfig:
    """AI service configuration."""

    api_key: str = ""
    base_url: str = "https://generativelanguage.googleapis.com/v1beta"
    model: str = "gemini-2.0-flash"
    temperature: float = TEMPERATURE_DEFAULT
    max_retries: int = API_MAX_RETRIES
    retry_delay: float = API_BASE_DELAY
    provider: str = "gemini"  # "gemini" or "openai"


@dataclass
class NotifyConfig:
    """Notification channel configuration."""

    # Webhook (generic)
    webhook_url: str = ""

    # Telegram
    telegram_bot_token: str = ""
    telegram_chat_id: str = ""

    # Email
    email_sender: str = ""
    email_password: str = ""
    email_receivers: list[str] = field(default_factory=list)
    email_smtp_host: str = ""
    email_smtp_port: int = 465

    @property
    def telegram_enabled(self) -> bool:
        return bool(self.telegram_bot_token and self.telegram_chat_id)

    @property
    def email_enabled(self) -> bool:
        return bool(self.email_sender and self.email_password and self.email_receivers)

    @property
    def webhook_enabled(self) -> bool:
        return bool(self.webhook_url)


@dataclass
class Config:
    """Root configuration with validation."""

    stock_codes: list[str] = field(default_factory=list)
    ai: AIConfig = field(default_factory=AIConfig)
    notify: NotifyConfig = field(default_factory=NotifyConfig)
    history_days: int = 120
    max_workers: int = 3
    report_dir: str = "reports"
    data_source: str = "akshare"  # akshare, yfinance
    log_level: str = "INFO"

    def validate(self) -> list[str]:
        """Validate config and return list of warnings/errors."""
        errors: list[str] = []

        if not self.stock_codes:
            errors.append("No stock codes configured (STOCK_CODES)")

        if not self.ai.api_key:
            errors.append("No AI API key configured (AI_API_KEY)")

        if not (0.0 <= self.ai.temperature <= 2.0):
            errors.append(
                f"AI temperature {self.ai.temperature} out of range [0.0, 2.0]"
            )

        if self.max_workers < 1:
            errors.append(f"max_workers must be >= 1, got {self.max_workers}")

        if self.history_days < 30:
            errors.append(
                f"history_days must be >= 30, got {self.history_days}"
            )

        return errors

    @classmethod
    def from_project(cls) -> Optional[Config]:
        """Load configuration from the original project's Config singleton.

        Returns None if the original project is not importable.
        """
        try:
            from src.config import get_config

            cfg = get_config()

            ai = AIConfig(
                api_key=getattr(cfg, "gemini_api_key", "") or "",
                base_url=getattr(cfg, "gemini_base_url", "") or AIConfig.base_url,
                model=getattr(cfg, "gemini_model", "") or AIConfig.model,
                temperature=getattr(cfg, "gemini_temperature", TEMPERATURE_DEFAULT),
                max_retries=getattr(cfg, "gemini_max_retries", API_MAX_RETRIES),
                retry_delay=getattr(cfg, "gemini_retry_delay", API_BASE_DELAY),
                provider="gemini",
            )

            stock_codes = list(getattr(cfg, "stock_list", []) or [])

            notify = NotifyConfig(
                webhook_url=getattr(cfg, "wechat_webhook_url", "") or "",
                telegram_bot_token=getattr(cfg, "telegram_bot_token", "") or "",
                telegram_chat_id=getattr(cfg, "telegram_chat_id", "") or "",
                email_sender=getattr(cfg, "email_sender", "") or "",
                email_password=getattr(cfg, "email_password", "") or "",
                email_receivers=list(getattr(cfg, "email_receivers", []) or []),
            )

            return cls(
                stock_codes=stock_codes,
                ai=ai,
                notify=notify,
                data_source="auto",
            )
        except ImportError:
            return None

    @classmethod
    def from_env(cls, env_file: Optional[str] = None) -> Config:
        """Load configuration from environment variables.

        Optionally loads a .env file first.
        """
        if env_file:
            _load_dotenv(env_file)

        stock_codes_raw = os.getenv("STOCK_CODES", "")
        stock_codes = split_csv(stock_codes_raw)

        ai = AIConfig(
            api_key=os.getenv("AI_API_KEY", ""),
            base_url=os.getenv(
                "AI_BASE_URL",
                "https://generativelanguage.googleapis.com/v1beta",
            ),
            model=os.getenv("AI_MODEL", "gemini-2.0-flash"),
            temperature=float(os.getenv("AI_TEMPERATURE", str(TEMPERATURE_DEFAULT))),
            max_retries=int(os.getenv("AI_MAX_RETRIES", str(API_MAX_RETRIES))),
            retry_delay=float(os.getenv("AI_RETRY_DELAY", str(API_BASE_DELAY))),
            provider=os.getenv("AI_PROVIDER", "gemini"),
        )

        email_receivers_raw = os.getenv("EMAIL_RECEIVERS", "")
        email_receivers = split_csv(email_receivers_raw)

        notify = NotifyConfig(
            webhook_url=os.getenv("WEBHOOK_URL", ""),
            telegram_bot_token=os.getenv("TELEGRAM_BOT_TOKEN", ""),
            telegram_chat_id=os.getenv("TELEGRAM_CHAT_ID", ""),
            email_sender=os.getenv("EMAIL_SENDER", ""),
            email_password=os.getenv("EMAIL_PASSWORD", ""),
            email_receivers=email_receivers,
            email_smtp_host=os.getenv("EMAIL_SMTP_HOST", ""),
            email_smtp_port=int(os.getenv("EMAIL_SMTP_PORT", "465")),
        )

        return cls(
            stock_codes=stock_codes,
            ai=ai,
            notify=notify,
            history_days=int(os.getenv("HISTORY_DAYS", "120")),
            max_workers=int(os.getenv("MAX_WORKERS", "3")),
            report_dir=os.getenv("REPORT_DIR", "reports"),
            data_source=os.getenv("DATA_SOURCE", "akshare"),
            log_level=os.getenv("LOG_LEVEL", "INFO"),
        )


def split_csv(raw: str) -> list[str]:
    """Split a comma-separated string, supporting Chinese comma."""
    return [c.strip() for c in raw.replace("，", ",").split(",") if c.strip()]


def _load_dotenv(path: str) -> None:
    """Minimal .env file loader (no external dependency)."""
    env_path = Path(path)
    if not env_path.exists():
        return

    for line in env_path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if not line or line.startswith("#"):
            continue
        if "=" not in line:
            continue
        key, _, value = line.partition("=")
        key = key.strip()
        value = value.strip().strip("\"'")
        if key and key not in os.environ:
            os.environ[key] = value
