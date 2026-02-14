# app/api/slack/interactions_router.py
from __future__ import annotations

import json

from fastapi import APIRouter, Depends, Form, HTTPException, Request

from app.core.logging import CorrelationAdapter, get_logger
from app.core.security.slack_signature import verify_slack_signature
from app.utils.constants import BAD_REQUEST_ERROR

router = APIRouter(prefix="/slack", tags=["slack-interactions"])
logger = get_logger("slack.interactions")


@router.post(
    "/interactions",
    dependencies=[Depends(verify_slack_signature)],
)
async def slack_interactions(
    request: Request,
    payload: str = Form(...),
) -> dict[str, str]:
    """Handles Slack interactive components (buttons, modals, etc.)."""
    corr_id: str = getattr(request.state, "corr_id", "evt_unknown")
    log = CorrelationAdapter(logger, corr_id)

    log.info("Received Slack interaction payload")

    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        log.error("Failed to decode Slack interaction payload: %s", exc)
        raise HTTPException(
            status_code=BAD_REQUEST_ERROR, detail="Invalid payload JSON"
        ) from exc

    interaction_type = data.get("type")
    callback_id = data.get("callback_id")

    log.info(
        "Slack interaction type=%s callback_id=%s",
        interaction_type,
        callback_id,
    )

    # TODO: route to InteractionService
    # Example:
    # if callback_id == "contact_card_action":
    #     return await interaction_service.handle_contact_action(data)

    return {"status": "ok"}
