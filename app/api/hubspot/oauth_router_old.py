# app/api/hubspot/oauth_router.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.core.logging import CorrelationAdapter, get_logger
from app.db.supabase import StorageService
from app.integrations.oauth import OAuthService

router = APIRouter(prefix="/hubspot/oauth", tags=["hubspot-oauth"])
logger = get_logger("hubspot.oauth")


@router.get("/callback")
async def hubspot_oauth_callback(
    request: Request,
    code: str = Query(...),
    state: str = Query(...),  # Slack team ID OR workspace ID
) -> dict[str, str]:
    """HubSpot OAuth callback.

    state = Slack team ID (Slack-first) OR workspace ID (HubSpot-first).
    """
    corr_id: str = getattr(request.state, "corr_id", "evt_unknown")
    log = CorrelationAdapter(logger, corr_id)

    log.info("Received HubSpot OAuth callback with code=%s state=%s", code, state)

    try:
        # 1. Exchange OAuth code for tokens
        token_data = await OAuthService.exchange_hubspot_token(code)
        log.info("HubSpot token exchange successful")

        access_token = token_data.get("access_token")
        refresh_token = token_data.get("refresh_token")
        portal_id_raw = token_data.get("portal_id")
        portal_id = str(portal_id_raw) if portal_id_raw is not None else None

        if access_token is None:
            log.error("HubSpot OAuth response missing access_token")
            raise HTTPException(status_code=400, detail="Missing access_token")

        if portal_id is None:
            log.error("HubSpot OAuth response missing portal_id")
            raise HTTPException(status_code=400, detail="Missing portal_id")

        # 2. Resolve workspace
        # Slack-first install → state = Slack team ID
        storage = StorageService(corr_id=corr_id)
        slack_integration = storage.get_integration_by_slack_team_id(state)

        if slack_integration:
            workspace_id = slack_integration.workspace_id
            log.info(
                "Resolved workspace via Slack integration: workspace_id=%s",
                workspace_id,
            )
        else:
            # HubSpot-first install → create workspace
            log.info(
                "No Slack integration found; creating workspace for HubSpot-first install"
            )
            workspace = storage.create_workspace()
            workspace_id = workspace.id
            log.info("Created new workspace: workspace_id=%s", workspace_id)

        # 3. Upsert HubSpot integration
        storage.upsert_hubspot_integration(
            workspace_id=workspace_id,
            portal_id=portal_id,
            access_token=access_token,
            refresh_token=refresh_token,
        )

        log.info(
            "HubSpot integration saved: workspace_id=%s portal_id=%s",
            workspace_id,
            portal_id,
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
