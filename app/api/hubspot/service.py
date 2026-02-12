from typing import Dict, Any
from app.integrations.connector import Connector
from app.api.hubspot.client import HubSpotClient
from app.api.slack.service import SlackConnector
from app.integrations.ai_service import AIService
from app.db.supabase import StorageService
from app.api.hubspot.schemas import HubSpotContactProperties, HubSpotTaskProperties

class HubSpotConnector(Connector):
    """Dynamic HubSpot connector fetching tokens from Supabase."""

    def __init__(self, slack_team_id: str, slack_connector: SlackConnector):
        self.slack_team_id = slack_team_id
        self.slack_connector = slack_connector
        self.client: HubSpotClient

    async def _init_client(self):
        """Fetch tokens from Supabase and initialize HubSpotClient."""
        integration = await StorageService.get_by_slack_id(self.slack_team_id, provider="hubspot")
        if not integration:
            raise ValueError(f"No HubSpot integration found for Slack team {self.slack_team_id}")
        self.client = HubSpotClient(
            slack_team_id=self.slack_team_id,
            access_token=integration.access_token,
            refresh_token=integration.refresh_token or "",
        )

    async def handle_event(self, event: Dict[str, Any], channel: str = "#general"):
        """Process HubSpot event with AI summary and send Slack notification."""
        if not self.client:
            await self._init_client()

        contact_data = event.get("contact") or {}
        ai_summary = AIService.generate_contact_insight(contact_data)

        slack_event = {
            "contact_data": contact_data,
            "ai_summary": ai_summary,
            "type": event.get("type"),
            "object_id": event.get("object_id"),
        }

        await self.slack_connector.handle_event(slack_event, channel)
        return {"status": "processed", "ai_summary": ai_summary}

    async def send_event(self, event: Dict[str, Any]):
        """Send a HubSpot Task."""
        if not self.client:
            await self._init_client()

        task_dict: Dict[str, Any] = event.get("task_properties") or {}
        task_properties = HubSpotTaskProperties(**task_dict)
        return await self.client.create_task(task_properties)

    async def create_contact(self, contact_properties: HubSpotContactProperties):
        """Create a HubSpot contact dynamically."""
        if not self.client:
            await self._init_client()
        return await self.client.create_contact(contact_properties)
