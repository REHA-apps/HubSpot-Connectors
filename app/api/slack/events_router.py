# app/api/slack/events_router.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.logging import CorrelationAdapter, get_logger
from app.security.slack_signature import verify_slack_signature
from app.services.integration_service import IntegrationService

router = APIRouter(prefix="/slack", tags=["slack-events"])
logger = get_logger("slack.events")


@router.post(
    "/events",
    dependencies=[Depends(verify_slack_signature)],
)
async def slack_events(request: Request) -> dict[str, str]:
    """Handles Slack Events API callbacks.
    Supports:
    - app_uninstalled → remove Slack integration
    """
    corr_id: str = getattr(request.state, "corr_id", "evt_unknown")
    log = CorrelationAdapter(logger, corr_id)

    try:
        payload = await request.json()
        log.info("Received Slack event payload")

    except Exception as exc:
        log.error("Failed to parse Slack event payload: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid JSON payload")

    event = payload.get("event", {})
    event_type = event.get("type")
    team_id = payload.get("team_id")

    log.info("Slack event type=%s team_id=%s", event_type, team_id)

    # ---------------------------------------------------------
    # Handle uninstall event
    # ---------------------------------------------------------
    if event_type == "app_uninstalled":
        if not team_id:
            log.error("Missing team_id in uninstall event")
            return {"status": "missing_team_id"}

        log.info("Processing Slack uninstall for team_id=%s", team_id)

        integration_service = IntegrationService(corr_id)
        try:
            # Resolve workspace via Slack integration
            workspace_id = integration_service.resolve_workspace(team_id)
            integration_service.uninstall_slack(workspace_id)
            log.info("Slack integration removed for workspace_id=%s", workspace_id)

        except Exception as exc:
            log.warning("Slack uninstall failed: %s", exc)

        return {"status": "ok"}

    # ---------------------------------------------------------
    # Ignore all other events
    # ---------------------------------------------------------
    log.info("Slack event ignored (not uninstall)")
    return {"status": "ignored"}
