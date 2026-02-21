from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any

from app.connectors.slack.channel import SlackChannel
from app.connectors.slack.renderer import SlackRenderer
from app.connectors.slack.ui import CardBuilder
from app.core.config import settings
from app.core.exceptions import IntegrationNotFoundError
from app.core.logging import get_logger
from app.core.models.channel import OutboundMessage
from app.db.records import Provider
from app.domains.ai.service import AIService
from app.domains.crm.base import BaseChannelService
from app.domains.crm.service import CRMService
from app.providers.slack.client import SlackClient
from app.utils.helpers import normalize_object_type

logger = get_logger("channel.service")

# Compiled Regex Patterns
TICKET_PATTERN = re.compile(r"Ticket #(\d+)")
TICKET_ID_PATTERN = re.compile(r"Ticket ID: (\d+)")
CONVERSATION_PATTERN = re.compile(r"Conversation #(\d+)")


class ChannelService(BaseChannelService):
    """Slack-specific implementation of the ChannelService.

    Orchestrates HubSpot and AI services to produce rich Slack notifications.
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
        if not self.slack_integration:
            raise IntegrationNotFoundError(
                "Slack integration not configured for this workspace"
            )

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
        client.on_token_refresh = lambda t, r, e: (
            self.integration_service.update_slack_tokens(
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
    async def send_card(
        self,
        *,
        workspace_id: str,
        obj: Mapping[str, Any],
        channel: str | None = None,
        analysis: Any = None,
    ) -> None:
        """Builds and dispatches a rich CRM object card with AI insights to Slack.

        Automatically determines object type for AI analysis if not provided.

        Args:
            workspace_id (str): Internal workspace identifier.
            obj (Mapping[str, Any]): The CRM object record from HubSpot.
            channel (str | None): Optional target channel override.
            analysis (Any): Optional pre-computed AI analysis.

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
        await self.send_message(
            workspace_id=workspace_id,
            channel=channel,
            blocks=rendered["blocks"],
        )

    # Core messaging
    async def send_message(
        self,
        *,
        workspace_id: str,
        channel: str | None,
        blocks: list[dict[str, Any]] | None = None,
        text: str | None = None,
        metadata: Mapping[str, Any] | None = None,
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
        try:
            channel = await self._resolve_channel(workspace_id, channel)
        except IntegrationNotFoundError:
            logger.warning(
                "Configuration missing: No Slack channel resolved. Skipping message."
            )
            return

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
        await self.send_message(
            workspace_id=workspace_id,
            channel=channel,
            blocks=rendered["blocks"],
        )

    async def send_slack_next_best_action(self, *, workspace_id, channel, analysis):
        unified_card = self.cards.build_ai_next_best_action(analysis)
        rendered = self.slack_renderer.render(unified_card)
        await self.send_message(
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
        await self.send_message(
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
        user_id: str = "",
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
            user_id (str): Slack user ID who triggered the search.

        Returns:
            None

        """
        # Build a context header showing who triggered the search
        context_blocks: list[dict[str, Any]] = []
        if user_id:
            context_blocks = [
                {
                    "type": "context",
                    "elements": [
                        {
                            "type": "mrkdwn",
                            "text": f"<@{user_id}> searched {object_type}s"
                            f" for *{query}*",
                        }
                    ],
                }
            ]

        # 1. Search HubSpot
        results = await self.crm.search(
            workspace_id=workspace_id,
            object_type=object_type,
            query=query,
        )

        if not results:
            await self.send_message(
                workspace_id=workspace_id,
                channel=channel,
                blocks=context_blocks,
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
            await self.send_message(
                workspace_id=workspace_id,
                channel=channel,
                blocks=context_blocks + rendered["blocks"],
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

        # Fetch pipelines if it's a deal (for stage dropdown)
        pipelines = None
        if obj_type == "deal":
            pipelines = await self.crm.hubspot.get_deal_pipelines(workspace_id)

        # Enrich task if it's a task
        task_context = None
        if obj_type == "task":
            task_context = await self.crm.hubspot.enrich_task(workspace_id, obj)

        # 4. Build Unified IR
        unified_card = self.cards.build(
            obj, analysis, pipelines=pipelines, task_context=task_context
        )
        rendered = self.slack_renderer.render(unified_card)

        await self.send_message(
            workspace_id=workspace_id,
            channel=channel,
            blocks=context_blocks + rendered["blocks"],
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

    async def handle_threaded_reply(
        self,
        *,
        workspace_id: str,
        channel: str,
        thread_ts: str,
        message_ts: str,
        text: str,
        user: str,
    ) -> None:
        """Description:
        Handles a reply in a threaded conversation.
        If the thread is associated with a CRM object (Ticket), syncs the reply.
        """
        try:
            slack_channel = await self._get_slack_channel()
            client = slack_channel.get_slack_client()

            # 1. Fetch parent message to establish context
            resp = await client.conversations_replies(
                channel=channel, ts=thread_ts, limit=1, inclusive=True
            )
            messages = resp.get("messages", [])
            if not messages:
                logger.warning(
                    "Could not fetch parent message for thread_ts=%s", thread_ts
                )
                return

            parent = messages[0]
            parent_text = parent.get("text", "")

            blocks = parent.get("blocks", [])
            full_context = f"{parent_text} {str(blocks)}"

            # 2. Heuristic: Look for Ticket or Conversation Context
            ticket_match = TICKET_PATTERN.search(full_context)
            if not ticket_match:
                ticket_match = TICKET_ID_PATTERN.search(full_context)

            conversation_match = CONVERSATION_PATTERN.search(full_context)

            if ticket_match:
                ticket_id = ticket_match.group(1)

                # 3. Create Note for Ticket
                note_content = f"Slack Reply from <@{user}>:\n{text}"

                await self.crm.hubspot.create_note(
                    workspace_id=workspace_id,
                    content=note_content,
                    associated_id=ticket_id,
                    associated_type="ticket",
                )
                logger.info("Synced threaded reply to Ticket %s", ticket_id)

            elif conversation_match:
                thread_id = conversation_match.group(1)

                # 3. Send Message to Conversation
                await self.crm.hubspot.send_thread_reply(
                    workspace_id=workspace_id,
                    thread_id=thread_id,
                    text=text,
                )
                logger.info("Synced threaded reply to Conversation %s", thread_id)

            else:
                # Not a CRM thread
                return

            # 4. React to the reply to confirm sync
            await client.reactions_add(
                channel=channel, name="notebook", timestamp=message_ts
            )

        except Exception as exc:
            logger.error("Failed to handle threaded reply: %s", exc, exc_info=True)
