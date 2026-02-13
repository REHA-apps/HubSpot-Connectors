# app/integrations/security.py
from __future__ import annotations

import base64
import hashlib
import hmac
import time
from collections.abc import Mapping

from app.core.config import settings
from app.core.logging import CorrelationAdapter, get_logger

hubspot_log = get_logger("hubspot.security")
slack_log = get_logger("slack.security")


# ----------------------------------------------------------------------
# HubSpot Signature Verification
# ----------------------------------------------------------------------
def verify_hubspot_signature(
    signature: str,
    request_body: bytes,
    url: str,
    *,
    corr_id: str | None = None,
) -> bool:
    """Verify HubSpot webhook signature.

    HubSpot expects:
        signature = base64(hmac_sha256(secret, url + body))
    """
    log = CorrelationAdapter(hubspot_log, corr_id or "no-corr-id")

    secret = settings.HUBSPOT_CLIENT_SECRET.get_secret_value()
    if not secret:
        log.error("Missing HubSpot client secret")
        return False

    if not signature or len(signature) < 20:
        log.error("Invalid or missing HubSpot signature")
        return False

    # HubSpot signs: raw URL + raw body bytes
    signed_data = url.encode() + request_body

    digest = hmac.new(
        secret.encode(),
        msg=signed_data,
        digestmod=hashlib.sha256,
    ).digest()

    computed = base64.b64encode(digest).decode()

    if not hmac.compare_digest(computed, signature):
        log.error("HubSpot signature mismatch")
        return False

    log.info("HubSpot signature verified")
    return True


# ----------------------------------------------------------------------
# Slack Signature Verification
# ----------------------------------------------------------------------
def verify_slack_signature(
    headers: Mapping[str, str],
    body: bytes,
    *,
    corr_id: str | None = None,
) -> bool:
    """Verify Slack request signature.

    Slack signs:
        v0:{timestamp}:{raw_body}
    """
    log = CorrelationAdapter(slack_log, corr_id or "no-corr-id")

    timestamp = headers.get("X-Slack-Request-Timestamp")
    signature = headers.get("X-Slack-Signature")
    secret = settings.SLACK_SIGNING_SECRET.get_secret_value()

    if not timestamp or not signature or not secret:
        log.error("Missing Slack signature headers or signing secret")
        return False

    # Reject replay attacks (older than 5 minutes)
    try:
        if abs(time.time() - int(timestamp)) > 60 * 5:
            log.error("Slack signature expired (timestamp too old)")
            return False
    except (ValueError, TypeError):
        log.error("Invalid Slack timestamp")
        return False

    base_string = f"v0:{timestamp}:{body.decode()}"

    digest = hmac.new(
        secret.encode(),
        base_string.encode(),
        hashlib.sha256,
    ).hexdigest()

    computed = f"v0={digest}"

    if not hmac.compare_digest(computed, signature):
        log.error("Slack signature mismatch")
        return False

    log.info("Slack signature verified")
    return True
