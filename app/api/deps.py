# app/api/deps.py
from __future__ import annotations

from fastapi import Depends, Header, HTTPException, Request

from app.clients.slack_client import SlackClient
from app.connectors.hubspot_connector import HubSpotConnector
from app.connectors.slack_connector import SlackConnector
from app.core.logging import CorrelationAdapter, get_logger
from app.db.supabase import StorageService

logger = get_logger("deps")


async def get_slack_connector(
    request: Request,
    x_slack_team_id: str = Header(...),
) -> SlackConnector:
    """Resolve SlackConnector using the Slack team ID and workspace integration."""
    corr_id: str = getattr(request.state, "corr_id", "evt_unknown")
    log = CorrelationAdapter(logger, corr_id)

    log.info("Resolving SlackConnector for team_id=%s", x_slack_team_id)

    integration = await StorageService.get_integration_by_slack_team_id(
        x_slack_team_id,
        corr_id=corr_id,
    )

    if integration is None or not integration.slack_bot_token:
        log.error("Slack integration not found for team_id=%s", x_slack_team_id)
        raise HTTPException(status_code=404, detail="Workspace not installed.")

    slack_client = SlackClient(token=integration.slack_bot_token)

    return SlackConnector(
        client=slack_client,
        corr_id=corr_id,
    )


async def get_hubspot_connector(
    request: Request,
    slack_connector: SlackConnector = Depends(get_slack_connector),
    x_slack_team_id: str = Header(...),
) -> HubSpotConnector:
    """Resolve HubSpotConnector using Slack team ID and SlackConnector."""
    corr_id: str = getattr(request.state, "corr_id", "evt_unknown")
    log = CorrelationAdapter(logger, corr_id)

    log.info("Resolving HubSpotConnector for team_id=%s", x_slack_team_id)

    return HubSpotConnector(
        slack_team_id=x_slack_team_id,
        slack_connector=slack_connector,
        corr_id=corr_id,
    )
