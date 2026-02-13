# app/utils/slack_helpers.py
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.core.logging import CorrelationAdapter, get_logger
from app.utils.helpers import HTTPClient

logger = get_logger("utils.slack")


async def send_slack_response(
    response_url: str,
    content: Mapping[str, Any],
    *,
    corr_id: str | None = None,
) -> None:
    """Send a JSON response to Slack via response_url.
    Includes correlation-ID aware logging.
    """
    log = CorrelationAdapter(logger, corr_id or "no-corr-id")

    client = HTTPClient.get_client(corr_id=corr_id)

    try:
        log.info("Sending Slack response to response_url")
        response = await client.post(response_url, json=content)
        response.raise_for_status()
        log.info("Slack response sent successfully")

    except Exception as exc:
        log.error("Failed to send Slack response: %s", exc)


async def send_slack_error(
    response_url: str,
    message: str,
    *,
    corr_id: str | None = None,
) -> None:
    """Send an error message to Slack."""
    await send_slack_response(
        response_url,
        {"text": f"❌ {message}"},
        corr_id=corr_id,
    )


async def send_delayed_slack_response(
    response_url: str,
    payload: Mapping[str, Any],
    *,
    corr_id: str | None = None,
) -> None:
    """Send delayed Slack response (used for background tasks)."""
    log = CorrelationAdapter(logger, corr_id or "no-corr-id")

    client = HTTPClient.get_client(corr_id=corr_id)

    try:
        log.info("Sending delayed Slack response")
        await client.post(response_url, json=payload)
        log.info("Delayed Slack response sent successfully")

    except Exception as exc:
        log.error("Failed to send delayed Slack response: %s", exc)
