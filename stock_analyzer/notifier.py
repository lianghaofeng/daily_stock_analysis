"""Multi-channel notification — delegates to the original project's NotificationService.

The original project supports 8+ channels (WeChat, Feishu, Telegram, Email,
Pushover, PushPlus, Discord, Custom Webhooks) with auto-detection and failover.
We reuse that when available, and fall back to a minimal standalone
implementation (webhook + Telegram + email) when running independently.
"""

from __future__ import annotations

import json
import logging
import smtplib
import urllib.request
import urllib.error
from dataclasses import dataclass
from email.mime.text import MIMEText
from typing import Optional

from .config import NotifyConfig

logger = logging.getLogger(__name__)


@dataclass
class NotifyResult:
    """Result of a notification attempt."""

    channel: str
    success: bool
    error: str = ""


def send_all(config: NotifyConfig, title: str, content: str) -> list[NotifyResult]:
    """Send notification to all enabled channels.

    Tries the original project's NotificationService first (8+ channels).
    Falls back to standalone senders when not available.
    """
    # Try original project's NotificationService first
    results = _try_project_notify(title, content)
    if results is not None:
        return results

    # Fallback: standalone minimal notification
    return _standalone_send_all(config, title, content)


def _try_project_notify(title: str, content: str) -> Optional[list[NotifyResult]]:
    """Try using the original project's NotificationService."""
    try:
        from src.notification import NotificationService

        service = NotificationService()
        if not service.is_available():
            return None

        channel_names = service.get_channel_names()
        logger.info("Using original NotificationService (%s)", channel_names)

        # The original service has its own send methods for markdown
        # We call send_to_all directly
        success = service.send_to_all(content)
        return [
            NotifyResult(
                channel=channel_names,
                success=success,
                error="" if success else "Send failed",
            )
        ]
    except ImportError:
        return None
    except Exception as e:
        logger.warning("Original NotificationService failed: %s", e)
        return None


# ──────────────────────────────────────────────────
# Standalone fallback implementation
# ──────────────────────────────────────────────────


def _standalone_send_all(
    config: NotifyConfig, title: str, content: str
) -> list[NotifyResult]:
    """Standalone notification for running outside the original project."""
    results: list[NotifyResult] = []

    channels = [
        ("webhook", config.webhook_enabled, _send_webhook),
        ("telegram", config.telegram_enabled, _send_telegram),
        ("email", config.email_enabled, _send_email),
    ]

    for name, enabled, send_fn in channels:
        if not enabled:
            continue
        try:
            send_fn(config, title, content)
            results.append(NotifyResult(channel=name, success=True))
            logger.info("Notification sent via %s", name)
        except Exception as e:
            results.append(NotifyResult(channel=name, success=False, error=str(e)))
            logger.error("Failed to send via %s: %s", name, e)

    if not results:
        logger.warning("No notification channels configured")

    return results


def _send_webhook(config: NotifyConfig, title: str, content: str) -> None:
    """Send to generic webhook (supports WeChat/Feishu/DingTalk format)."""
    payload = {
        "msgtype": "markdown",
        "markdown": {"title": title, "text": content},
    }

    data = json.dumps(payload, ensure_ascii=False).encode("utf-8")
    req = urllib.request.Request(
        config.webhook_url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read().decode("utf-8"))
        errcode = result.get("errcode", result.get("code", 0))
        if errcode != 0:
            raise RuntimeError(f"Webhook error: {result}")


def _send_telegram(config: NotifyConfig, title: str, content: str) -> None:
    """Send via Telegram Bot API."""
    TELEGRAM_MSG_LIMIT = 4096
    message = f"*{title}*\n\n{content}"
    if len(message) > TELEGRAM_MSG_LIMIT - 96:
        message = message[: TELEGRAM_MSG_LIMIT - 99] + "..."

    url = f"https://api.telegram.org/bot{config.telegram_bot_token}/sendMessage"
    payload = {
        "chat_id": config.telegram_chat_id,
        "text": message,
        "parse_mode": "Markdown",
    }

    data = json.dumps(payload).encode("utf-8")
    req = urllib.request.Request(
        url,
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=15) as resp:
        result = json.loads(resp.read().decode("utf-8"))
        if not result.get("ok"):
            raise RuntimeError(f"Telegram error: {result}")


def _send_email(config: NotifyConfig, title: str, content: str) -> None:
    """Send via SMTP email."""
    msg = MIMEText(content, "plain", "utf-8")
    msg["Subject"] = title
    msg["From"] = config.email_sender
    msg["To"] = ", ".join(config.email_receivers)

    smtp_host = config.email_smtp_host or _guess_smtp_host(
        config.email_sender.split("@")[-1]
    )

    if config.email_smtp_port == 465:
        server = smtplib.SMTP_SSL(smtp_host, config.email_smtp_port, timeout=15)
    else:
        server = smtplib.SMTP(smtp_host, config.email_smtp_port, timeout=15)
        server.starttls()

    try:
        server.login(config.email_sender, config.email_password)
        server.sendmail(
            config.email_sender, config.email_receivers, msg.as_string()
        )
    finally:
        server.quit()


def _guess_smtp_host(domain: str) -> str:
    """Guess SMTP host from email domain.

    The original project's notification.py has a more complete SMTP_CONFIGS map;
    this is a minimal fallback for standalone use.
    """
    known = {
        "qq.com": "smtp.qq.com",
        "163.com": "smtp.163.com",
        "126.com": "smtp.126.com",
        "gmail.com": "smtp.gmail.com",
        "outlook.com": "smtp-mail.outlook.com",
        "hotmail.com": "smtp-mail.outlook.com",
        "yahoo.com": "smtp.mail.yahoo.com",
    }
    return known.get(domain, f"smtp.{domain}")
