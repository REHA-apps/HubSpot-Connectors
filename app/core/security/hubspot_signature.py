# app/core/security/hubspot_signature.py
from __future__ import annotations

import base64
import hashlib
import hmac

from fastapi import HTTPException, Request

from app.core.config import settings
from app.core.logging import CorrelationAdapter, get_logger
from app.utils.constants import ErrorCode

logger = get_logger("hubspot.security")


async def verify_hubspot_signature(request: Request) -> None:
    """FastAPI dependency for verifying HubSpot webhook signatures.

    HubSpot signs:
        scheme + host + path  (NO query params)
        + raw request body

    Signature header:
        X-HubSpot-Signature: base64(hmac_sha256(secret, signed_data))
    """
    corr_id = getattr(request.state, "corr_id", "no-corr-id")
    log = CorrelationAdapter(logger, corr_id)

    signature = request.headers.get("X-HubSpot-Signature")
    if not signature:
        log.error("Missing HubSpot signature header")
        raise HTTPException(
            status_code=ErrorCode.BAD_REQUEST,
            detail="Missing HubSpot signature",
        )

    secret = settings.HUBSPOT_CLIENT_SECRET.get_secret_value()
    if not secret:
        log.error("Missing HubSpot client secret")
        raise HTTPException(
            status_code=ErrorCode.INTERNAL_ERROR,
            detail="Server misconfiguration",
        )

    # Raw body (bytes)
    body = await request.body()

    # HubSpot signs: scheme + host + path (no query params)
    # This is critical when behind proxy like ngrok
    url_base = f"{request.url.scheme}://{request.url.hostname}{request.url.path}"

    signed_data = url_base.encode() + body

    digest = hmac.new(
        secret.encode("utf-8"),
        msg=signed_data,
        digestmod=hashlib.sha256,
    ).digest()

    computed = base64.b64encode(digest).decode()

    if not hmac.compare_digest(computed, signature):
        log.error(
            "HubSpot signature mismatch. URL: %s, Method: %s", url_base, request.method
        )
        raise HTTPException(
            status_code=ErrorCode.UNAUTHORIZED,
            detail="Invalid signature",
        )

    log.info("HubSpot signature verified")
