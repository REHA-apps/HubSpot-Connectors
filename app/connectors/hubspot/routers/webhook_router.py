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


async def verify_hubspot_signature(
    request: Request, x_hubspot_signature: str = Header(None)
) -> None:
    """Verifies the X-HubSpot-Signature header to ensure the request is from HubSpot.
    HubSpot v3 Signature: SHA-256 hash of (client_secret + request_body).
    """
    if not settings.HUBSPOT_CLIENT_SECRET:
        # If secret is not configured, we cannot verify.
        # In prod, this should likely be an error or just log warning.
        logger.warning(
            "HUBSPOT_CLIENT_SECRET not set, skipping signature verification."
        )
        return

    if not x_hubspot_signature:
        raise HTTPException(
            status_code=401, detail="Missing X-HubSpot-Signature header"
        )

    body_bytes = await request.body()
    secret = settings.HUBSPOT_CLIENT_SECRET.get_secret_value().encode("utf-8")

    # Concatenate secret + body
    source = secret + body_bytes

    # Calculate SHA-256 hash
    expected_signature = hashlib.sha256(source).hexdigest()

    if not hmac.compare_digest(expected_signature, x_hubspot_signature):
        logger.error(
            "Invalid HubSpot signature. Expected %s, got %s",
            expected_signature,
            x_hubspot_signature,
        )
        raise HTTPException(status_code=401, detail="Invalid signature")


@router.post("/")
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
