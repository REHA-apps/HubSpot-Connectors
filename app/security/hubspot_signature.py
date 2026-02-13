# app/security/hubspot_signature.py
from __future__ import annotations

import base64
import hashlib
import hmac

from fastapi import HTTPException, Request

from app.core.config import settings
from app.core.logging import CorrelationAdapter, get_logger

logger = get_logger("hubspot.security")


async def verify_hubspot_signature(request: Request) -> None:
    """FastAPI dependency for verifying HubSpot webhook signatures."""
    corr_id = getattr(request.state, "corr_id", "no-corr-id")
    log = CorrelationAdapter(logger, corr_id)

    signature = request.headers.get("X-HubSpot-Signature")
    if not signature:
        log.error("Missing HubSpot signature header")
        raise HTTPException(status_code=400, detail="Missing HubSpot signature")

    secret = settings.HUBSPOT_CLIENT_SECRET.get_secret_value()
    if not secret:
        log.error("Missing HubSpot client secret")
        raise HTTPException(status_code=500, detail="Server misconfiguration")

    body = await request.body()
    url = str(request.url)

    signed_data = url.encode() + body

    digest = hmac.new(
        secret.encode(),
        msg=signed_data,
        digestmod=hashlib.sha256,
    ).digest()

    computed = base64.b64encode(digest).decode()

    if not hmac.compare_digest(computed, signature):
        log.error("HubSpot signature mismatch")
        raise HTTPException(status_code=401, detail="Invalid signature")

    log.info("HubSpot signature verified")
