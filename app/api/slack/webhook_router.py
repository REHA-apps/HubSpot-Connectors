# app/api/slack/webhook_router.py
from __future__ import annotations

from typing import Any

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app.core.logging import CorrelationAdapter, get_logger
from app.core.security.slack_signature import verify_slack_signature
from app.services.command_service import CommandService
from app.services.integration_service import IntegrationService
from app.utils.constants import INTERNAL_SERVER_ERROR, NOT_FOUND_ERROR

router = APIRouter(prefix="/slack", tags=["slack-webhooks"])
logger = get_logger("slack.webhooks")


@router.post("/commands")
async def slack_commands(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, Any]:
    corr_id = getattr(request.state, "corr_id", "evt_unknown")
    log = CorrelationAdapter(logger, corr_id)

    body = await request.body()
    await verify_slack_signature(request.headers, body, corr_id=corr_id)

    form = await request.form()
    command = str(form.get("command", "")).strip()
    text = str(form.get("text", "")).strip()
    team_id = str(form.get("team_id", ""))
    response_url = str(form.get("response_url", ""))
    channel_id = str(form.get("channel_id", "")).strip()

    if not command:
        return {"text": "Unknown command."}

    # Fetch integration ONCE
    integration_service = IntegrationService(corr_id)
    integration = await integration_service.get_integration_by_slack_team_id(team_id)
    if not integration:
        raise HTTPException(
            status_code=NOT_FOUND_ERROR, detail="Workspace not installed"
        )

    command_service = CommandService(corr_id, integration=integration)

    try:
        result = await command_service.handle_slack_command(
            command=command,
            text=text,
            workspace_id=integration.workspace_id,
            response_url=response_url,
            channel_id=channel_id,
            background_tasks=background_tasks,
        )
        return result or {"text": "Command executed."}

    except Exception as exc:
        log.error("Slack command failed: %s", exc)
        raise HTTPException(status_code=INTERNAL_SERVER_ERROR, detail="Command failed")
