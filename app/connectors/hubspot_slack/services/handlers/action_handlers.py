from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, cast

from app.core.exceptions import HubSpotAPIError
from app.core.logging import get_logger
from app.db.records import IntegrationRecord
from app.domains.crm.ui.card_builder import CardBuilder
from app.domains.messaging.slack.service import SlackMessagingService

from .base import (
    InteractionContext,
    InteractionHandler,
    interaction_handler,
    with_slack_error_handling,
)

logger = get_logger("action_handlers")


class ActionButtonHandler(InteractionHandler):
    @interaction_handler("update_deal_stage")
    @with_slack_error_handling("update_deal_stage")
    async def _handle_update_deal_stage(
        self,
        *,
        payload: Mapping[str, Any],
        integration: IntegrationRecord,
        messaging_service: SlackMessagingService,
        context: InteractionContext,
        **kwargs: Any,
    ) -> None:
        value = context.value or ""
        channel_id = context.channel_id
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
        is_pro = await self.integration_service.is_pro_workspace(
            integration.workspace_id
        )
        if is_pro:
            deal = await self.hubspot.get_deal(
                workspace_id=integration.workspace_id, object_id=deal_id
            )
            props = deal.get("properties", {}) if deal else {}
            response_url = context.response_url
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
                    trigger_id=context.trigger_id,
                    view=modal,
                )
                return
            if not props.get("hs_next_step"):
                modal = messaging_service.cards.build_next_step_enforcement_modal(
                    deal_id, new_stage_id, metadata=metadata
                )
                await messaging_service.integration_service.slack_channel.open_view(
                    bot_token=integration.credentials["slack_bot_token"],
                    trigger_id=context.trigger_id,
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
        response_url = context.response_url
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

    @interaction_handler("ticket_claim")
    @with_slack_error_handling("ticket_claim")
    async def _handle_ticket_claim(
        self,
        *,
        payload: Mapping[str, Any],
        integration: IntegrationRecord,
        messaging_service: SlackMessagingService,
        context: InteractionContext,
        **kwargs: Any,
    ) -> None:
        """Assigns the HubSpot ticket to the claiming Slack user."""
        if not context.value or not context.user_id or not context.channel_id:
            return
        ticket_id = context.value
        user_id = context.user_id
        channel_id = str(context.channel_id)
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

    @interaction_handler("ticket_close")
    @with_slack_error_handling("ticket_close")
    async def _handle_ticket_close(
        self,
        *,
        payload: Mapping[str, Any],
        integration: IntegrationRecord,
        messaging_service: SlackMessagingService,
        context: InteractionContext,
        **kwargs: Any,
    ) -> None:
        """Closes the HubSpot ticket and archives the Slack channel."""
        if not context.value or not context.user_id or not context.channel_id:
            return
        ticket_id = context.value
        user_id = context.user_id
        channel_id = str(context.channel_id)
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

    @interaction_handler("ticket_delete")
    @with_slack_error_handling("ticket_delete")
    async def _handle_ticket_delete(
        self,
        *,
        payload: Mapping[str, Any],
        integration: IntegrationRecord,
        messaging_service: SlackMessagingService,
        context: InteractionContext,
        **kwargs: Any,
    ) -> None:
        """Deletes the Slack channel (permanent archive)."""
        if not context.user_id or not context.channel_id:
            return
        user_id = context.user_id
        channel_id = str(context.channel_id)
        slack_channel = await messaging_service.get_slack_channel()
        slack_client = slack_channel.get_slack_client()
        await slack_client.chat_postMessage(
            channel=channel_id,
            text=f"🗑️ Ticket channel permanently removed by <@{user_id}>.",
        )
        await slack_client.conversations_archive(channel=channel_id)

    @interaction_handler("ticket_transcript")
    @with_slack_error_handling("ticket_transcript")
    async def _handle_ticket_transcript(
        self,
        *,
        payload: Mapping[str, Any],
        integration: IntegrationRecord,
        messaging_service: SlackMessagingService,
        context: InteractionContext,
        **kwargs: Any,
    ) -> None:
        """Placeholder for generating a conversation transcript."""
        response_url = context.response_url
        if response_url:
            await messaging_service.send_via_response_url(
                response_url=str(response_url),
                text="📄 Transcript generation is coming soon!",
            )

    @interaction_handler("gated_feature_click")
    @with_slack_error_handling("gated_feature_click")
    async def _handle_gated_click(
        self,
        *,
        payload: Mapping[str, Any],
        integration: IntegrationRecord,
        messaging_service: SlackMessagingService,
        context: InteractionContext,
        **kwargs: Any,
    ) -> None:
        action_id = kwargs.get("action_id", "")
        feature_id = action_id.split(":")[1] if ":" in action_id else action_id
        trigger_id = context.trigger_id
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
