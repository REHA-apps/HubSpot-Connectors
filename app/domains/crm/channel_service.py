from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from app.connectors.slack.channel import SlackChannel
from app.connectors.slack.renderer import SlackRenderer
from app.connectors.slack.ui import CardBuilder
from app.core.config import settings
from app.core.logging import get_logger
from app.core.models.channel import OutboundMessage
from app.db.records import Provider
from app.domains.ai.service import AIService
from app.domains.crm.service import CRMService
from app.providers.slack.client import SlackClient
from app.utils.helpers import normalize_object_type

logger = get_logger("channel.service")


class ChannelService:
    """Description:
        Channel-agnostic orchestration layer for cross-platform messaging (Slack, etc.).

    Rules Applied:
        - Abstracts provider-specific connector resolution.
        - Coordinates HubSpot and AI services to produce rich Slack notifications.
    """

    def __init__(
        self,
        corr_id: str,
        integration_service,
        slack_integration,
        crm: CRMService | None = None,
        ai: AIService | None = None,
    ):
        self.corr_id = corr_id
        self.integration_service = integration_service
        self.slack_integration = slack_integration

        # Local per-request services
        self.crm = crm or CRMService(corr_id)
        self.ai = ai or AIService(corr_id)

        # Unified card builder and renderer
        self.cards = CardBuilder()
        self.slack_renderer = SlackRenderer()

    # Connector management
    async def _get_slack_channel(self) -> SlackChannel:
        workspace_id = self.slack_integration.workspace_id
        token = self.slack_integration.slack_bot_token
        refresh_token = self.slack_integration.refresh_token
        expires_at = self.slack_integration.expires_at

        client = SlackClient(
            corr_id=self.corr_id,
            bot_token=token,
            refresh_token=refresh_token,
            expires_at=expires_at,
        )

        # Set callback for token rotation
        client.on_token_refresh = (
            lambda t, r, e: self.integration_service.update_slack_tokens(
                workspace_id=workspace_id,
                access_token=t,
                refresh_token=r,
                expires_at=e,
            )
        )

        return SlackChannel(
            bot_token=token,
            corr_id=self.corr_id,
        )

    async def _resolve_channel(self, workspace_id: str, channel: str | None) -> str:
        if channel:
            return channel
        return await self.integration_service.resolve_default_channel(
            workspace_id=workspace_id,
            provider=Provider.SLACK,
        )

    # Rich message rendering
    async def send_slack_card(
        self,
        *,
        workspace_id: str,
        obj: Mapping[str, Any],
        channel: str | None = None,
        analysis: Any = None,
    ) -> None:
        """Description:
            Builds and dispatches a rich CRM object card with AI insights to Slack.

        Args:
            workspace_id (str): Internal workspace identifier.
            obj (Mapping[str, Any]): The CRM object record from HubSpot.
            channel (str | None): Optional target channel override.

        Returns:
            None

        Rules Applied:
            - Automatically determines object type (Deal, Company, etc.) for
              AI analysis.
            - Standardizes rendering via CardBuilder.

        """
        # 1. AI analysis (if not provided)
        if analysis is None:
            obj_type = str(obj.get("type") or "contact")
            analysis = await self.ai.analyze_polymorphic(obj, obj_type)

        # 2. Build Unified IR
        unified_card = self.cards.build(obj, analysis)

        # 3. Render for Slack
        rendered = self.slack_renderer.render(unified_card)

        # 4. Send Slack message
        await self.send_slack_message(
            workspace_id=workspace_id,
            channel=channel,
            blocks=rendered["blocks"],
        )

    # Core messaging
    async def send_slack_message(
        self,
        *,
        workspace_id: str,
        channel: str | None,
        blocks: list[dict[str, Any]] | None = None,
        text: str | None = None,
    ) -> None:
        """Dispatches a generic message or Block Kit payload to Slack.

        Args:
            workspace_id (str): Internal workspace identifier.
            channel (str | None): Target channel ID or name.
            blocks (list[dict[str, Any]] | None): Optional Slack Block Kit payload.
            text (str | None): Optional fallback text.

        Returns:
            None

        """
        channel_inst = await self._get_slack_channel()
        channel = await self._resolve_channel(workspace_id, channel)

        message = OutboundMessage(
            workspace_id=workspace_id,
            destination=channel,
            text=text,
            provider_metadata={"blocks": blocks},
        )

        await channel_inst.send_message(message)

    # Specialized AI rendering
    async def send_slack_ai_insights(self, *, workspace_id, channel, analysis):
        unified_card = self.cards.build_ai_insights(analysis)
        rendered = self.slack_renderer.render(unified_card)
        await self.send_slack_message(
            workspace_id=workspace_id,
            channel=channel,
            blocks=rendered["blocks"],
        )

    async def send_slack_next_best_action(self, *, workspace_id, channel, analysis):
        unified_card = self.cards.build_ai_next_best_action(analysis)
        rendered = self.slack_renderer.render(unified_card)
        await self.send_slack_message(
            workspace_id=workspace_id,
            channel=channel,
            blocks=rendered["blocks"],
        )

    async def send_welcome_message(self, workspace_id: str, channel: str) -> None:
        """Description:
        Sends a welcome message to Slack with a button to connect HubSpot.
        """
        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "👋 *Welcome to the HubSpot CRM Connector!* \n\n"
                        "To start searching your CRM directly from Slack, "
                        "you need to connect your HubSpot account."
                    ),
                },
            },
            {
                "type": "actions",
                "elements": [
                    {
                        "type": "button",
                        "text": {"type": "plain_text", "text": "Connect HubSpot"},
                        "style": "primary",
                        "url": (
                            f"{settings.API_BASE_URL}/hubspot/install"
                            f"?state={workspace_id}"
                        ),
                        "action_id": "connect_hubspot",
                    }
                ],
            },
        ]
        await self.send_slack_message(
            workspace_id=workspace_id,
            channel=channel,
            blocks=blocks,
            text="Welcome! Please connect your HubSpot account.",
        )

    # Composite operations
    async def search_and_send(
        self,
        workspace_id: str,
        query: str,
        channel: str,
        response_url: str,
        object_type: str,
        corr_id: str,
    ) -> None:
        """Coordinates HubSpot search and sends the best possible Slack result.

        (e.g., card, summary, or error).

        Args:
            workspace_id (str): Internal workspace identifier.
            query (str): The search query.
            channel (str): Target Slack channel.
            response_url (str): Slack response URL for deferred responses.
            object_type (str): CRM object type.
            corr_id (str): Correlation ID for tracing.

        Returns:
            None

        """
        # 1. Search HubSpot
        results = await self.crm.search(
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

        if len(results) > 1:
            # 2. Multiple results -> Send summary list with "View" buttons
            logger.info(
                "Multiple results found (%d), sending summary list", len(results)
            )
            summary_card = self.cards.build_search_results(results[:5])  # Limit to 5
            rendered = self.slack_renderer.render(summary_card)
            await self.send_slack_message(
                workspace_id=workspace_id,
                channel=channel,
                blocks=rendered["blocks"],
            )
            return

        # 3. Single result hit -> Perform rich AI analysis
        obj = results[0]
        obj_type = str(obj.get("type") or normalize_object_type(object_type))
        logger.info(
            "Single hit found id=%s type=%s, performing AI analysis",
            obj.get("id"),
            obj_type,
        )

        analysis = await self.ai.analyze_polymorphic(obj, obj_type)

        # 4. Build Unified IR
        unified_card = self.cards.build(obj, analysis)
        rendered = self.slack_renderer.render(unified_card)

        await self.send_slack_message(
            workspace_id=workspace_id,
            channel=channel,
            blocks=rendered["blocks"],
        )

    async def handle_link_shared(
        self,
        *,
        workspace_id: str,
        channel: str,
        ts: str,
        links: list[dict[str, str]],
    ) -> None:
        """Description:
        Handles Slack link_shared event by unfurling HubSpot URLs.
        """
        try:
            # HubSpot URL pattern: https://app.hubspot.com/contacts/PORTAL_ID/contact/CONTACT_ID/
            pattern = re.compile(
                r"https://app\.hubspot\.com/contacts/\d+/(contact|deal|company)/(\d+)/?"
            )

            unfurls = {}

            for link in links:
                url = link.get("url", "")
                match = pattern.search(url)
                if not match:
                    continue

                obj_type = match.group(1)
                obj_id = match.group(2)

                # 1. Fetch HubSpot object
                obj = await self.crm.get_object(
                    workspace_id=workspace_id, object_type=obj_type, object_id=obj_id
                )
                if not obj:
                    continue

                # 2. AI Analysis
                analysis = await self.ai.analyze_polymorphic(obj, obj_type)

                # 3. Build Card Blocks
                unified_card = self.cards.build(obj, analysis)
                rendered = self.slack_renderer.render(unified_card)

                # 4. Add to unfurls
                unfurls[url] = {"blocks": rendered["blocks"]}

            if unfurls:
                # 5. Call chat.unfurl
                slack_channel = self.integration_service.slack_channel
                await slack_channel.chat_unfurl(
                    channel=channel,
                    ts=ts,
                    unfurls=unfurls,
                )
                logger.info("Sent %d unfurls to channel=%s", len(unfurls), channel)

        except Exception as exc:
            logger.error(
                "Failed to handle Slack link_shared event: %s", exc, exc_info=True
            )
