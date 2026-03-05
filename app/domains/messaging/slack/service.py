from __future__ import annotations

import re
from collections.abc import Mapping
from typing import Any, cast

from slack_sdk.errors import SlackApiError

from app.connectors.hubspot_slack.slack_channel import SlackChannel
from app.connectors.hubspot_slack.slack_renderer import SlackRenderer
from app.core.config import settings
from app.core.exceptions import IntegrationNotFoundError
from app.core.logging import get_logger
from app.core.models.channel import OutboundMessage
from app.domains.ai.service import AIService
from app.domains.crm.service import CRMService
from app.domains.crm.ui import CardBuilder
from app.domains.messaging.base import MessagingService
from app.utils.helpers import normalize_object_type

logger = get_logger("slack.channel.service")

# Compiled Regex Patterns
TICKET_PATTERN = re.compile(r"Ticket #(\d+)")
TICKET_ID_PATTERN = re.compile(r"Ticket ID: (\d+)")
CONVERSATION_PATTERN = re.compile(r"Conversation #(\d+)")


class SlackMessagingService(MessagingService):
    """Slack-specific implementation of the MessagingService.

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
    async def get_slack_channel(self) -> SlackChannel:
        if not self.slack_integration:
            raise IntegrationNotFoundError(
                "Slack integration not configured for this workspace"
            )

        client = await self.integration_service.get_slack_client(self.slack_integration)

        return SlackChannel(
            bot_token=self.slack_integration.slack_bot_token,
            corr_id=self.corr_id,
            slack_client=client,
        )

    async def _resolve_channel(self, workspace_id: str, channel: str | None) -> str:
        if channel:
            return channel

        # Use the specific channel defined for this integration instance
        # (Enterprise routing support)
        if self.slack_integration and self.slack_integration.metadata.get("channel_id"):
            return str(self.slack_integration.metadata["channel_id"])

        try:
            return await self.integration_service.resolve_default_channel(
                workspace_id=workspace_id,
            )
        except IntegrationNotFoundError:
            # Fall back to dynamically fetching the actual
            # default channel from Slack API
            client = await self.get_slack_channel()
            default_id = await client.get_default_channel_id()
            if default_id:
                return default_id
            raise

    # Rich message rendering
    async def send_card(
        self,
        *,
        workspace_id: str,
        obj: Mapping[str, Any],
        channel: str | None = None,
        analysis: Any = None,
        is_pro: bool = False,
        thread_ts: str | None = None,
        response_url: str | None = None,
    ) -> str | None:
        """Builds and dispatches a rich CRM object card with AI insights to Slack."""
        # 1. AI analysis (if not provided)
        if analysis is None:
            obj_type = str(obj.get("type") or "contact")
            analysis = await self.ai.analyze_polymorphic(obj, obj_type)

        # 2. Build Unified IR
        unified_card = self.cards.build(obj, cast(Any, analysis), is_pro=is_pro)

        # 3. Render for Slack
        rendered = self.slack_renderer.render(unified_card)

        # 4. Send Slack message
        if response_url:
            await self.send_via_response_url(
                response_url=response_url,
                blocks=rendered["blocks"],
                text=unified_card.title or "CRM Object Detail",
            )
            return None

        resp = await self.send_message(
            workspace_id=workspace_id,
            channel=channel,
            blocks=rendered["blocks"],
            thread_ts=thread_ts,
        )
        return str(resp.get("ts")) if resp and resp.get("ts") else None

    # Core messaging
    async def send_message(
        self,
        *,
        workspace_id: str,
        channel: str | None,
        blocks: list[dict[str, Any]] | None = None,
        text: str | None = None,
        metadata: Mapping[str, Any] | None = None,
        thread_ts: str | None = None,
    ) -> Mapping[str, Any] | None:
        """Dispatches a generic message or Block Kit payload to Slack."""
        channel_inst = await self.get_slack_channel()
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
            provider_metadata={"blocks": blocks, "thread_ts": thread_ts},
        )

        return await channel_inst.send_message(message)

    async def send_via_response_url(
        self,
        response_url: str,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
        replace_original: bool = False,
    ) -> bool:
        """Sends a response to a Slack slash command or interaction using the
        response_url.

        # noqa: E501
        """
        channel = await self.get_slack_channel()
        return await channel.send_via_response_url(
            response_url=response_url,
            text=text,
            blocks=blocks,
            replace_original=replace_original,
        )

    # Specialized AI rendering
    async def send_ai_insights(
        self, *, workspace_id, channel, user_email: str | None = None, analysis
    ):
        """Sends AI insights/recap to Slack or user DM."""
        unified_card = self.cards.build_ai_insights(analysis)
        rendered = self.slack_renderer.render(unified_card)

        # Try sending to the defined channel (or fallback to workspace default)
        result = await self.send_message(
            workspace_id=workspace_id,
            channel=channel,
            blocks=rendered["blocks"],
        )

        # If sending failed (e.g., no default channel resolved)
        # and we have their email, DM them
        if not result and user_email:
            logger.info(
                "Primary channel delivery failed, attempting to DM user %s.", user_email
            )
            channel_inst = await self.get_slack_channel()
            slack_user_id = await channel_inst.get_user_by_email(user_email)
            if slack_user_id:
                await channel_inst.send_dm(
                    user_id=slack_user_id,
                    text="Your HubSpot AI Insights",
                    blocks=rendered["blocks"],
                )
            else:
                logger.warning(
                    "Could not resolve Slack user ID for email %s.", user_email
                )

    async def send_dm(
        self,
        *,
        user_id: str | None = None,
        user_email: str | None = None,
        text: str,
    ) -> bool:
        """Sends a direct message to a user by ID or email."""
        try:
            channel_inst = await self.get_slack_channel()
            if not user_id and user_email:
                user_id = await channel_inst.get_user_by_email(user_email)

            if not user_id:
                logger.warning("Could not resolve Slack user ID.")
                return False

            await channel_inst.send_dm(user_id=user_id, text=text)
            return True
        except Exception as exc:
            logger.error("Failed to send DM: %s", exc)
            return False

    async def send_welcome_message(self, workspace_id: str, channel: str) -> None:
        """Sends a welcome message to Slack with a button to connect HubSpot."""
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
        """Coordinates HubSpot search and sends the best possible Slack result."""
        slack_channel = await self.get_slack_channel()

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
            await slack_channel.send_via_response_url(
                response_url=response_url,
                blocks=context_blocks,
                text=f"No {object_type} found for *{query}*.",
            )
            return

        if len(results) > 1:
            # 2. Multiple results -> Send summary list with "View" buttons
            logger.info(
                "Multiple results found (%d), sending summary list", len(results)
            )
            summary_card = self.cards.build_search_results(results[:5])
            rendered = self.slack_renderer.render(summary_card)
            await slack_channel.send_via_response_url(
                response_url=response_url,
                blocks=context_blocks + rendered["blocks"],
                text=f"Found multiple {object_type}s.",
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

        # Fetch pipelines if it's a deal
        pipelines = None
        if obj_type == "deal":
            pipelines = await self.crm.hubspot.get_deal_pipelines(workspace_id)

        # Enrich task if it's a task
        task_context = None
        if obj_type == "task":
            task_context = await self.crm.hubspot.enrich_task(workspace_id, obj)

        # 4. Build Unified IR
        is_pro = await self.integration_service.is_pro_workspace(workspace_id)
        unified_card = self.cards.build(
            obj,
            cast(Any, analysis),
            pipelines=pipelines,
            task_context=task_context,
            is_pro=is_pro,
        )
        rendered = self.slack_renderer.render(unified_card)

        await slack_channel.send_via_response_url(
            response_url=response_url,
            blocks=context_blocks + rendered["blocks"],
            text=f"Found {object_type}: {obj.get('id')}",
        )

    async def handle_link_shared(
        self,
        *,
        workspace_id: str,
        channel: str,
        ts: str,
        links: list[dict[str, str]],
    ) -> None:
        """Handles Slack link_shared event by unfurling HubSpot URLs."""
        try:
            pattern = re.compile(
                r"https://app(?:-[a-z0-9]+)?\.hubspot\.com/contacts/\d+/(?:record/)?([^/?#]+)/(\d+)"
            )

            unfurls = {}

            for link in links:
                url = link.get("url", "")
                match = pattern.search(url)
                if not match:
                    continue

                obj_type = normalize_object_type(match.group(1))
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
                is_pro = await self.integration_service.is_pro_workspace(workspace_id)
                unified_card = self.cards.build(obj, cast(Any, analysis), is_pro=is_pro)
                rendered = self.slack_renderer.render(unified_card)

                # 4. Add to unfurls
                unfurls[url] = {"blocks": rendered["blocks"]}

            if unfurls:
                # 5. Call chat.unfurl
                slack_channel_inst = await self.get_slack_channel()
                try:
                    await slack_channel_inst.chat_unfurl(
                        channel=channel,
                        ts=ts,
                        unfurls=unfurls,
                    )
                    logger.info("Sent %d unfurls to channel=%s", len(unfurls), channel)
                except SlackApiError as exc:
                    if exc.response.get("error") == "cannot_unfurl_url":
                        logger.warning(
                            "Slack chat.unfurl failed"
                            " (cannot_unfurl_url)."
                            " Falling back to threaded reply."
                        )
                        # Fallback: Post as threaded reply
                        for url, data in unfurls.items():
                            blocks = data.get("blocks")
                            if blocks:
                                client = slack_channel_inst.get_slack_client()
                                await client.chat_postMessage(
                                    channel=channel,
                                    thread_ts=ts,
                                    blocks=blocks,
                                    text=f"AI Insights for: {url}",
                                )
                    else:
                        logger.error("Slack chat.unfurl failed: %s", exc)
                        raise

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
        """Handles a reply in a threaded conversation."""
        try:
            slack_channel = await self.get_slack_channel()
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

            # 2. Look up thread mapping
            object_id = None
            object_type = None

            mapping = await self.integration_service.storage.get_thread_mapping_by_ts(
                workspace_id=workspace_id,
                channel_id=channel,
                thread_ts=thread_ts,
            )

            supported_types = ("ticket", "contact", "deal", "company")
            if mapping and mapping.object_type in supported_types:
                object_id = mapping.object_id
                object_type = mapping.object_type
                logger.info(
                    "Resolved object ID from thread mapping: %s:%s",
                    object_type,
                    object_id,
                )

            # Heuristic Fallback
            if not object_id:
                ticket_match = TICKET_PATTERN.search(full_context)
                if not ticket_match:
                    ticket_match = TICKET_ID_PATTERN.search(full_context)
                if ticket_match:
                    object_id = ticket_match.group(1)
                    object_type = "ticket"

            conversation_match = CONVERSATION_PATTERN.search(full_context)

            if object_id and object_type:
                # 3. Create Note for Object
                note_content = f"Slack Reply from <@{user}>:\n{text}"
                await self.crm.hubspot.create_note(
                    workspace_id=workspace_id,
                    content=note_content,
                    associated_id=object_id,
                    associated_type=object_type,
                )
                logger.info(
                    "Synced threaded reply to %s %s",
                    object_type.capitalize(),
                    object_id,
                )

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
                return

            # 4. React to the reply to confirm sync
            await client.reactions_add(
                channel=channel, name="notebook", timestamp=message_ts
            )

        except Exception as exc:
            logger.error("Failed to handle threaded reply: %s", exc, exc_info=True)

    async def handle_reaction_logging(
        self,
        *,
        workspace_id: str,
        channel: str,
        message_ts: str,
        reaction: str,
        user: str,
    ) -> None:
        """Handles a Slack reaction (📝) by logging the message content to HubSpot."""
        try:
            # 1. Tier Check
            is_pro = await self.integration_service.is_pro_workspace(workspace_id)
            if not is_pro:
                logger.info(
                    "Skipping reaction sync: Workspace %s is not PRO", workspace_id
                )
                return

            slack_channel = await self.get_slack_channel()
            client = slack_channel.get_slack_client()

            # 2. Fetch the specific message
            resp = await client.reactions_get(channel=channel, timestamp=message_ts)
            msg_data = resp.get("message", {})
            text = msg_data.get("text", "")
            thread_ts = msg_data.get("thread_ts") or message_ts

            if not text:
                logger.warning("Empty message for reaction sync in channel=%s", channel)
                return

            # 3. Resolve HubSpot Record
            mapping = await self.integration_service.storage.get_thread_mapping_by_ts(
                workspace_id=workspace_id,
                channel_id=channel,
                thread_ts=thread_ts,
            )

            object_id = None
            object_type = None

            if mapping:
                object_id = mapping.object_id
                object_type = mapping.object_type
            else:
                full_context = text + str(msg_data.get("blocks", []))
                ticket_match = TICKET_PATTERN.search(full_context)
                if not ticket_match:
                    ticket_match = TICKET_ID_PATTERN.search(full_context)

                if ticket_match:
                    object_id = ticket_match.group(1)
                    object_type = "ticket"

            if not object_id or not object_type:
                logger.warning(
                    "Could not resolve HubSpot record for reaction sync in "
                    "channel=%s message_ts=%s",
                    channel,
                    message_ts,
                )
                return

            # 4. Create Note in HubSpot
            note_content = f"Logged from Slack by <@{user}> (📝 reaction):\n{text}"
            await self.crm.hubspot.create_note(
                workspace_id=workspace_id,
                content=note_content,
                associated_id=object_id,
                associated_type=object_type,
            )

            # 5. Confirmation Reaction
            await client.reactions_add(
                channel=channel, name="notebook", timestamp=message_ts
            )
            logger.info(
                "Synced message to HubSpot %s:%s via emoji", object_type, object_id
            )

        except Exception as exc:
            logger.error("Failed to handle reaction logging: %s", exc, exc_info=True)

    async def handle_app_home_opened(self, user_id: str) -> None:
        """Publishes the static Home tab view when a user opens the App Home."""
        try:
            slack_channel = await self.get_slack_channel()
            client = slack_channel.get_slack_client()

            logger.info("Publishing App Home view for user=%s", user_id)
            view_payload = self.cards.build_app_home_view()

            await client.views_publish(user_id=user_id, view=view_payload)
            logger.info("Successfully published App Home for user=%s", user_id)
        except Exception as exc:
            logger.error(
                "Failed to publish App Home view for user=%s: %s", user_id, exc
            )
