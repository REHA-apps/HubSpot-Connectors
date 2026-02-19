from __future__ import annotations

import json

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import Response
from slack_sdk.web.async_client import AsyncWebClient

from app.connectors.slack.ui import CardBuilder
from app.core.dependencies import get_integration_service
from app.core.logging import CorrelationAdapter, get_corr_id, get_logger
from app.core.security.slack_signature import verify_slack_signature
from app.domains.crm.integration_service import IntegrationService
from app.domains.crm.interaction_service import InteractionService
from app.utils.constants import ErrorCode

MIN_ACTION_PARTS = 3

router = APIRouter(prefix="/slack", tags=["slack-interactions"])
logger = get_logger("slack.interactions")


@router.post("/interactions")
async def slack_interactions(
    request: Request,
    background_tasks: BackgroundTasks,
    corr_id: str = Depends(get_corr_id),
    integration_service: IntegrationService = Depends(get_integration_service),
) -> Response:
    """Description:
        Handles Slack interactivity callbacks (button clicks, modal submissions).

    Rules Applied:
        - Modal opens execute IMMEDIATELY to beat Slack's 3s trigger_id window.
        - view_submission returns an EMPTY 200 response so Slack closes the modal,
          then processes the note creation in the background.
        - All other interactions are dispatched to background tasks.
    """
    log = CorrelationAdapter(logger, corr_id)

    # 1. Verify signature
    body = await request.body()
    await verify_slack_signature(request.headers, body, corr_id=corr_id)

    # 2. Parse payload
    form = await request.form()
    payload_str = form.get("payload")
    if not payload_str:
        log.error("Missing payload in Slack interaction")
        raise HTTPException(status_code=ErrorCode.BAD_REQUEST, detail="Missing payload")

    try:
        payload = json.loads(str(payload_str))
    except Exception as exc:
        log.error("Failed to parse Slack interaction payload: %s", exc)
        raise HTTPException(
            status_code=ErrorCode.BAD_REQUEST, detail="Invalid JSON payload"
        )

    interaction_type = payload.get("type")

    # ─── FAST PATH: Modal opens ───────────────────────────────────────
    # Slack trigger_id expires in 3 seconds — open the modal BEFORE any
    # DB lookups or service initialization.
    if interaction_type == "block_actions":
        actions = payload.get("actions", [])
        if actions and actions[0].get("action_id") == "open_add_note_modal":
            trigger_id = payload.get("trigger_id")
            value = str(actions[0].get("value", ""))
            parts = value.split(":")

            if trigger_id and len(parts) >= MIN_ACTION_PARTS:
                obj_type = parts[1]
                object_id = parts[2]

                # Build modal (pure computation, no I/O)
                cards = CardBuilder()
                modal = cards.build_note_modal(obj_type, object_id)

                # Single DB lookup to get bot token
                # (integration_service injected via Depends)
                team = payload.get("team", {})
                team_id = str(team.get("id", ""))

                integration = (
                    await integration_service.get_integration_by_slack_team_id(team_id)
                )
                if integration:
                    bot_token = integration.credentials.get("slack_bot_token")
                    if bot_token:
                        log.info(
                            "Fast-path: opening modal for trigger=%s", trigger_id[:8]
                        )
                        try:
                            client = AsyncWebClient(token=bot_token)
                            await client.views_open(trigger_id=trigger_id, view=modal)
                            log.info("Modal opened for object_id=%s", object_id)
                        except Exception as exc:
                            log.error("Failed to open modal: %s", exc)

                        return Response(status_code=200)

    # ─── FAST PATH: Modal submissions ─────────────────────────────────
    # Slack requires an EMPTY 200 response within 3 seconds to close the
    # modal. Any delay or non-empty body causes "operation timed out".
    # We return immediately and process the note in the background.
    if interaction_type == "view_submission":
        log.info("view_submission received — returning empty 200 to close modal")
        interaction_service = InteractionService(corr_id)
        background_tasks.add_task(interaction_service.handle_interaction, payload)
        # Empty body = Slack closes the modal with no errors
        return Response(status_code=200)

    # ─── DEFAULT: Background processing ───────────────────────────────
    interaction_service = InteractionService(corr_id)
    background_tasks.add_task(interaction_service.handle_interaction, payload)

    return Response(status_code=200)
