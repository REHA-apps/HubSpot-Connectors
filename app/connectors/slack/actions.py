from app.connectors.base import Connector
from app.connectors.slack.client import post_message, post_blocks
from app.connectors.slack.ui import build_contact_card

class SlackConnector(Connector):

    async def send_event(self, event: dict):
        text = (
            f"🔔 HubSpot Event\n"
            f"Type: {event['type']}\n"
            f"Object ID: {event['object_id']}"
        )
        await post_message("#general", text)

    async def handle_event(self, event: dict):
        """
        Rich UI notification (used when contact data is available)
        """
        blocks = build_contact_card(
            contact_data=event["contact_data"],
            ai_summary=event["ai_summary"]
        )

        await post_blocks(
            channel="#general",
            blocks=blocks
        )
