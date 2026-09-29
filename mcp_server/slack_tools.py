"""Slack notification through an incoming webhook.

A webhook URL is enough for the demo: no OAuth install, no bot token, and no
workspace-wide scope. The trade-off is that it can only post to the channel the
webhook was created for, which is exactly what "notify the finance team" needs.
"""

from __future__ import annotations

import os

import requests

DEFAULT_TIMEOUT = 15


class SlackError(RuntimeError):
    """Raised when the webhook is missing or the post fails."""


def webhook_url() -> str:
    url = (os.environ.get("SLACK_WEBHOOK_URL") or "").strip()
    if not url:
        raise SlackError(
            "SLACK_WEBHOOK_URL is not set. Create an incoming webhook in your Slack "
            "app and put the URL in .env."
        )
    return url


def finance_channel() -> str:
    """Display label used in spoken confirmations. The webhook decides the real one."""
    return (os.environ.get("SLACK_FINANCE_CHANNEL") or "#finance").strip() or "#finance"


def post_message(text: str) -> dict[str, object]:
    response = requests.post(webhook_url(), json={"text": text}, timeout=DEFAULT_TIMEOUT)
    if response.status_code >= 300:
        raise SlackError(f"Slack webhook returned HTTP {response.status_code}: {response.text[:200]}")
    return {"ok": True, "status": response.status_code, "channel": finance_channel()}
