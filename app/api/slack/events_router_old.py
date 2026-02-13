# app/api/slack/events_router.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Request

from app.core.logging import CorrelationAdapter, get_logger
from app.db.supabase import StorageService

router = APIRouter(prefix="/slack", tags=["slack-events"])
logger = get_logger("slack.events")


@router.post("/events")
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

    log.info("Slack event type=%s", event_type)

    # 1. Handle uninstall event
    if event_type == "app_uninstalled":
        team_id = payload.get("team_id")

        if not team_id:
            log.error("Missing team_id in uninstall event")
            return {"status": "missing_team_id"}

        log.info("Processing Slack uninstall for team_id=%s", team_id)

        storage = StorageService(corr_id=corr_id)
        integration = storage.get_integration_by_slack_team_id(team_id)

        if integration:
            storage.delete_integration(
                workspace_id=integration.workspace_id,
                provider="slack",
            )
            log.info(
                "Slack integration removed for workspace_id=%s",
                integration.workspace_id,
            )
        else:
            log.warning("No Slack integration found for team_id=%s", team_id)

        return {"status": "ok"}

    # 2. Ignore all other events
    log.info("Slack event ignored (not uninstall)")
    return {"status": "ignored"}
