# scripts/demo.py
import asyncio
import uuid
from collections.abc import Mapping
from typing import Any

from app.core.logging import CorrelationAdapter, get_logger
from app.db.records import IntegrationRecord, Provider
from app.domains.crm.event_router import EventRouter
from app.domains.crm.integration_service import IntegrationService

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

    # Minimal IntegrationRecord mock
    slack_integration = IntegrationRecord(
        id="demo_id",
        workspace_id="demo_workspace",
        provider=Provider.SLACK,
        credentials={"slack_bot_token": "xoxb-your-demo-token"},
        metadata={"channel_id": "#general"},
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
