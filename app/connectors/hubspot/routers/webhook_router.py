from __future__ import annotations

import hashlib
import hmac
import uuid

from fastapi import APIRouter, Depends, Header, HTTPException, Request

from app.core.config import settings
from app.core.logging import get_logger
from app.domains.crm.notification_service import NotificationService

router = APIRouter(prefix="/hubspot/webhooks", tags=["hubspot_webhooks"])
logger = get_logger("hubspot.webhooks")

# HubSpot signature version header values
_SIG_V1 = "v1"
_SIG_V2 = "v2"
_SIG_V3 = "v3"


async def verify_hubspot_signature(
    request: Request,
    x_hubspot_signature: str | None = Header(None),
    x_hubspot_signature_v3: str | None = Header(None),
    x_hubspot_request_timestamp: str | None = Header(None),
    x_hubspot_signature_version: str = Header(_SIG_V1),
) -> None:
    """Verify the HubSpot webhook signature."""
    if not settings.HUBSPOT_CLIENT_SECRET:
        logger.warning(
            "HUBSPOT_CLIENT_SECRET not set, skipping signature verification."
        )
        return

    signature = x_hubspot_signature_v3 or x_hubspot_signature
    if not signature:
        raise HTTPException(status_code=401, detail="Missing HubSpot signature header")

    body_bytes = await request.body()
    secret = settings.HUBSPOT_CLIENT_SECRET.get_secret_value()
    version = x_hubspot_signature_version.lower()

    # Build the canonical URL for signing (scheme + host + path, no query params)
    # This is critical for V3 and V2 when behind proxies like ngrok
    url_base = f"{request.url.scheme}://{request.url.hostname}{request.url.path}"

    if version == _SIG_V3 and x_hubspot_signature_v3:
        if not x_hubspot_request_timestamp:
            raise HTTPException(
                status_code=401, detail="Missing timestamp for v3 signature"
            )

        # v3: HMAC-SHA-256(secret, method + URL + body + timestamp)
        source_bytes = (
            request.method.encode()
            + url_base.encode()
            + body_bytes
            + x_hubspot_request_timestamp.encode()
        )
        expected = hmac.new(
            secret.encode("utf-8"),
            source_bytes,
            hashlib.sha256,
        ).hexdigest()
        signature_to_check = x_hubspot_signature_v3

    elif version == _SIG_V2:
        # v2: SHA-256(secret + method + URL + body)
        source_string = (
            secret
            + request.method
            + url_base
            + body_bytes.decode("utf-8", errors="replace")
        )
        expected = hashlib.sha256(source_string.encode("utf-8")).hexdigest()
        signature_to_check = x_hubspot_signature or ""

    else:
        # v1: SHA-256(secret + body)
        source_bytes = secret.encode("utf-8") + body_bytes
        expected = hashlib.sha256(source_bytes).hexdigest()
        signature_to_check = x_hubspot_signature or ""

    if not hmac.compare_digest(expected, signature_to_check):
        logger.error(
            "HubSpot signature mismatch (version=%s). "
            "URL: %s, Method: %s. Expected: %s, Received: %s",
            version,
            url_base,
            request.method,
            expected,
            signature_to_check,
        )
        # Log headers for deep debugging if signature fails
        logger.debug("Request Headers: %s", dict(request.headers))
        raise HTTPException(status_code=401, detail="Invalid signature")


@router.post("")
async def handle_hubspot_events(
    request: Request,
    _: None = Depends(verify_hubspot_signature),
) -> dict[str, str]:
    """Receives and processes HubSpot webhook events."""
    try:
        events = await request.json()
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid JSON body")

    if not isinstance(events, list):
        # HubSpot sends an array of events
        events = [events]

    # Use a shared correlation ID for this batch of events
    corr_id = f"hs-hook-{uuid.uuid4().hex[:8]}"
    service = NotificationService(corr_id=corr_id)

    logger.info("Received %d HubSpot events (corr_id=%s)", len(events), corr_id)

    # Process events sequentially (could be async/backgrounded for scale)
    for event in events:
        try:
            await service.handle_event(event)
        except Exception as exc:
            logger.error("Failed to process event: %s", exc, exc_info=True)

    return {"status": "processed"}
