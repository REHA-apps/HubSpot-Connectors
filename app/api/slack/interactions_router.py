from __future__ import annotations

import json

from fastapi import APIRouter, Form, HTTPException, Request

from app.core.logging import CorrelationAdapter, get_logger

router = APIRouter(prefix="/slack", tags=["slack-interactions"])
logger = get_logger("slack.interactions")


@router.post("/interactions")
async def slack_interactions(
    request: Request,
    payload: str = Form(...),
) -> dict[str, str]:
    """Handles Slack interactive components (buttons, modals, etc.).

    Slack sends application/x-www-form-urlencoded with a "payload" field.
    """
    corr_id: str = getattr(request.state, "corr_id", "evt_unknown")
    log = CorrelationAdapter(logger, corr_id)

    log.info("Received Slack interaction payload")

    try:
        data = json.loads(payload)
    except json.JSONDecodeError as exc:
        log.error("Failed to decode Slack interaction payload: %s", exc)
        raise HTTPException(status_code=400, detail="Invalid payload JSON") from exc

    interaction_type = data.get("type")
    callback_id = data.get("callback_id")

    log.info(
        "Slack interaction type=%s callback_id=%s",
        interaction_type,
        callback_id,
    )

    # Here you can route by callback_id / type into your services.
    # For now we just acknowledge.
    return {"status": "ok"}
