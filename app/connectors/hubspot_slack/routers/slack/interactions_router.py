from __future__ import annotations

import json
from collections.abc import Callable

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import Response

from app.connectors.hubspot_slack.services.service import InteractionService
from app.connectors.hubspot_slack.ui import ModalBuilder
from app.core.dependencies import get_integration_service
from app.core.logging import get_corr_id, get_logger
from app.core.security.slack_signature import verify_slack_signature
from app.domains.crm.integration_service import IntegrationService
from app.domains.crm.ui.card_builder import CardBuilder
from app.utils.constants import CREATE_RECORD_CALLBACK_ID, ErrorCode

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
    """Handles Slack interactivity callbacks (button clicks, modal submissions)."""
    # 1. Verify signature
    body = await request.body()
    await verify_slack_signature(request.headers, body, corr_id=corr_id)

    # 2. Parse payload
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

    # Dispatch to specialized handlers
    if interaction_type == "block_actions":
        response = await _handle_block_actions(payload, integration_service, corr_id)
        if response:
            return response

    if interaction_type in ("shortcut", "message_action"):
        response = await _handle_shortcuts(payload, integration_service, corr_id)
        if response:
            return response

    # Default: process in background (including view_submission)
    interaction_service = InteractionService(corr_id)
    background_tasks.add_task(
        _run_task_with_context,
        corr_id,
        interaction_service.handle_interaction,
        payload,
    )

    if interaction_type == "view_submission":
        return Response(
            content=json.dumps({"response_action": "clear"}),
            media_type="application/json",
        )

    return Response(status_code=200)


async def _handle_block_actions(
    payload: dict,
    integration_service: IntegrationService,
    corr_id: str,
) -> Response | None:
    """Fast-path for modal opens within the 3s window."""
    actions = payload.get("actions", [])
    action_id = str(actions[0].get("action_id", "")) if actions else ""

    if not action_id.startswith(("open_add_note_modal", "open_schedule_meeting_modal")):
        return None

    trigger_id = payload.get("trigger_id")
    value = str(actions[0].get("value", ""))
    parts = value.split(":")

    if not (trigger_id and len(parts) >= 2):  # noqa: PLR2004
        return None

    # Resolve integration & token
    team_id = str(payload.get("team", {}).get("id", ""))
    integration = await integration_service.get_integration_by_slack_team_id(team_id)
    if not integration:
        return None

    bot_token = integration.credentials.get("slack_bot_token")
    if not bot_token:
        return None

    # Tier check for Pro actions
    is_pro = await integration_service.is_pro_workspace(integration.workspace_id)
    if not is_pro:
        # Prompt to upgrade via ephemeral message instead of modal
        response_url = payload.get("response_url")
        if response_url:
            try:
                from app.connectors.hubspot_slack.slack_channel import SlackChannel

                slack_channel = SlackChannel(corr_id=corr_id, bot_token=bot_token)
                await slack_channel.send_via_response_url(
                    response_url=response_url,
                    text=(
                        "Update fields, indexing notes, and scheduling meetings are "
                        "Professional features. [Upgrade to Pro]"
                        "(https://app.crm-connectors.com/upgrade) to continue."
                    ),
                )
            except Exception as exc:
                logger.error("Failed to send upgrade prompt: %s", exc)
        return Response(status_code=200)

    # Build modal
    object_id = parts[-1]
    obj_type = parts[1] if len(parts) > 2 else "contact"  # noqa: PLR2004
    # Build metadata
    channel_id = payload.get("channel", {}).get("id")
    response_url = payload.get("response_url")
    meta_dict = {
        "object_id": object_id,
        "object_type": obj_type,
        "contact_id": object_id if obj_type == "contact" else None,
    }
    if channel_id:
        meta_dict["channel_id"] = channel_id
    if response_url:
        meta_dict["response_url"] = response_url

    metadata = json.dumps(meta_dict)

    cards = CardBuilder()

    if action_id.startswith("open_add_note_modal"):
        modal = cards.build_note_modal(obj_type, object_id, metadata=metadata)
    else:
        modal = cards.build_meeting_modal(object_id, metadata=metadata)

    logger.info("Fast-path: opening modal for trigger=%s", trigger_id[:8])
    try:
        client = await integration_service.get_slack_client(integration)
        await client.views_open(trigger_id=trigger_id, view=modal)
        logger.info("Modal opened for object_id=%s", object_id)
    except Exception as exc:
        logger.error("Failed to open modal: %s", exc)

    return Response(status_code=200)


async def _handle_shortcuts(
    payload: dict,
    integration_service: IntegrationService,
    corr_id: str,
) -> Response | None:
    """Fast-path for shortcuts (e.g., Global Search / Create)."""
    callback_id = payload.get("callback_id")
    if callback_id not in (CREATE_RECORD_CALLBACK_ID, "create_hubspot_record_message"):
        return None

    trigger_id = payload.get("trigger_id")
    team_id = str(payload.get("team", {}).get("id", ""))

    integration = await integration_service.get_integration_by_slack_team_id(team_id)
    if not (integration and integration.credentials.get("slack_bot_token")):
        return None

    # Tier check for Pro actions (Create)
    is_pro = await integration_service.is_pro_workspace(integration.workspace_id)
    if not is_pro:
        try:
            # For shortcuts, we might want to open a small "Upgrade Required" modal
            # instead of ephemeral
            # or just use views.open with an alert.
            # For now, let's use the response_url if available, or just log.
            # Shortcuts often don't have response_url unless triggered from message.
            # If no response_url, we can open a tiny "Upgrade" modal.
            modals = ModalBuilder()
            modal = {
                "type": "modal",
                "title": {"type": "plain_text", "text": "Upgrade to Pro"},
                "blocks": [
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                "Creating records from Slack is a Professional "
                                "feature. \n\n"
                                "<https://app.crm-connectors.com/upgrade|"
                                "Upgrade to Professional Plan>"
                            ),
                        },
                    }
                ],
            }
            client = await integration_service.get_slack_client(integration)
            await client.views_open(trigger_id=trigger_id, view=modal)
        except Exception as exc:
            logger.error("Failed to open upgrade modal: %s", exc)
        return Response(status_code=200)

    # Build modal
    modals = ModalBuilder()
    modal = modals.build_type_selection(CREATE_RECORD_CALLBACK_ID)

    channel_id = payload.get("channel", {}).get("id")
    response_url = payload.get("response_url")
    meta_dict = {}
    if channel_id:
        meta_dict["channel_id"] = channel_id
    if response_url:
        meta_dict["response_url"] = response_url

    if meta_dict:
        modal["private_metadata"] = json.dumps(meta_dict)

    logger.info("Fast-path: opening creation modal for trigger=%s", trigger_id)
    try:
        client = await integration_service.get_slack_client(integration)
        await client.views_open(trigger_id=trigger_id, view=modal)
    except Exception as exc:
        logger.error("Failed to open creation modal: %s", exc)

    return Response(status_code=200)


async def _run_task_with_context(corr_id: str, func: Callable, *args, **kwargs):
    """Wraps a background task in log_context to maintain correlation IDs."""
    from app.core.logging import log_context

    with log_context(corr_id):
        await func(*args, **kwargs)
