# app/security/slack_signature.py
from __future__ import annotations

import hashlib
import hmac
import time

from fastapi import HTTPException, Request

from app.core.config import settings
from app.core.logging import CorrelationAdapter, get_logger

logger = get_logger("slack.security")


async def verify_slack_signature(request: Request) -> None:
    """FastAPI dependency for verifying Slack request signatures."""
    corr_id = getattr(request.state, "corr_id", "no-corr-id")
    log = CorrelationAdapter(logger, corr_id)

    timestamp = request.headers.get("X-Slack-Request-Timestamp")
    signature = request.headers.get("X-Slack-Signature")
    secret = settings.SLACK_SIGNING_SECRET.get_secret_value()

    if not timestamp or not signature or not secret:
        log.error("Missing Slack signature headers or signing secret")
        raise HTTPException(status_code=400, detail="Missing Slack signature")

    # Replay attack protection
    try:
        if abs(time.time() - int(timestamp)) > 60 * 5:
            log.error("Slack signature expired")
            raise HTTPException(status_code=401, detail="Expired Slack signature")
    except Exception:
        log.error("Invalid Slack timestamp")
        raise HTTPException(status_code=400, detail="Invalid Slack timestamp")

    body = (await request.body()).decode()
    base_string = f"v0:{timestamp}:{body}"

    digest = hmac.new(
        secret.encode(),
        base_string.encode(),
        hashlib.sha256,
    ).hexdigest()

    computed = f"v0={digest}"

    if not hmac.compare_digest(computed, signature):
        log.error("Slack signature mismatch")
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    log.info("Slack signature verified")
