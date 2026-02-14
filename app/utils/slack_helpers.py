# app/utils/slack_helpers.py
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.core.logging import CorrelationAdapter, get_logger
from app.utils.helpers import HTTPClient

logger = get_logger("utils.slack")


# ---------------------------------------------------------
# Core Slack response_url sender
# ---------------------------------------------------------
async def send_slack_response(
    response_url: str,
    content: Mapping[str, Any],
    *,
    corr_id: str | None = None,
) -> None:
    """Send a JSON response to Slack via response_url.

    This is used for:
    - immediate ephemeral responses
    - delayed background responses
    - slash command acknowledgements
    """
    log = CorrelationAdapter(logger, corr_id or "no-corr-id")
    client = HTTPClient.get_client(corr_id=corr_id)

    try:
        log.info("Sending Slack response to response_url")
        resp = await client.post(response_url, json=content)
        resp.raise_for_status()
        log.info("Slack response sent successfully")

    except Exception as exc:
        log.error("Failed to send Slack response: %s", exc)


# ---------------------------------------------------------
# Error helper
# ---------------------------------------------------------
async def send_slack_error(
    response_url: str,
    message: str,
    *,
    corr_id: str | None = None,
) -> None:
    """Send an error message to Slack via response_url."""
    await send_slack_response(
        response_url,
        {"text": f"❌ {message}"},
        corr_id=corr_id,
    )


# ---------------------------------------------------------
# Delayed response helper
# ---------------------------------------------------------
async def send_delayed_slack_response(
    response_url: str,
    payload: Mapping[str, Any],
    *,
    corr_id: str | None = None,
) -> None:
    """Send a delayed Slack response (used for background tasks).

    This is functionally identical to send_slack_response,
    but kept for semantic clarity.
    """
    log = CorrelationAdapter(logger, corr_id or "no-corr-id")
    log.info("Sending delayed Slack response")

    await send_slack_response(
        response_url,
        payload,
        corr_id=corr_id,
    )
