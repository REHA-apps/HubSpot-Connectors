# app/api/hubspot/oauth_router.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.core.logging import CorrelationAdapter, get_logger
from app.services.integration_service import IntegrationService

router = APIRouter(prefix="/hubspot/oauth", tags=["hubspot-oauth"])
logger = get_logger("hubspot.oauth")


@router.get("/callback")
async def hubspot_oauth_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
) -> dict[str, str]:
    """HubSpot OAuth callback.
    state = Slack team ID (Slack-first) OR workspace ID (HubSpot-first).
    """
    corr_id: str = getattr(request.state, "corr_id", "evt_unknown")
    log = CorrelationAdapter(logger, corr_id)

    log.info("Received HubSpot OAuth callback code=%s state=%s", code, state)

    try:
        integration_service = IntegrationService(corr_id)

        await integration_service.handle_hubspot_oauth_callback(
            code=code,
            state=state,
        )

        return {
            "status": "success",
            "message": "HubSpot connected successfully.",
        }

    except HTTPException:
        raise

    except Exception as exc:
        log.error("HubSpot OAuth callback failed: %s", exc)
        raise HTTPException(status_code=500, detail="HubSpot OAuth failed") from exc
