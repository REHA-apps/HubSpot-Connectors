from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.core.logging import get_logger
from app.domains.crm.integration_service import IntegrationService
from app.domains.messaging.slack.service import SlackMessagingService

logger = get_logger("event.router")


class EventRouter:
    """Description:
        Centralized router for normalizing and dispatching cross-platform
        integration events.

    Rules Applied:
        - Transforms inbound HubSpot webhooks into internal structured events.
        - Coordinates with MessagingService for rich UI reporting and delivery.
    """

    def __init__(
        self, corr_id: str, integration_service: IntegrationService, slack_integration
    ) -> None:
        self.corr_id = corr_id
        self.messaging_service = SlackMessagingService(
            corr_id,
            integration_service=integration_service,
            slack_integration=slack_integration,
        )

    # Hook routing logic
    async def route_contact_update(
        self,
        *,
        workspace_id: str,
        contact: Mapping[str, Any],
        channel: str,
    ) -> str | None:
        logger.info(
            "Routing HubSpot contact update id=%s to Slack channel=%s",
            contact.get("id"),
            channel,
        )

        # MessagingService handles:
        # - AI analysis
        # - Slack UI building
        # - SlackConnector resolution
        # - Slack message sending
        return await self.messaging_service.send_card(
            workspace_id=workspace_id,
            obj=contact,
            channel=channel,
        )

    # Generic object routing
    async def route_hubspot_object_to_slack(
        self,
        *,
        workspace_id: str,
        obj: Mapping[str, Any],
        channel: str | None = None,
    ) -> str | None:
        logger.info(
            "Routing HubSpot object id=%s to Slack channel=%s",
            obj.get("id"),
            channel,
        )

        return await self.messaging_service.send_card(
            workspace_id=workspace_id,
            obj=obj,
            channel=channel,
        )
