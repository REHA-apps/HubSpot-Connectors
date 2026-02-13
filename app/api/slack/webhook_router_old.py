# app/api/slack/webhook_router.py
from __future__ import annotations

from fastapi import (
    APIRouter,
    BackgroundTasks,
    HTTPException,
    Request,
)

from app.clients.slack_client import SlackClient
from app.connectors.slack_connector import SlackConnector
from app.core.logging import CorrelationAdapter, get_logger
from app.db.supabase import StorageService
from app.integrations.ai_service import AIService
from app.integrations.security import verify_slack_signature
from app.services.contact_search_service import hubspot_contact_search

router = APIRouter(prefix="/slack", tags=["slack-webhooks"])
logger = get_logger("slack.webhooks")


async def get_slack_connector(
    request: Request,
    x_slack_team_id: str,
) -> SlackConnector:
    corr_id: str = getattr(request.state, "corr_id", "evt_unknown")
    log = CorrelationAdapter(logger, corr_id)

    log.info("Resolving SlackConnector for team_id=%s", x_slack_team_id)

    storage = StorageService(corr_id=corr_id)
    integration = storage.get_integration_by_slack_team_id(
        slack_team_id=x_slack_team_id
    )

    if not integration or not integration.slack_bot_token:
        log.error("Workspace not installed for team_id=%s", x_slack_team_id)
        raise HTTPException(status_code=404, detail="Workspace not installed.")

    client = SlackClient(token=integration.slack_bot_token)
    return SlackConnector(client=client, corr_id=corr_id)


@router.post("/commands")
async def slack_commands(
    request: Request,
    background_tasks: BackgroundTasks,
) -> dict[str, str]:
    corr_id: str = getattr(request.state, "corr_id", "evt_unknown")
    log = CorrelationAdapter(logger, corr_id)

    body = await request.body()

    # Verify Slack signature
    if not verify_slack_signature(request.headers, body):
        log.error("Invalid Slack signature")
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    form = await request.form()

    command = form.get("command")
    text = str(form.get("text", "")).strip()
    team_id = str(form.get("team_id", ""))
    response_url = str(form.get("response_url", ""))

    log.info(
        "Received Slack command=%s text=%s team_id=%s",
        command,
        text,
        team_id,
    )

    # ------------------------------------------------------------
    # /hs-contacts
    # ------------------------------------------------------------
    if command == "/hs-contacts":
        if not text:
            return {
                "text": "❌ Please provide an email: `/hs-contacts user@example.com`"
            }

        background_tasks.add_task(
            hubspot_contact_search,
            team_id,
            text,
            response_url,
            corr_id,
        )

        return {
            "response_type": "ephemeral",
            "text": f"🔍 Searching HubSpot contacts for *{text}*...",
        }

    # ------------------------------------------------------------
    # /hs-deals
    # ------------------------------------------------------------
    if command == "/hs-deals":
        if not text:
            return {"text": "❌ Usage: `/hs-deals renewal`"}

        background_tasks.add_task(
            hubspot_contact_search,
            team_id,
            text,
            response_url,
            corr_id,
        )

        return {
            "response_type": "ephemeral",
            "text": f"💼 Searching HubSpot deals for *{text}*...",
        }

    # ------------------------------------------------------------
    # /hs-leads
    # ------------------------------------------------------------
    if command == "/hs-leads":
        if not text:
            return {"text": "❌ Usage: `/hs-leads john`"}

        background_tasks.add_task(
            hubspot_contact_search,
            team_id,
            text,
            response_url,
            corr_id,
        )

        return {
            "response_type": "ephemeral",
            "text": f"🟩 Searching HubSpot leads for *{text}*...",
        }

    # ------------------------------------------------------------
    # /hs (smart intent detection)
    # ------------------------------------------------------------
    if command == "/hs":
        if not text:
            return {"text": "❌ Usage: `/hs <query>`"}

        intent = AIService.detect_intent(text)

        if intent == "deal":
            background_tasks.add_task(
                hubspot_contact_search,
                team_id,
                text,
                response_url,
                corr_id,
            )
            return {
                "response_type": "ephemeral",
                "text": f"💼 Searching HubSpot deals for *{text}*...",
            }

        if intent == "lead":
            background_tasks.add_task(
                hubspot_contact_search,
                team_id,
                text,
                response_url,
                corr_id,
            )
            return {
                "response_type": "ephemeral",
                "text": f"🟩 Searching HubSpot leads for *{text}*...",
            }

        # Default → contact
        background_tasks.add_task(
            hubspot_contact_search,
            team_id,
            text,
            response_url,
            corr_id,
        )
        return {
            "response_type": "ephemeral",
            "text": f"🔍 Searching HubSpot contacts for *{text}*...",
        }

    # ------------------------------------------------------------
    # Unknown command
    # ------------------------------------------------------------
    log.warning("Unknown Slack command received: %s", command)
    return {"text": "Unknown command received."}
