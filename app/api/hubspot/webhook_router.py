# app/api/hubspot/webhook_router.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.logging import CorrelationAdapter, get_logger
from app.core.security.hubspot_signature import verify_hubspot_signature
from app.services.event_router import EventRouter
from app.services.integration_service import IntegrationService
from app.utils.constants import BAD_REQUEST_ERROR, INTERNAL_SERVER_ERROR

router = APIRouter(prefix="/hubspot", tags=["hubspot-webhooks"])
logger = get_logger("hubspot.webhooks")


@router.post("/webhook", dependencies=[Depends(verify_hubspot_signature)])
async def hubspot_webhook(request: Request) -> dict[str, str]:
    corr_id: str = getattr(request.state, "corr_id", "evt_unknown")
    log = CorrelationAdapter(logger, corr_id)

    try:
        payload = await request.json()
        log.info("Received HubSpot webhook event")

        portal_id = payload.get("portalId")
        if not portal_id:
            log.error("Missing portalId in HubSpot webhook")
            raise HTTPException(
                status_code=BAD_REQUEST_ERROR, detail="Missing portalId"
            )

        # Resolve workspace
        integration_service = IntegrationService(corr_id)
        workspace_id = await integration_service.resolve_workspace(portal_id)

        # Route event
        event_router = EventRouter(corr_id)
        await event_router.route_hubspot_object_to_slack(
            workspace_id=workspace_id,
            obj=payload,
            channel=None,  # ChannelService decides where to send
        )

        return {"status": "ok"}

    except Exception as exc:
        log.error("HubSpot webhook failed: %s", exc)
        raise HTTPException(
            status_code=INTERNAL_SERVER_ERROR, detail="Webhook processing failed"
        )
