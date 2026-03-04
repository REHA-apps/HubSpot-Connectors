# app/api/slack/oauth_router.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, HTTPException, Query, Request
from fastapi.responses import RedirectResponse

from app.core.dependencies import get_integration_service
from app.core.logging import get_corr_id, get_logger
from app.core.security.state_validator import verify_state
from app.db.records import Provider
from app.domains.crm.integration_service import IntegrationService
from app.domains.messaging.slack.service import SlackMessagingService
from app.utils.constants import ErrorCode
from app.utils.ui import render_success_page

router = APIRouter(prefix="/slack/oauth", tags=["slack-oauth"])

logger = get_logger("slack.oauth")


@router.get("/callback")
async def slack_oauth_callback(
    request: Request,
    code: str = Query(...),
    state: str | None = Query(default=None),
    corr_id: str = Depends(get_corr_id),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> Any:
    """Slack OAuth callback."""
    logger.info("Received Slack OAuth callback code=%s state=%s", code, state)

    # 1. CSRF Protection: Verify signed state
    if not state:
        logger.warning("Missing state in OAuth callback")
        raise HTTPException(
            status_code=ErrorCode.BAD_REQUEST, detail="Security error: Missing state"
        )

    workspace_context = verify_state(state)
    if not workspace_context:
        logger.warning("Invalid or expired state: %s", state)
        raise HTTPException(
            status_code=ErrorCode.BAD_REQUEST,
            detail="Security error: Invalid or expired state",
        )

    # 2. handle Slack OAuth errors
    error = request.query_params.get("error")
    if error:
        logger.warning("Slack OAuth error=%s", error)
        raise HTTPException(
            status_code=ErrorCode.BAD_REQUEST, detail=f"Slack OAuth error: {error}"
        )

    try:
        # integration_service injected via Depends()

        workspace_id = await integration_service.handle_slack_oauth_callback(
            code=code,
            state=workspace_context,
        )

        slack_integration = await integration_service.get_integration(
            workspace_id, Provider.SLACK
        )

        # Bridge to HubSpot if missing
        hubspot_integration = await integration_service.get_integration(
            workspace_id, Provider.HUBSPOT
        )
        if not hubspot_integration:
            logger.info("Sending proactive welcome message to Slack")
            try:
                messaging_service = SlackMessagingService(
                    corr_id=corr_id,
                    integration_service=integration_service,
                    slack_integration=slack_integration,
                )
                # Use team_id as the default channel for the welcome DM
                team_id = (
                    slack_integration.slack_team_id if slack_integration else None
                ) or workspace_id
                await messaging_service.send_welcome_message(
                    workspace_id=workspace_id, channel=team_id
                )
            except Exception as e:
                logger.error("Failed to send welcome message: %s", e)

            logger.info("Redirecting to HubSpot install to bridge connection")
            return RedirectResponse(url=f"/api/hubspot/install?state={workspace_id}")

        return render_success_page(
            title="Connection Successful",
            message=(
                "Slack has been linked successfully. "
                "Your cross-platform CRM integration is now active."
            ),
            workspace_id=workspace_id,
            primary_color="#4a154b",  # Slack Purple
            secondary_color="#ff5c35",  # HubSpot Orange
        )

    except HTTPException:
        raise

    except Exception as exc:
        logger.error("Slack OAuth callback failed: %s", exc)
        raise HTTPException(
            status_code=ErrorCode.INTERNAL_ERROR, detail="Slack OAuth failed"
        ) from exc
