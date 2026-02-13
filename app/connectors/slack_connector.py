# app/connectors/slack_connector.py
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

logger = get_logger("slack.connector")


class SlackConnector(Connector):
    """Slack connector:
    - normalizes Slack events
    - resolves workspace + tokens via IntegrationService
    - delegates HubSpot operations to HubSpotService
    - delegates Slack UI rendering + sending to ChannelService
    """

    def __init__(self, slack_client, corr_id: str) -> None:
        self.client = slack_client
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
            channel="slack",
            event_type=raw_event.get("type"),
            user_id=raw_event.get("user"),
            raw=raw_event,
        )

    # ---------------------------------------------------------
    # Inbound event handling
    # ---------------------------------------------------------
    async def handle_event(
        self,
        event: NormalizedEvent,
    ) -> Mapping[str, Any]:
        self.log.info("Handling Slack event type=%s", event.event_type)

        team_id = event.raw.get("team_id")
        query = event.raw.get("query")

        if not team_id or not query:
            return await self.channel_service.send_basic_message(
                client=self.client,
                channel=event.raw.get("channel", "#general"),
                text="No query provided.",
            )

        workspace_id = await self.integration_service.resolve_workspace(
            slack_team_id=team_id,
        )

        hubspot_client = await self.hubspot_service.get_client(workspace_id)

        contacts = await hubspot_client.search_contacts(query)
        deals = await hubspot_client.search_deals(query)
        leads = [c for c in contacts if c["properties"].get("lifecyclestage") == "lead"]

        # CONTACT CARDS
        for contact in contacts:
            ai_summary = self.ai_service.generate_contact_insight(contact)
            await self.channel_service.send_contact_card(
                client=self.client,
                channel=event.raw.get("channel", "#general"),
                contact=contact,
                ai_summary=ai_summary,
            )

        # LEAD CARDS
        for lead in leads:
            ai_summary = self.ai_service.generate_contact_insight(lead)
            await self.channel_service.send_lead_card(
                client=self.client,
                channel=event.raw.get("channel", "#general"),
                lead=lead,
                ai_summary=ai_summary,
            )

        # DEAL CARDS
        for deal in deals:
            ai_summary = self.ai_service.generate_contact_insight(deal)
            await self.channel_service.send_deal_card(
                client=self.client,
                channel=event.raw.get("channel", "#general"),
                deal=deal,
                ai_summary=ai_summary,
            )

        return {"status": "sent"}

    # ---------------------------------------------------------
    # Outbound events
    # ---------------------------------------------------------
    async def send_event(
        self,
        event: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        return await self.channel_service.send_basic_message(
            client=self.client,
            channel=event.get("channel", "#general"),
            text=event.get("text", "Slack event"),
        )

    # ---------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------
    async def install(self, payload: Mapping[str, Any]) -> None:
        await self.integration_service.install_slack(payload)

    async def uninstall(self, payload: Mapping[str, Any]) -> None:
        await self.integration_service.uninstall_slack(payload)
