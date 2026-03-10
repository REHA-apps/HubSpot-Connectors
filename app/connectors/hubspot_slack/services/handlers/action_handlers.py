from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, cast

from slack_sdk.web.async_client import AsyncWebClient

from app.core.exceptions import HubSpotAPIError
from app.core.logging import get_logger
from app.domains.crm.ui.card_builder import CardBuilder
from app.domains.messaging.slack.service import SlackMessagingService

from .base import InteractionHandler

logger = get_logger("action_handlers")


class ActionButtonHandler(InteractionHandler):
    async def handle(
        self,
        payload: Mapping[str, Any],
        integration: Any,
        messaging_service: SlackMessagingService,
        **kwargs: Any,
    ) -> Any:
        action_id = kwargs.get("action_id", "")
        if action_id == "update_deal_stage":
            return await self._handle_update_deal_stage(
                value=kwargs.get("value", ""),
                payload=payload,
                integration=integration,
                messaging_service=messaging_service,
                channel_id=kwargs.get("channel_id"),
            )
        elif action_id in (
            "ticket_claim",
            "ticket_close",
            "ticket_delete",
            "ticket_transcript",
        ):
            return await self._handle_ticket_action(
                action_id=action_id,
                payload=payload,
                integration=integration,
                messaging_service=messaging_service,
            )
        elif action_id.startswith("gated_feature_click:"):
            return await self._handle_gated_click(
                feature_id=action_id.split(":")[1] if ":" in action_id else action_id,
                trigger_id=kwargs.get("trigger_id"),
                integration=integration,
                messaging_service=messaging_service,
            )

    async def _handle_update_deal_stage(
        self,
        *,
        value: str,
        payload: Mapping[str, Any],
        integration: Any,
        messaging_service: SlackMessagingService,
        channel_id: str | None,
        **kwargs: Any,
    ) -> None:
        parts = value.split(":")
        if len(parts) < 2:
            logger.warning("Malformed update_deal_stage value=%s", value)
            return
        deal_id = parts[1]
        actions = payload.get("actions", [])
        if not actions:
            return
        selected_option = actions[0].get("selected_option")
        if not selected_option:
            return
        new_stage_id = selected_option.get("value")
        try:
            is_pro = await self.integration_service.is_pro_workspace(
                integration.workspace_id
            )
            if is_pro:
                deal = await self.hubspot.get_deal(
                    workspace_id=integration.workspace_id, object_id=deal_id
                )
                props = deal.get("properties", {}) if deal else {}
                response_url = payload.get("response_url")
                metadata = json.dumps(
                    {
                        "deal_id": deal_id,
                        "stage_id": new_stage_id,
                        "channel_id": channel_id,
                        "response_url": response_url,
                    }
                )
                if "won" in new_stage_id.lower() or "lost" in new_stage_id.lower():
                    modal = messaging_service.cards.build_post_mortem_modal(
                        deal_id, new_stage_id, metadata=metadata
                    )
                    await messaging_service.integration_service.slack_channel.open_view(
                        bot_token=integration.credentials["slack_bot_token"],
                        trigger_id=payload.get("trigger_id"),
                        view=modal,
                    )
                    return
                if not props.get("hs_next_step"):
                    modal = messaging_service.cards.build_next_step_enforcement_modal(
                        deal_id, new_stage_id, metadata=metadata
                    )
                    await messaging_service.integration_service.slack_channel.open_view(
                        bot_token=integration.credentials["slack_bot_token"],
                        trigger_id=payload.get("trigger_id"),
                        view=modal,
                    )
                    return
            await self.hubspot.update_deal(
                workspace_id=integration.workspace_id,
                deal_id=deal_id,
                properties={"dealstage": new_stage_id},
            )
            deal = await self.hubspot.get_deal(
                workspace_id=integration.workspace_id, object_id=deal_id
            )
            pipelines = await self.hubspot.get_deal_pipelines(integration.workspace_id)
            if not deal:
                await messaging_service.send_message(
                    workspace_id=integration.workspace_id,
                    channel=channel_id,
                    text="Error: Could not reload deal after update.",
                )
                return
            analysis = await self.ai.analyze_polymorphic(deal, "deal")
            unified_card = messaging_service.cards.build(
                deal, cast(Any, analysis), pipelines=pipelines, is_pro=is_pro
            )
            rendered = messaging_service.slack_renderer.render(unified_card)
            response_url = payload.get("response_url")
            if response_url:
                await messaging_service.send_via_response_url(
                    response_url=response_url,
                    replace_original=True,
                    blocks=rendered["blocks"],
                    text=f"Deal stage updated to {new_stage_id}",
                )
            else:
                await messaging_service.send_message(
                    workspace_id=integration.workspace_id,
                    channel=channel_id,
                    blocks=rendered["blocks"],
                    text="Deal stage updated.",
                )
        except Exception as exc:
            logger.error("Failed to update deal stage: %s", exc)
            user_id = str(payload.get("user", {}).get("id", ""))
            if user_id:
                client = AsyncWebClient(
                    token=integration.credentials.get("slack_bot_token")
                )
                await client.chat_postMessage(
                    channel=user_id, text=f"❌ Failed to update deal stage: {str(exc)}"
                )

    async def _handle_ticket_action(
        self,
        action_id: str,
        payload: Mapping[str, Any],
        integration: Any,
        messaging_service: SlackMessagingService,
    ) -> None:
        """Dispatcher for ticket Control Panel button actions."""
        actions = payload.get("actions", [])
        if not actions:
            return
        action = actions[0]
        ticket_id = action.get("value")
        if not ticket_id:
            return
        user_id = str(payload.get("user", {}).get("id") or "")
        channel_id = str(payload.get("channel", {}).get("id") or "")
        if not user_id or not channel_id:
            return
        if action_id == "ticket_claim":
            await self._handle_ticket_claim(
                ticket_id, user_id, channel_id, integration, messaging_service, payload
            )
        elif action_id == "ticket_close":
            await self._handle_ticket_close(
                ticket_id, user_id, channel_id, integration, messaging_service
            )
        elif action_id == "ticket_delete":
            await self._handle_ticket_delete(
                ticket_id, user_id, channel_id, integration, messaging_service
            )
        elif action_id == "ticket_transcript":
            await self._handle_ticket_transcript(
                ticket_id, user_id, channel_id, integration, messaging_service, payload
            )

    async def _handle_ticket_claim(
        self,
        ticket_id: str,
        user_id: str,
        channel_id: str,
        integration: Any,
        messaging_service: SlackMessagingService,
        payload: Mapping[str, Any],
    ) -> None:
        """Assigns the HubSpot ticket to the claiming Slack user."""
        try:
            slack_channel = await messaging_service.get_slack_channel()
            slack_client = slack_channel.get_slack_client()
            user_info = await slack_client.users_info(user=user_id)
            email = user_info.get("user", {}).get("profile", {}).get("email")
            if not email:
                raise HubSpotAPIError("Could not resolve email for Slack user.")
            owners = await self.hubspot.get_owners(integration.workspace_id)
            hs_owner = next((o for o in owners if o.get("email") == email), None)
            if not hs_owner:
                raise HubSpotAPIError(f"No HubSpot owner found for email {email}")
            hubspot_client = await self.hubspot.get_client(integration.workspace_id)
            await hubspot_client.request(
                "PATCH",
                f"objects/tickets/{ticket_id}",
                json={"properties": {"hubspot_owner_id": hs_owner["id"]}},
            )
            await slack_client.chat_postMessage(
                channel=channel_id,
                text=f"🙋\u200d♂️ <@{user_id}> has claimed this ticket.",
            )
        except Exception as exc:
            logger.error("Failed to claim ticket %s: %s", ticket_id, exc)
            response_url = payload.get("response_url")
            if response_url:
                await messaging_service.send_via_response_url(
                    response_url=str(response_url),
                    text=f"❌ Failed to claim ticket: {str(exc)}",
                )

    async def _handle_ticket_close(
        self,
        ticket_id: str,
        user_id: str,
        channel_id: str,
        integration: Any,
        messaging_service: SlackMessagingService,
    ) -> None:
        """Closes the HubSpot ticket and archives the Slack channel."""
        try:
            hubspot_client = await self.hubspot.get_client(integration.workspace_id)
            await hubspot_client.request(
                "PATCH",
                f"objects/tickets/{ticket_id}",
                json={"properties": {"hs_pipeline_stage": "4"}},
            )
            slack_channel = await messaging_service.get_slack_channel()
            slack_client = slack_channel.get_slack_client()
            await slack_client.chat_postMessage(
                channel=channel_id,
                text=f"🔒 Ticket closed by <@{user_id}>. Archiving channel...",
            )
            await slack_client.conversations_archive(channel=channel_id)
        except Exception as exc:
            logger.error("Failed to close ticket %s: %s", ticket_id, exc)

    async def _handle_ticket_delete(
        self,
        ticket_id: str,
        user_id: str,
        channel_id: str,
        integration: Any,
        messaging_service: SlackMessagingService,
    ) -> None:
        """Deletes the Slack channel (permanent archive)."""
        try:
            slack_channel = await messaging_service.get_slack_channel()
            slack_client = slack_channel.get_slack_client()
            await slack_client.chat_postMessage(
                channel=channel_id,
                text=f"🗑️ Ticket channel permanently removed by <@{user_id}>.",
            )
            await slack_client.conversations_archive(channel=channel_id)
        except Exception as exc:
            logger.error("Failed to delete ticket channel %s: %s", ticket_id, exc)

    async def _handle_ticket_transcript(
        self,
        ticket_id: str,
        user_id: str,
        channel_id: str,
        integration: Any,
        messaging_service: SlackMessagingService,
        payload: Mapping[str, Any],
    ) -> None:
        """Placeholder for generating a conversation transcript."""
        response_url = payload.get("response_url")
        if response_url:
            await messaging_service.send_via_response_url(
                response_url=str(response_url),
                text="📄 Transcript generation is coming soon!",
            )

    async def _handle_gated_click(
        self,
        feature_id: str,
        trigger_id: str | None,
        integration: Any,
        messaging_service: SlackMessagingService,
    ) -> None:
        """Shows the upgrade nudge modal when a gated feature is clicked.

        Args:
            feature_id: The ID of the feature they tried to access.
            trigger_id: The trigger ID from Slack to open a modal.
            integration: The integration record.
            messaging_service: The messaging service for Slack API calls.

        """
        if not trigger_id:
            return
        builder = CardBuilder()
        modal = builder.build_upgrade_nudge_modal(feature_name=feature_id)
        slack_channel = messaging_service.integration_service.slack_channel
        await slack_channel.open_view(
            bot_token=integration.credentials["slack_bot_token"],
            trigger_id=trigger_id,
            view=modal,
        )
