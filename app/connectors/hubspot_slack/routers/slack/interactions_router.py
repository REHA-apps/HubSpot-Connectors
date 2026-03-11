from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import Response

from app.connectors.hubspot_slack.services.service import InteractionService
from app.core.dependencies import get_integration_service
from app.core.logging import get_corr_id, get_logger, run_task_with_context
from app.core.security.slack_signature import slack_signature_required
from app.domains.crm.integration_service import IntegrationService
from app.utils.constants import ErrorCode

MIN_ACTION_PARTS = 3

router = APIRouter(prefix="/slack", tags=["slack-interactions"])
logger = get_logger("slack.interactions")


@router.post("/interactions", dependencies=[Depends(slack_signature_required)])
async def slack_interactions(
    request: Request,
    background_tasks: BackgroundTasks,
    corr_id: str = Depends(get_corr_id),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> Response:
    """Handles Slack interactivity callbacks (button clicks, modal submissions)."""
    # 1. Parse payload
    form = await request.form()
    payload_str = form.get("payload")
    if not payload_str:
        logger.error("Missing payload in Slack interaction")
        raise HTTPException(status_code=ErrorCode.BAD_REQUEST, detail="Missing payload")

    try:
        payload = json.loads(str(payload_str))
    except Exception as exc:
        logger.error("Failed to parse Slack interaction payload: %s", exc)
        raise HTTPException(
            status_code=ErrorCode.BAD_REQUEST, detail="Invalid JSON payload"
        )

    interaction_type = payload.get("type")

    from app.domains.ai.service import AIService
    from app.domains.crm.hubspot.service import HubSpotService
    from app.domains.messaging.slack.service import SlackMessagingService

    hubspot = HubSpotService(corr_id=corr_id)
    ai = AIService(corr_id=corr_id)

    interaction_svc = InteractionService(
        hubspot=hubspot, ai=ai, integration_service=integration_service
    )

    # Dispatch to specialized handlers
    if interaction_type == "block_actions":
        response = await interaction_svc.handle_fast_path_block_actions(
            payload, corr_id
        )
        if response:
            return response

    if interaction_type in ("shortcut", "message_action"):
        response = await interaction_svc.handle_fast_path_block_actions(
            payload, corr_id
        )
        if response:
            return response

    # Default: process in background (including view_submission)

    team_id = str(payload.get("team", {}).get("id", ""))
    integration = await integration_service.get_integration_by_slack_team_id(team_id)

    if not integration:
        logger.error("Could not resolve integration for team_id=%s", team_id)
        return Response(status_code=200)

    messaging_service = SlackMessagingService(
        corr_id,
        integration_service=integration_service,
        slack_integration=integration,
    )

    background_tasks.add_task(
        run_task_with_context,
        corr_id,
        interaction_svc.handle_interaction,
        payload,
        integration,
        messaging_service,
        corr_id,
    )

    if interaction_type == "view_submission":
        return Response(
            content=json.dumps({"response_action": "clear"}),
            media_type="application/json",
        )

    return Response(status_code=200)
