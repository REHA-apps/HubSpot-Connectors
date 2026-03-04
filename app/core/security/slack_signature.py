# app/core/security/slack_signature.py
from __future__ import annotations

import hashlib
import hmac
import time
from collections.abc import Mapping

from fastapi import HTTPException

from app.core.config import settings
from app.core.logging import get_logger
from app.utils.constants import ErrorCode

logger = get_logger("slack.security")


async def verify_slack_signature(
    headers: Mapping[str, str],
    body: bytes,
    *,
    corr_id: str | None = None,
) -> None:
    """Verify Slack request signature.

    Slack signs:
        v0:{timestamp}:{raw_body}

    Signature header:
        X-Slack-Signature: v0=hex(hmac_sha256(secret, basestring))

    Timestamp must be within 5 minutes to prevent replay attacks.
    """
    timestamp = headers.get("X-Slack-Request-Timestamp")
    signature = headers.get("X-Slack-Signature")
    secret = settings.SLACK_SIGNING_SECRET.get_secret_value()

    if not timestamp or not signature:
        logger.error("Missing Slack signature headers")
        raise HTTPException(
            status_code=ErrorCode.UNAUTHORIZED,
            detail="Missing Slack signature headers",
        )

    if not secret:
        logger.error("Missing Slack signing secret")
        raise HTTPException(
            status_code=ErrorCode.INTERNAL_ERROR,
            detail="Server misconfiguration",
        )

    # ---------------------------------------------------------
    # Replay attack protection (Slack recommends 5 minutes)
    # ---------------------------------------------------------
    try:
        ts = int(timestamp)
    except ValueError:
        logger.error("Invalid Slack timestamp")
        raise HTTPException(
            status_code=ErrorCode.UNAUTHORIZED,
            detail="Invalid Slack timestamp",
        )

    if abs(time.time() - ts) > 60 * 5:
        logger.error("Slack request timestamp too old")
        raise HTTPException(
            status_code=ErrorCode.UNAUTHORIZED,
            detail="Slack request timestamp too old",
        )

    # ---------------------------------------------------------
    # Compute Slack signature
    # ---------------------------------------------------------
    basestring = f"v0:{timestamp}:{body.decode()}"

    computed = (
        "v0="
        + hmac.new(
            secret.encode(),
            basestring.encode(),
            hashlib.sha256,
        ).hexdigest()
    )

    if not hmac.compare_digest(computed, signature):
        logger.error("Slack signature mismatch")
        raise HTTPException(
            status_code=ErrorCode.UNAUTHORIZED,
            detail="Invalid Slack signature",
        )

    logger.info("Slack signature verified")
