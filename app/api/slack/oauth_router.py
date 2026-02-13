# app/api/slack/oauth_router.py
from __future__ import annotations

from fastapi import APIRouter, HTTPException, Query, Request

from app.core.logging import CorrelationAdapter, get_logger
from app.services.integration_service import IntegrationService

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
      - None (Slack-first)
    """
    corr_id: str = getattr(request.state, "corr_id", "evt_unknown")
    log = CorrelationAdapter(logger, corr_id)

    log.info("Received Slack OAuth callback code=%s state=%s", code, state)

    try:
        integration_service = IntegrationService(corr_id)

        workspace_id = await integration_service.handle_slack_oauth_callback(
            code=code,
            state=state,
        )

        return {
            "status": "success",
            "message": "Slack connected successfully.",
            "workspace_id": workspace_id,
        }

    except HTTPException:
        raise

    except Exception as exc:
        log.error("Slack OAuth callback failed: %s", exc)
        raise HTTPException(status_code=500, detail="Slack OAuth failed") from exc
