# scripts/demo.py
import asyncio
import uuid

from app.clients.slack_client import SlackClient
from app.connectors.hubspot_connector import HubSpotConnector
from app.connectors.slack_connector import SlackConnector
from app.core.config import settings
from app.core.logging import CorrelationAdapter, get_logger

logger = get_logger("demo")


async def run_demo():
    corr_id = f"demo_{uuid.uuid4().hex[:12]}"
    log = CorrelationAdapter(logger, corr_id)

    slack_client = SlackClient(token=settings.SLACK_BOT_TOKEN)
    slack_connector = SlackConnector(client=slack_client)

    hubspot_connector = HubSpotConnector(
        slack_team_id="T12345",
        slack_connector=slack_connector,
    )

    contact_event = {
        "contact": {
            "id": "123",
            "properties": {
                "firstname": "Alice",
                "lastname": "Smith",
                "email": "alice@example.com",
                "company": "Example Corp",
                "hs_analytics_num_visits": 8,
            },
        },
        "type": "contact.created",
        "object_id": "123",
        "corr_id": corr_id,
    }

    log.info("➡️ Sending HubSpot contact event...")
    hubspot_result = await hubspot_connector.handle_event(
        contact_event, corr_id=corr_id
    )
    log.info("✅ HubSpotConnector result: %s", hubspot_result)

    slack_event = {
        "channel": "#general",
        "text": "Hello from the demo script!",
        "corr_id": corr_id,
    }

    log.info("➡️ Sending Slack message...")
    await slack_connector.send_event(slack_event, corr_id=corr_id)


if __name__ == "__main__":
    asyncio.run(run_demo())
