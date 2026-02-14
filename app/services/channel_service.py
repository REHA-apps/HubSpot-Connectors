# app/services/channel_service.py
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from slack_sdk.web.async_client import AsyncWebClient

from app.connectors.slack_connector import SlackConnector
from app.core.logging import CorrelationAdapter, get_logger
from app.core.models.channel import OutboundMessage
from app.integrations.slack_ui import build_card

logger = get_logger("channel.service")


class ChannelService:
    """Channel-agnostic orchestration layer."""

    def __init__(
        self,
        corr_id: str,
        ai,
        hubspot,
        integration_service,
        slack_integration,
    ):
        self.corr_id = corr_id
        self.log = CorrelationAdapter(logger, corr_id)

        self.ai = ai
        self.hubspot = hubspot
        self.integration_service = integration_service
        self.slack_integration = slack_integration

    # ---------------------------------------------------------
    # Slack connector resolution
    # ---------------------------------------------------------
    async def _get_slack_connector(self) -> SlackConnector:
        token = self.slack_integration.slack_bot_token.get_secret_value()
        client = AsyncWebClient(token=token)
        return SlackConnector(slack_client=client, corr_id=self.corr_id)

    # ---------------------------------------------------------
    # Unified Slack send
    # ---------------------------------------------------------
    async def send_slack_card(
        self,
        workspace_id: str,
        obj: Mapping[str, Any],
        channel: str | None = None,
    ) -> Mapping[str, Any] | None:
        connector = await self._get_slack_connector()

        if channel is None:
            channel = await self.integration_service.resolve_default_channel(
                workspace_id
            )

        analysis = self.ai.analyze_contact(obj)
        card = build_card(obj, analysis)

        message = OutboundMessage(
            workspace_id=workspace_id,
            channel=channel,
            text=None,
            blocks=card["blocks"],
        )

        return await connector.send_message(message)

    # ---------------------------------------------------------
    # Search handlers
    # ---------------------------------------------------------
    async def search_and_send(
        self,
        workspace_id: str,
        query: str,
        channel_id: str,
        response_url: str,
        object_type: str,
        corr_id: str,
    ) -> None:
        self.log = CorrelationAdapter(logger, corr_id)
        self.log.info("Searching HubSpot %s for query=%s", object_type, query)

        if object_type == "contact":
            results = await self.hubspot.search_contacts(workspace_id, query)
        elif object_type == "lead":
            results = await self.hubspot.search_leads(workspace_id, query)
        elif object_type == "deal":
            results = await self.hubspot.search_deals(workspace_id, query)
        else:
            raise ValueError(f"Unknown object_type: {object_type}")

        if not results:
            await self.send_ephemeral(
                response_url, f"No {object_type}s found for *{query}*."
            )
            return

        summary = self.ai.summarize_results(results)
        await self.send_ephemeral(response_url, summary)

        connector = await self._get_slack_connector()
        for obj in results:
            analysis = self.ai.analyze_contact(obj)
            card = build_card(obj, analysis)
            message = OutboundMessage(
                workspace_id=workspace_id,
                channel=channel_id,
                text=None,
                blocks=card["blocks"],
            )
            await connector.send_message(message)

    # ---------------------------------------------------------
    # Slack ephemeral responses
    # ---------------------------------------------------------
    async def send_ephemeral(self, response_url: str, text: str) -> None:
        import httpx

        async with httpx.AsyncClient() as client:
            await client.post(
                response_url,
                json={"response_type": "ephemeral", "text": text},
            )
