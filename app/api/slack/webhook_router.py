# app/api/slack/webhook_router.py
from __future__ import annotations

from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app.core.logging import CorrelationAdapter, get_logger
from app.security.slack_signature import verify_slack_signature
from app.services.command_service import CommandService
from app.services.integration_service import IntegrationService

router = APIRouter(prefix="/slack", tags=["slack-webhooks"])
logger = get_logger("slack.webhooks")


@router.post("/commands")
async def slack_commands(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    corr_id: str = getattr(request.state, "corr_id", "evt_unknown")
    log = CorrelationAdapter(logger, corr_id)

    body = await request.body()

    # Verify Slack signature
    if not verify_slack_signature(request.headers, body, corr_id=corr_id):
        log.error("Invalid Slack signature")
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    form = await request.form()

    command = form.get("command")
    text = str(form.get("text", "")).strip()
    team_id = str(form.get("team_id", ""))
    response_url = str(form.get("response_url", ""))

    log.info("Received Slack command=%s text=%s team_id=%s", command, text, team_id)

    # Resolve workspace
    integration_service = IntegrationService(corr_id)
    try:
        workspace_id = integration_service.resolve_workspace(team_id)
    except Exception:
        raise HTTPException(status_code=404, detail="Workspace not installed")

    # Delegate to CommandService
    command_service = CommandService(corr_id)

    try:
        return await command_service.handle_slack_command(
            command=command,
            text=text,
            workspace_id=workspace_id,
            response_url=response_url,
            background_tasks=background_tasks,
        )
    except Exception as exc:
        log.error("Slack command failed: %s", exc)
        raise HTTPException(status_code=500, detail="Command failed")
