from fastapi import Depends
from app.core.config import settings
from app.api.slack.client import SlackClient
from app.api.slack.service import SlackConnector
from app.api.hubspot.service import HubSpotConnector
from app.db.supabase import StorageService
from fastapi import Header, HTTPException

async def get_slack_connector(
    x_slack_team_id: str = Header(...)
) -> SlackConnector:
    """
    Reads Slack team ID from header (or you can pass via route param).
    """
    workspace = await StorageService.get_workspace_by_team_id(x_slack_team_id)

    if not workspace:
        raise HTTPException(status_code=404, detail="Workspace not installed.")

    slack_client = SlackClient(token=workspace.slack_bot_token)
    return SlackConnector(client=slack_client)


def get_hubspot_connector(
    slack_connector: SlackConnector = Depends(get_slack_connector),
    slack_team_id: str = "T12345"
) -> HubSpotConnector:
    return HubSpotConnector(slack_team_id=slack_team_id, slack_connector=slack_connector)
