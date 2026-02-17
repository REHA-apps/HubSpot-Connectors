# app/api/hubspot/oauth_router.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Query, Request   

from app.core.logging import CorrelationAdapter, get_logger, get_corr_id
from app.services.integration_service import IntegrationService
from app.utils.constants import ErrorCode

router = APIRouter(prefix="/hubspot/oauth", tags=["hubspot-oauth"])
logger = get_logger("hubspot.oauth")


@router.get("/callback")
async def hubspot_oauth_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    corr_id: str = Depends(get_corr_id),
) -> dict[str, str]:
    """HubSpot OAuth callback."""
    log = CorrelationAdapter(logger, corr_id)

    log.info("Received HubSpot OAuth callback code=%s state=%s", code, state)

    # Optional: handle HubSpot OAuth errors
    error = request.query_params.get("error")
    if error:
        log.warning("HubSpot OAuth error=%s", error)
        raise HTTPException(
            status_code=ErrorCode.BAD_REQUEST, detail=f"HubSpot OAuth error: {error}"
        )

    try:
        integration_service = IntegrationService(corr_id)

        workspace_id = await integration_service.handle_hubspot_oauth_callback(
            code=code,
            state=state,
        )

        return {
            "status": "success",
            "message": "HubSpot connected successfully.",
            "workspace_id": workspace_id,
        }

    except HTTPException:
        raise

    except Exception as exc:
        log.error("HubSpot OAuth callback failed: %s", exc)
        raise HTTPException(
            status_code=ErrorCode.INTERNAL_ERROR, detail="HubSpot OAuth failed"
        ) from exc
