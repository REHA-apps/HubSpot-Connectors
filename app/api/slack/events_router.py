from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response

from app.core.logging import CorrelationAdapter, get_logger, get_corr_id
from app.core.security.slack_signature import verify_slack_signature
from app.services.integration_service import IntegrationService
from app.utils.constants import ErrorCode

router = APIRouter(prefix="/slack", tags=["slack-events"])
logger = get_logger("slack.events")


@router.post(
    "/events",
    # dependencies=[Depends(verify_slack_signature)],
)
async def slack_events(request: Request, corr_id: str = Depends(get_corr_id)):
    """Handles Slack Events API callbacks.
    Supports:
    - url_verification
    - app_uninstalled
    """
    log = CorrelationAdapter(logger, corr_id)

    try:
        raw_body = await request.body()
        payload = await request.json()
        log.info("Received Slack event payload")
    except Exception as exc:
        log.error("Failed to parse Slack event payload: %s", exc)
        raise HTTPException(
            status_code=ErrorCode.BAD_REQUEST, detail="Invalid JSON payload"
        )

    # ---------------------------------------------------------
    # Slack URL verification challenge
    # ---------------------------------------------------------
    if payload.get("type") == "url_verification":
        challenge = payload["challenge"]
        log.info("Responding to Slack challenge")
        return Response(content=challenge, media_type="text/plain")

    # ---------------------------------------------------------
    # Normal event handling
    # ---------------------------------------------------------
    await verify_slack_signature(
        headers=request.headers,
        body=raw_body,
        corr_id=corr_id,
    )
    event = payload.get("event", {})
    event_type = event.get("type")
    team_id = payload.get("team_id")

    log.info("Slack event type=%s team_id=%s", event_type, team_id)

    # Handle uninstall event
    if event_type == "app_uninstalled":
        if not team_id:
            log.error("Missing team_id in uninstall event")
            return {"ok": False}

        log.info("Processing Slack uninstall for team_id=%s", team_id)

        integration_service = IntegrationService(corr_id)
        try:
            workspace_id = await integration_service.resolve_workspace(team_id)
            await integration_service.uninstall_slack(workspace_id)
            log.info("Slack integration removed for workspace_id=%s", workspace_id)
        except Exception as exc:
            log.warning("Slack uninstall failed: %s", exc)

        return {"ok": True}

    return {"ok": True}
