# app/api/hubspot/oauth_router.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from app.core.dependencies import get_integration_service
from app.core.logging import CorrelationAdapter, get_corr_id, get_logger
from app.db.records import Provider
from app.domains.crm.integration_service import IntegrationService
from app.utils.constants import ErrorCode
from app.utils.ui import render_success_page

router = APIRouter(prefix="/hubspot/oauth", tags=["hubspot-oauth"])
logger = get_logger("hubspot.oauth")


@router.get("/callback")
async def hubspot_oauth_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),
    corr_id: str = Depends(get_corr_id),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> Any:
    log = CorrelationAdapter(logger, corr_id)
    log.info("Received HubSpot OAuth callback code=%s state=%s", code, state)

    error = request.query_params.get("error")
    if error:
        log.warning("HubSpot OAuth error=%s", error)
        raise HTTPException(
            status_code=ErrorCode.BAD_REQUEST, detail=f"HubSpot OAuth error: {error}"
        )

    try:
        workspace_id = await integration_service.handle_hubspot_oauth_callback(
            code=code,
            state=state,
        )

        slack_integration = await integration_service.get_integration(
            workspace_id, Provider.SLACK
        )
        if not slack_integration:
            log.info("Redirecting to Slack install to bridge connection")
            return RedirectResponse(url=f"/api/slack/install?state={workspace_id}")

        return render_success_page(
            title="Connection Successful",
            message=(
                "HubSpot has been linked successfully. "
                "Your cross-platform CRM integration is now active."
            ),
            workspace_id=workspace_id,
        )

    except HTTPException:
        raise
    except Exception as exc:
        log.error("HubSpot OAuth callback failed: %s", exc)
        raise HTTPException(
            status_code=ErrorCode.INTERNAL_ERROR, detail="HubSpot OAuth failed"
        ) from exc
