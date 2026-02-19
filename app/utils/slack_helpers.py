from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.core.logging import CorrelationAdapter, get_logger
from app.utils.helpers import HTTPClient

logger = get_logger("utils.slack")


# Core Slack response_url integration
async def send_slack_response(
    response_url: str,
    content: Mapping[str, Any],
    *,
    corr_id: str | None = None,
) -> None:
    """Description:
        Dispatches an asynchronous JSON payload to a Slack response_url.

    Args:
        response_url (str): The specific endpoint provided by Slack for background
                            responses.
        content (Mapping[str, Any]): The message payload (text, blocks, etc.).
        corr_id (str | None): Optional correlation ID for tracking.

    Returns:
        None

    Rules Applied:
        - Utilizes the global HTTPClient singleton.
        - Handles both immediate and delayed command responses.

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


# Specialized error handling
async def send_slack_error(
    response_url: str,
    message: str,
    *,
    corr_id: str | None = None,
) -> None:
    """Description:
        Sends a standardized error message notification to Slack.

    Args:
        response_url (str): Target response URL.
        message (str): The error description.
        corr_id (str | None): Correlation ID.

    Returns:
        None

    """
    await send_slack_response(
        response_url,
        {"text": f"❌ {message}"},
        corr_id=corr_id,
    )
