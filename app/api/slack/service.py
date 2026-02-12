from typing import Dict, Any, Optional
from app.integrations.connector import Connector
from app.api.slack.client import SlackClient
from app.integrations.slack.ui import build_contact_card


class SlackConnector(Connector):
    """
    Unified SlackConnector supporting both simple messages and rich HubSpot event notifications.
    """

    def __init__(self, client: SlackClient):
        self.client = client

    # ---------------------------
    # Send Event (Outbound to Slack)
    # ---------------------------
    async def send_event(
        self,
        event: Dict[str, Any],
        channel: str = "#general",
        blocks: Optional[list[Dict[str, Any]]] = None
    ):
        """
        Sends a message to Slack.

        - If blocks are provided, sends rich UI message.
        - Otherwise sends plain text notification.
        """
        if blocks:
            # Send rich block message
            await self.client.send_message(channel, event.get("text", ""), blocks=blocks)
        else:
            # Default plain text message
            text = event.get("text") or (
                f"🔔 *HubSpot Event*\n"
                f"*Type:* {event.get('type')}\n"
                f"*Object ID:* {event.get('object_id')}"
            )
            await self.client.send_message(channel, text)

    # ---------------------------
    # Handle Event (Incoming processing)
    # ---------------------------
    async def handle_event(
        self,
        event: Dict[str, Any],
        channel: str = "#general"
    ):
        """
        Processes an incoming event and sends a Slack notification.

        If contact data and AI summary exist, generates a rich contact card.
        Otherwise sends a simple notification.
        """
        contact_data = event.get("contact_data")
        ai_summary = event.get("ai_summary")

        if contact_data and ai_summary:
            # Build rich Slack blocks
            blocks = build_contact_card(contact_data=contact_data, ai_summary=ai_summary)
            await self.send_event(event, channel, blocks=blocks)
        else:
            # Fall back to simple text notification
            await self.send_event(event, channel)

        return {"status": "processed"}
