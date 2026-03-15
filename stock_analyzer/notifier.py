"""Multi-channel notification — webhook, Telegram, email."""

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
    """Send notification to all enabled channels. Returns per-channel results."""
    results: list[NotifyResult] = []

    # Channel registry: (name, enabled_check, send_function)
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
    # Telegram has a 4096 char limit, truncate if needed
    message = f"*{title}*\n\n{content}"
    if len(message) > 4000:
        message = message[:3997] + "..."

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

    smtp_host = config.email_smtp_host
    if not smtp_host:
        # Auto-detect from email domain
        domain = config.email_sender.split("@")[-1]
        smtp_host = _guess_smtp_host(domain)

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
    """Guess SMTP host from email domain."""
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
