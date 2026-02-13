# app/services/channel_service.py
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.clients.slack_client import SlackClient
from app.connectors.slack_connector import SlackConnector
from app.core.logging import CorrelationAdapter, get_logger
from app.integrations.ai_service import AIService
from app.integrations.slack_ui import (
    build_card,
)
from app.services.hubspot_service import HubSpotService
from app.services.integration_service import IntegrationService

logger = get_logger("channel.service")


class ChannelService:
    """Channel-agnostic message delivery layer.

    Responsibilities:
    - Fetch HubSpot data (via HubSpotService)
    - Generate AI insights (via AIService)
    - Build Slack UI blocks (via slack_ui)
    - Send messages via SlackConnector
    - Provide unified search handlers for contacts, leads, deals
    - Prepare for future channels (WhatsApp, Email, SMS)
    """

    def __init__(self, corr_id: str) -> None:
        self.corr_id = corr_id
        self.log = CorrelationAdapter(logger, corr_id)
        self.hubspot = HubSpotService(corr_id)
        self.integration = IntegrationService(corr_id)

    # ---------------------------------------------------------
    # Slack connector resolution
    # ---------------------------------------------------------
    def _get_slack_connector(self, workspace_id: str) -> SlackConnector:
        integration = (
            self.integration.storage.get_integration_by_workspace_and_provider(
                workspace_id=workspace_id,
                provider="slack",
            )
        )

        if not integration or not integration.slack_bot_token:
            raise ValueError(f"No Slack integration for workspace {workspace_id}")

        client = SlackClient(token=integration.slack_bot_token, corr_id=self.corr_id)
        return SlackConnector(client=client, corr_id=self.corr_id)

    # ---------------------------------------------------------
    # Unified Slack send
    # ---------------------------------------------------------
    async def _send_slack_card(
        self,
        workspace_id: str,
        obj: Mapping[str, Any],
        channel: str,
    ) -> Mapping[str, Any]:
        connector = self._get_slack_connector(workspace_id)

        ai_summary = AIService.generate_contact_insight(obj)
        card = build_card(obj, ai_summary)

        event = {
            "type": "hubspot.object",
            "object_id": obj.get("id"),
            "corr_id": self.corr_id,
        }

        return await connector.send_event(
            event,
            channel=channel,
            blocks=card["blocks"],
        )

    # ---------------------------------------------------------
    # Search handlers (Slack slash commands)
    # ---------------------------------------------------------
    async def search_and_respond_contacts(
        self,
        workspace_id: str,
        query: str,
        response_url: str,
    ) -> None:
        self.log.info("Searching HubSpot contacts for query=%s", query)

        results = await self.hubspot.search_contacts(workspace_id, query)

        if not results:
            await self._send_ephemeral(
                response_url, f"No contacts found for *{query}*."
            )
            return

        summary = AIService.summarize_results(results)
        await self._send_ephemeral(response_url, summary)

        for obj in results:
            await self._send_slack_card(
                workspace_id=workspace_id,
                obj=obj,
                channel=response_url,
            )

    async def search_and_respond_leads(
        self,
        workspace_id: str,
        query: str,
        response_url: str,
    ) -> None:
        self.log.info("Searching HubSpot leads for query=%s", query)

        results = await self.hubspot.search_leads(workspace_id, query)

        if not results:
            await self._send_ephemeral(response_url, f"No leads found for *{query}*.")
            return

        summary = AIService.summarize_results(results)
        await self._send_ephemeral(response_url, summary)

        for obj in results:
            await self._send_slack_card(
                workspace_id=workspace_id,
                obj=obj,
                channel=response_url,
            )

    async def search_and_respond_deals(
        self,
        workspace_id: str,
        query: str,
        response_url: str,
    ) -> None:
        self.log.info("Searching HubSpot deals for query=%s", query)

        results = await self.hubspot.search_deals(workspace_id, query)

        if not results:
            await self._send_ephemeral(response_url, f"No deals found for *{query}*.")
            return

        summary = AIService.summarize_results(results)
        await self._send_ephemeral(response_url, summary)

        for obj in results:
            await self._send_slack_card(
                workspace_id=workspace_id,
                obj=obj,
                channel=response_url,
            )

    # ---------------------------------------------------------
    # Slack ephemeral responses
    # ---------------------------------------------------------
    async def _send_ephemeral(self, response_url: str, text: str) -> None:
        """Sends an ephemeral message back to Slack via response_url."""
        import httpx

        async with httpx.AsyncClient() as client:
            await client.post(
                response_url,
                json={"response_type": "ephemeral", "text": text},
            )
