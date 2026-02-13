# app/api/hubspot/webhook_router.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.connectors.hubspot_connector import HubSpotConnector
from app.core.logging import CorrelationAdapter, get_logger
from app.integrations.security import verify_hubspot_signature

router = APIRouter(prefix="/hubspot", tags=["hubspot-webhooks"])
logger = get_logger("hubspot.webhooks")


async def get_hubspot_connector(request: Request) -> HubSpotConnector:
    corr_id: str = getattr(request.state, "corr_id", "evt_unknown")
    team_id = request.headers.get("X-Slack-Team-Id")

    return HubSpotConnector(
        slack_team_id=team_id,
        corr_id=corr_id,
    )


@router.post("/webhook", dependencies=[Depends(verify_hubspot_signature)])
async def hubspot_webhook(
    request: Request,
    connector: HubSpotConnector = Depends(get_hubspot_connector),
) -> dict[str, str]:
    corr_id: str = getattr(request.state, "corr_id", "evt_unknown")
    log = CorrelationAdapter(logger, corr_id)

    try:
        payload = await request.json()
        log.info("Received HubSpot webhook event")

        result = await connector.handle_event(payload)
        return {"status": "ok", **result}

    except Exception as exc:
        log.error("HubSpot webhook failed: %s", exc)
        raise HTTPException(status_code=500, detail="Webhook processing failed")
