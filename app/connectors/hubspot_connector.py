# app/connectors/hubspot_connector.py
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.connectors.base import Connector
from app.core.logging import CorrelationAdapter, get_logger
from app.core.models.events import NormalizedEvent
from app.services.ai_scoring_service import AIScoringService
from app.services.channel_service import ChannelService
from app.services.hubspot_service import HubSpotService
from app.services.integration_service import IntegrationService

logger = get_logger("hubspot.connector")


class HubSpotConnector(Connector):
    """HubSpot connector:
    - normalizes HubSpot webhook events
    - resolves workspace + tokens via IntegrationService
    - delegates HubSpot operations to HubSpotService
    - delegates Slack/WhatsApp notifications to ChannelService
    """

    def __init__(
        self,
        slack_team_id: str | None,
        corr_id: str,
    ) -> None:
        self.slack_team_id = slack_team_id
        self.corr_id = corr_id
        self.log = CorrelationAdapter(logger, corr_id)

        self.integration_service = IntegrationService(corr_id)
        self.hubspot_service = HubSpotService(corr_id)
        self.channel_service = ChannelService(corr_id)
        self.ai_service = AIScoringService()

    # ---------------------------------------------------------
    # Normalization
    # ---------------------------------------------------------
    async def normalize_event(
        self,
        raw_event: Mapping[str, Any],
    ) -> NormalizedEvent:
        return NormalizedEvent(
            channel="hubspot",
            event_type=raw_event.get("type"),
            user_id=None,
            raw=raw_event,
        )

    # ---------------------------------------------------------
    # Inbound event handling
    # ---------------------------------------------------------
    async def handle_event(
        self,
        event: NormalizedEvent,
    ) -> Mapping[str, Any]:
        self.log.info("Handling HubSpot event type=%s", event.event_type)

        workspace_id = await self.integration_service.resolve_workspace(
            slack_team_id=self.slack_team_id,
        )

        hubspot_client = await self.hubspot_service.get_client(workspace_id)

        contact_data = event.raw.get("contact") or {}

        ai_summary = self.ai_service.generate_contact_insight(contact_data)

        await self.channel_service.send_contact_notification(
            workspace_id=workspace_id,
            contact_data=contact_data,
            ai_summary=ai_summary,
        )

        return {"status": "processed", "ai_summary": ai_summary}

    # ---------------------------------------------------------
    # Outbound events
    # ---------------------------------------------------------
    async def send_event(
        self,
        event: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        workspace_id = await self.integration_service.resolve_workspace(
            slack_team_id=self.slack_team_id,
        )

        hubspot_client = await self.hubspot_service.get_client(workspace_id)

        return await hubspot_client.create_task(event)

    # ---------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------
    async def install(self, payload: Mapping[str, Any]) -> None:
        await self.integration_service.install_hubspot(payload)

    async def uninstall(self, payload: Mapping[str, Any]) -> None:
        await self.integration_service.uninstall_hubspot(payload)
