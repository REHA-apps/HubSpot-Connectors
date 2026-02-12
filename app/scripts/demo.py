import asyncio
from app.core.config import settings
from app.db.supabase import StorageService
from app.api.slack.client import SlackClient
from app.api.slack.service import SlackConnector
from app.api.hubspot.service import HubSpotConnector

async def run_demo():
    # ---------------------------
    # Initialize Slack connector
    # ---------------------------
    slack_client = SlackClient(token=settings.SLACK_BOT_TOKEN)
    slack_connector = SlackConnector(client=slack_client)

    # ---------------------------
    # Initialize HubSpot connector (dynamic tokens from Supabase)
    # ---------------------------
    # Replace "T12345" with your Slack team ID in Supabase
    hubspot_connector = HubSpotConnector(slack_team_id="T12345", slack_connector=slack_connector)

    # ---------------------------
    # Demo: HubSpot contact event
    # ---------------------------
    contact_event = {
        "contact": {
            "id": "123",
            "properties": {
                "firstname": "Alice",
                "lastname": "Smith",
                "email": "alice@example.com",
                "company": "Example Corp",
                "hs_analytics_num_visits": 8
            }
        },
        "type": "contact.created",
        "object_id": "123"
    }

    print("➡️ Sending HubSpot contact event...")
    hubspot_result = await hubspot_connector.handle_event(contact_event, channel="#general")
    print("✅ HubSpotConnector result:", hubspot_result)

    # ---------------------------
    # Demo: Slack message
    # ---------------------------
    slack_event = {"channel": "#general", "text": "Hello from the demo script!"}
    print("➡️ Sending Slack message...")
    slack_result = await slack_connector.send_event(slack_event)
    print("✅ SlackConnector result:", slack_result)

if __name__ == "__main__":
    asyncio.run(run_demo())
