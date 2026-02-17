# app/services/channel_service.py
from __future__ import annotations

from collections.abc import Mapping
from typing import Any
from slack_sdk.web.async_client import AsyncWebClient

from app.connectors.slack_connector import SlackConnector
from app.core.logging import CorrelationAdapter, get_logger
from app.core.models.channel import OutboundMessage
from app.api.slack.card_builder import CardBuilder
from app.services.hubspot_service import HubSpotService
from app.integrations.ai_service import AIService
from app.db.records import Provider

logger = get_logger("channel.service")


class ChannelService:
    """Channel-agnostic orchestration layer (Slack only for now)."""

    def __init__(self, *, corr_id: str, integration_service, slack_integration):
        self.corr_id = corr_id
        self.log = CorrelationAdapter(logger, corr_id)
        self.integration_service = integration_service
        self.slack_integration = slack_integration

        # Local per-request services
        self.hubspot = HubSpotService(corr_id)
        self.ai = AIService()
        self.ai.set_corr_id(corr_id)

        # Unified card builder
        self.cards = CardBuilder()

    # ---------------------------------------------------------
    # Slack connector resolution
    # ---------------------------------------------------------
    async def _get_slack_connector(self) -> SlackConnector:
        token = self.slack_integration.slack_bot_token.get_secret_value()
        default_channel = self.slack_integration.channel_id
        client = AsyncWebClient(token=token)
        return SlackConnector(
            slack_client=client,
            corr_id=self.corr_id,
            default_channel=default_channel,
        )

    async def _resolve_channel(self, workspace_id: str, channel: str | None) -> str:
        if channel:
            return channel
        return await self.integration_service.resolve_default_channel(
            workspace_id=workspace_id,
            provider=Provider.SLACK,
        )

    # ---------------------------------------------------------
    # Unified Slack card send (object + AI → Slack)
    # ---------------------------------------------------------
    async def send_slack_card(
        self,
        *,
        workspace_id: str,
        obj: Mapping[str, Any],
        channel: str | None = None,
    ) -> None:

        # 1. AI analysis based on object type
        match obj.get("type"):
            case "deal":
                analysis = self.ai.analyze_deal(obj)
            case "company":
                analysis = self.ai.analyze_company(obj)
            case "lead":
                analysis = self.ai.analyze_contact(obj)
            case "contact" | _:
                analysis = self.ai.analyze_contact(obj)

        # 2. Build Slack card
        card = self.cards.build(obj, analysis)

        # 3. Send Slack message
        await self.send_slack_message(
            workspace_id=workspace_id,
            channel=channel,
            blocks=card["blocks"],
        )

    # ---------------------------------------------------------
    # Raw Slack message send
    # ---------------------------------------------------------
    async def send_slack_message(
        self,
        *,
        workspace_id: str,
        channel: str | None,
        blocks: list[dict[str, Any]] | None = None,
        text: str | None = None,
    ) -> None:
        connector = await self._get_slack_connector()
        channel = await self._resolve_channel(workspace_id, channel)

        message = OutboundMessage(
            workspace_id=workspace_id,
            channel=channel,
            text=text,
            blocks=blocks,
        )

        await connector.send_message(message)

    # ---------------------------------------------------------
    # Unified Slack AI cards
    # ---------------------------------------------------------
    async def send_slack_ai_insights(self, *, workspace_id, channel, analysis):
        card = self.cards.build_ai_insights(analysis)
        await self.send_slack_message(
            workspace_id=workspace_id,
            channel=channel,
            blocks=card["blocks"],
        )

    async def send_slack_ai_scoring(self, *, workspace_id, channel, analysis):
        card = self.cards.build_ai_scoring(analysis)
        await self.send_slack_message(
            workspace_id=workspace_id,
            channel=channel,
            blocks=card["blocks"],
        )

    async def send_slack_next_best_action(self, *, workspace_id, channel, analysis):
        card = self.cards.build_ai_next_best_action(analysis)
        await self.send_slack_message(
            workspace_id=workspace_id,
            channel=channel,
            blocks=card["blocks"],
        )

    # ---------------------------------------------------------
    # HubSpot search + AI + Slack send
    # ---------------------------------------------------------
    async def search_and_send(
        self,
        workspace_id: str,
        query: str,
        channel: str,
        response_url: str,
        object_type: str,
        corr_id: str,
    ) -> None:

        # 1. Search HubSpot
        results = await self.hubspot.search(
            workspace_id=workspace_id,
            object_type=object_type,
            query=query,
        )

        if not results:
            await self.send_slack_message(
                workspace_id=workspace_id,
                channel=channel,
                text=f"No {object_type} found for *{query}*.",
            )
            return

        # 2. Analyze each result
        for obj in results:
            analysis = self.ai.analyze_contact(obj)

            # 3. Build Slack card
            card = self.cards.build(obj, analysis)

            # 4. Send Slack message
            await self.send_slack_message(
                workspace_id=workspace_id,
                channel=channel,
                blocks=card["blocks"],
            )