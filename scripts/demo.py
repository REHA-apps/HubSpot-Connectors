# scripts/demo.py
import asyncio
import uuid
from collections.abc import Mapping
from typing import Any

from app.core.logging import CorrelationAdapter, get_logger
from app.services.event_router import EventRouter
from app.services.integration_service import IntegrationService
from app.integrations.slack_integration import SlackIntegration  # adjust import if needed

logger = get_logger("demo")


async def run_demo() -> None:
    # ---------------------------------------------------------
    # Correlation ID
    # ---------------------------------------------------------
    corr_id = f"demo_{uuid.uuid4().hex[:12]}"
    log = CorrelationAdapter(logger, corr_id)

    log.info("Starting demo run with corr_id=%s", corr_id)

    # ---------------------------------------------------------
    # Mock integration objects (replace with real DB fetches)
    # ---------------------------------------------------------
    integration_service = IntegrationService(corr_id=corr_id)

    # Minimal SlackIntegration mock
    from pydantic import SecretStr

    slack_integration = SlackIntegration(
        slack_bot_token=SecretStr("xoxb-your-demo-token"),
        default_channel="#general",
    )

    # ---------------------------------------------------------
    # Create EventRouter
    # ---------------------------------------------------------
    router = EventRouter(
        corr_id=corr_id,
        integration_service=integration_service,
        slack_integration=slack_integration,
    )

    # ---------------------------------------------------------
    # Simulated HubSpot contact object
    # ---------------------------------------------------------
    contact: Mapping[str, Any] = {
        "id": "123",
        "type": "contact",
        "properties": {
            "firstname": "Alice",
            "lastname": "Smith",
            "email": "alice@example.com",
            "company": "Example Corp",
            "hs_analytics_num_visits": 8,
        },
    }

    log.info("➡️ Routing HubSpot contact update to Slack...")

    await router.route_contact_update(
        workspace_id="demo_workspace",
        contact=contact,
        channel="#general",
    )

    log.info("✅ Demo completed successfully")


if __name__ == "__main__":
    asyncio.run(run_demo())