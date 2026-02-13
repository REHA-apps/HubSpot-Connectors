# app/connectors/slack_connector.py
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.clients.hubspot_client import HubSpotClient
from app.clients.slack_client import SlackClient
from app.connectors.base import Connector
from app.core.logging import CorrelationAdapter, get_logger
from app.db.supabase import StorageService
from app.integrations.ai_service import AIService
from app.integrations.slack_ui import (
    build_contact_card,
    build_deal_card,
    build_lead_card,
)

logger = get_logger("slack.connector")


class SlackConnector(Connector):
    """Slack connector for sending notifications and rendering Slack UI blocks.
    Lightweight by design — not a full Slack app.
    """

    def __init__(self, client: SlackClient, corr_id: str) -> None:
        self.client = client
        self.corr_id = corr_id
        self.log = CorrelationAdapter(logger, corr_id)

    # ------------------------------------------------------------------
    # Resolve HubSpot client for a Slack workspace
    # ------------------------------------------------------------------
    async def _get_hubspot_client(self, team_id: str) -> HubSpotClient | None:
        storage = StorageService(corr_id=self.corr_id)

        slack_integration = storage.get_integration_by_slack_team_id(team_id)
        if not slack_integration:
            self.log.error("No Slack integration found for team_id=%s", team_id)
            return None

        workspace_id = slack_integration.workspace_id

        hubspot_integration = storage.get_integration_by_workspace_and_provider(
            workspace_id=workspace_id,
            provider="hubspot",
        )
        if not hubspot_integration:
            self.log.error(
                "No HubSpot integration found for workspace_id=%s", workspace_id
            )
            return None

        if not hubspot_integration.access_token:
            self.log.error(
                "HubSpot integration missing access_token for workspace_id=%s",
                workspace_id,
            )
            return None

        return HubSpotClient(
            access_token=hubspot_integration.access_token,
            refresh_token=hubspot_integration.refresh_token,
            workspace_id=workspace_id,
            corr_id=self.corr_id,
        )

    # ------------------------------------------------------------------
    # Outbound Slack message
    # ------------------------------------------------------------------
    async def send_event(
        self,
        event: Mapping[str, Any],
        *,
        channel: str = "#general",
        blocks: list[Mapping[str, Any]] | None = None,
    ) -> Mapping[str, Any]:
        self.log.info("Sending Slack event to channel=%s", channel)

        text = event.get("text") or (
            "🔔 *HubSpot Event*\n"
            f"*Type:* {event.get('type')}\n"
            f"*Object ID:* {event.get('object_id')}"
        )

        try:
            await self.client.send_message(
                channel=channel,
                text=text,
                blocks=blocks,
            )
        except Exception as exc:
            self.log.error("Failed to send Slack message: %s", exc)
            raise

        return {"status": "sent"}

    # ------------------------------------------------------------------
    # Inbound event handler
    # ------------------------------------------------------------------
    async def handle_event(
        self,
        event: Mapping[str, Any],
        *,
        channel: str = "#general",
    ) -> Mapping[str, Any]:
        """Expected event shape:
        {
            "team_id": "T12345",
            "query": "john",
            ...
        }
        """
        self.log.info("Handling Slack event for channel=%s", channel)

        team_id = event.get("team_id")
        query = event.get("query")

        if not team_id or not query:
            return await self.send_event(event, channel=channel)

        hubspot = await self._get_hubspot_client(team_id)
        if not hubspot:
            return await self.send_event(event, channel=channel)

        # Fetch contacts, leads, deals
        contacts = await hubspot.search_contacts(query)
        deals = await hubspot.search_deals(query)
        leads = [c for c in contacts if c["properties"].get("lifecyclestage") == "lead"]

        # CONTACT CARDS
        for contact in contacts:
            ai_summary = AIService.generate_contact_insight(contact)
            card = build_contact_card(contact, ai_summary)
            await self.send_event(event, channel=channel, blocks=card["blocks"])

        # LEAD CARDS
        for lead in leads:
            ai_summary = AIService.generate_contact_insight(lead)
            card = build_lead_card(lead, ai_summary)
            await self.send_event(event, channel=channel, blocks=card["blocks"])

        # DEAL CARDS
        for deal in deals:
            ai_summary = AIService.generate_contact_insight(deal)
            card = build_deal_card(deal, ai_summary)
            await self.send_event(event, channel=channel, blocks=card["blocks"])

        return {"status": "sent"}
