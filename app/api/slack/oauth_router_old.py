from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.core.logging import CorrelationAdapter, get_logger
from app.db.supabase import StorageService
from app.integrations.oauth import OAuthService

router = APIRouter(prefix="/slack/oauth", tags=["slack-oauth"])
logger = get_logger("slack.oauth")


@router.get("/callback")
async def slack_oauth_callback(
    request: Request,
    code: str = Query(...),
    state: str | None = Query(default=None),
) -> dict[str, str]:
    """Slack OAuth callback.

    state:
      - workspace_id (HubSpot-first), or
      - None (Slack-first → create workspace or reuse by team_id)
    """
    corr_id: str = getattr(request.state, "corr_id", "evt_unknown")
    log = CorrelationAdapter(logger, corr_id)

    log.info("Received Slack OAuth callback with code=%s state=%s", code, state)

    try:
        token_data = await OAuthService.exchange_slack_token(code, corr_id=corr_id)
        log.info("Slack token exchange successful")
    except Exception as exc:
        log.error("Slack token exchange failed: %s", exc)
        raise HTTPException(
            status_code=502, detail="Slack token exchange failed"
        ) from exc

    access_token = token_data.get("access_token")
    team = token_data.get("team") or {}
    team_id = team.get("id")

    if access_token is None or not isinstance(access_token, str):
        log.error("Slack OAuth response missing access_token")
        raise HTTPException(status_code=400, detail="Missing access_token")

    if team_id is None or not isinstance(team_id, str):
        log.error("Slack OAuth response missing team.id")
        raise HTTPException(status_code=400, detail="Missing team_id")

    # Resolve workspace
    workspace_id: str | None = None

    # HubSpot-first: state is workspace_id
    storage = StorageService(corr_id=corr_id)

    if state:
        workspace = storage.get_workspace_by_id(state)
        if workspace:
            workspace_id = workspace.id
            log.info("Resolved workspace via state: workspace_id=%s", workspace_id)
        else:
            log.warning(
                "No workspace found for state=%s; creating new workspace", state
            )

    if workspace_id is None:
        # Try existing Slack integration
        integration = storage.get_integration_by_slack_team_id(team_id)
        if integration:
            workspace_id = integration.workspace_id
            log.info(
                "Resolved workspace via existing Slack integration: workspace_id=%s",
                workspace_id,
            )
        else:
            # Slack-first: create workspace
            log.info(
                "No existing workspace; creating workspace for Slack-first install"
            )
            workspace = storage.create_workspace(
                workspace_id=workspace_id,
                primary_email=email,
            )
            workspace_id = workspace.id
            log.info("Created new workspace: workspace_id=%s", workspace_id)

    storage.upsert_slack_integration(
        workspace_id=workspace_id,
        slack_team_id=team_id,
        slack_bot_token=access_token,
    )

    log.info(
        "Slack integration saved: workspace_id=%s team_id=%s",
        workspace_id,
        team_id,
    )

    return {
        "status": "success",
        "message": "Slack connected successfully.",
    }
