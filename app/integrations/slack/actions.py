from typing import Dict, Any
from app.integrations.base import Connector
from app.integrations.slack.client import post_message, post_blocks
from app.integrations.slack.ui import build_contact_card

class SlackConnector(Connector):
    """Connector for handling Slack-specific outbound actions."""

    async def send_event(self, event: Dict[str, Any], channel: str = "#general"):
        """Sends a HubSpot event notification to Slack.
        
        Args:
            event: The event data from HubSpot.
            channel: The Slack channel to send the notification to.
        """
        text = (
            f"🔔 *HubSpot Event*\n"
            f"*Type:* {event.get('type')}\n"
            f"*Object ID:* {event.get('object_id')}"
        )
        await post_message(channel, text)

    async def handle_event(self, event: Dict[str, Any], channel: str = "#general"):
        """Sends a rich UI notification with contact data to Slack.
        
        Args:
            event: The event data including contact_data and ai_summary.
            channel: The Slack channel to send the notification to.
        """
        blocks = build_contact_card(
            contact_data=event["contact_data"],
            ai_summary=event["ai_summary"]
        )

        await post_blocks(
            channel=channel,
            blocks=blocks
        )
