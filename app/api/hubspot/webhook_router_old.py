# app/api/hubspot/webhook_router.py
from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request

from app.clients.slack_client import SlackClient
from app.connectors.hubspot_connector import HubSpotConnector
from app.connectors.slack_connector import SlackConnector
from app.core.logging import CorrelationAdapter, get_logger
from app.db.supabase import StorageService

router = APIRouter(prefix="/hubspot", tags=["hubspot-webhooks"])
logger = get_logger("hubspot.webhooks")


async def get_slack_connector(
    request: Request,
) -> SlackConnector:
    corr_id: str = getattr(request.state, "corr_id", "evt_unknown")
    adapter = CorrelationAdapter(logger, corr_id)

    team_id = request.headers.get("X-Slack-Team-Id")
    if not team_id:
        adapter.error("Missing X-Slack-Team-Id header")
        raise HTTPException(status_code=400, detail="Missing X-Slack-Team-Id header")

    workspace = await StorageService.get_integration_by_slack_team_id(team_id)
    if not workspace or not workspace.slack_bot_token:
        adapter.error("Workspace not installed for team_id=%s", team_id)
        raise HTTPException(status_code=404, detail="Workspace not installed.")

    client = SlackClient(token=workspace.slack_bot_token)
    return SlackConnector(client=client, corr_id=corr_id)


async def get_hubspot_connector(
    request: Request,
    slack_connector: SlackConnector = Depends(get_slack_connector),
) -> HubSpotConnector:
    corr_id: str = getattr(request.state, "corr_id", "evt_unknown")
    team_id = request.headers.get("X-Slack-Team-Id")
    return HubSpotConnector(
        slack_team_id=team_id,
        slack_connector=slack_connector,
        corr_id=corr_id,
    )
