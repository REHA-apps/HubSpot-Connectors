# app/core/security/slack_signature.py
from __future__ import annotations

import hashlib
import hmac
import time

from fastapi import HTTPException, Request
from collections.abc import Mapping

from app.core.config import settings
from app.core.logging import CorrelationAdapter, get_logger

logger = get_logger("slack.security")


async def verify_slack_signature(
    headers: Mapping[str, str],
    body: bytes,
    *,
    corr_id: str | None = None,
) -> bool:
    """Verify Slack request signature."""

    log = CorrelationAdapter(logger, corr_id or "no-corr-id")

    timestamp = headers.get("X-Slack-Request-Timestamp")
    signature = headers.get("X-Slack-Signature")
    secret = settings.SLACK_SIGNING_SECRET.get_secret_value()

    if not timestamp or not signature or not secret:
        log.error("Missing Slack signature headers or signing secret")
        return False

    # Slack signing base string
    basestring = f"v0:{timestamp}:{body.decode()}"

    # Compute HMAC SHA256
    computed = "v0=" + hmac.new(
        secret.encode(),
        basestring.encode(),
        hashlib.sha256,
    ).hexdigest()

    if not hmac.compare_digest(computed, signature):
        log.error("Slack signature mismatch")
        return False

    return True