from __future__ import annotations

import json
import re
from collections.abc import Mapping
from typing import Any

from slack_sdk.web.async_client import AsyncWebClient

from app.connectors.hubspot_slack.ui.modal_builder import ModalBuilder
from app.core.logging import get_logger
from app.core.models.ui import ModalMetadata, UnifiedCard
from app.db.records import IntegrationRecord
from app.domains.messaging.slack.service import SlackMessagingService
from app.utils.constants import CREATE_RECORD_CALLBACK_ID

from .base import (
    InteractionContext,
    InteractionHandler,
    interaction_handler,
    slack_error_handling,
)

logger = get_logger("modal_handlers")


class ModalHandler(InteractionHandler):
    @interaction_handler("add_note_modal")
    async def _handle_add_note_submission(
        self,
        *,
        payload: Mapping[str, Any],
        integration: IntegrationRecord,
        messaging_service: SlackMessagingService,
        context: InteractionContext,
        **kwargs: Any,
    ) -> None:
        view = payload.get("view", {})
        metadata = self._parse_modal_metadata(view.get("private_metadata", ""))
        object_type = metadata.object_type
        object_id = metadata.object_id
        channel_id = metadata.channel_id
        response_url = metadata.response_url
        if not object_type or not object_id:
            logger.warning("Missing object context in metadata")
            return
        values = view.get("state", {}).get("values", {})
        note_content = ""
        for block_id, actions in values.items():
            if "content" in actions:
                note_content = actions["content"].get("value", "")
                break
        if not note_content:
            logger.warning("Empty note content submitted")
            return
        await self.hubspot.create_note(
            workspace_id=integration.workspace_id,
            content=note_content,
            associated_id=object_id,
            associated_type=object_type,
        )
        try:
            sender_name = str(payload.get("user", {}).get("name", "Slack User"))
            await self.hubspot.publish_app_event(
                workspace_id=integration.workspace_id,
                event_template_id="slack-message-sent",
                object_type=object_type,
                object_id=object_id,
                properties={
                    "message_body": note_content,
                    "channel_name": f"<#{channel_id}>" if channel_id else "DM",
                    "sender_name": sender_name,
                },
            )
        except Exception as e:
            logger.warning(
                "Failed to publish custom timeline event "
                "(expected if app not yet uploaded to portal): %s",
                e,
            )
        user_id = context.user_id
        msg = "✅ Note successfully logged to HubSpot!"
        if response_url:
            await messaging_service.send_via_response_url(
                response_url=response_url, text=msg
            )
        elif channel_id and user_id:
            client = AsyncWebClient(
                token=integration.credentials.get("slack_bot_token")
            )
            try:
                await client.chat_postEphemeral(
                    channel=str(channel_id), user=user_id, text=msg
                )
            except Exception:
                pass
        return

    @interaction_handler("update_lead_type_modal")
    async def _handle_update_lead_type_submission(
        self,
        *,
        payload: Mapping[str, Any],
        integration: IntegrationRecord,
        messaging_service: SlackMessagingService,
        context: InteractionContext,
        **kwargs: Any,
    ) -> None:
        view = payload.get("view", {})
        metadata = self._parse_modal_metadata(view.get("private_metadata", ""))
        deal_id = metadata.deal_id
        channel_id = metadata.channel_id
        response_url = metadata.response_url
        values = view.get("state", {}).get("values", {})
        lead_type = ""
        for block in values.values():
            if "lead_type_input" in block:
                lead_type = block["lead_type_input"].get("value", "")
                break
        if not deal_id:
            logger.warning("Missing deal_id in metadata for update_lead_type_modal")
            return
        async with slack_error_handling(
            "update Lead Type",
            payload,
            messaging_service,
            response_url=response_url,
        ):
            await self.hubspot.update_deal(
                workspace_id=integration.workspace_id,
                deal_id=deal_id,
                properties={"hs_lead_type": lead_type},
            )
            user_id = context.user_id
            msg = "✅ Lead Type updated for deal!"
            if response_url:
                await messaging_service.send_via_response_url(
                    response_url=response_url, text=msg
                )
            elif channel_id and user_id:
                client = await self.integration_service.get_slack_client(integration)
                try:
                    await client.chat_postEphemeral(
                        channel=str(channel_id), user=user_id, text=msg
                    )
                except Exception:
                    pass
        return

    @interaction_handler("post_mortem_submission")
    async def _handle_post_mortem_submission(
        self,
        *,
        payload: Mapping[str, Any],
        integration: IntegrationRecord,
        messaging_service: SlackMessagingService,
        context: InteractionContext,
        **kwargs: Any,
    ) -> None:
        view = payload.get("view", {})
        metadata = self._parse_modal_metadata(view.get("private_metadata", ""))
        deal_id = metadata.deal_id
        stage_id = metadata.stage_id
        channel_id = metadata.channel_id
        response_url = metadata.response_url
        values = view.get("state", {}).get("values", {})
        properties = {"dealstage": stage_id}
        won_reason = ""
        lost_reason = ""
        for block in values.values():
            if "closed_won_reason" in block:
                won_reason = block["closed_won_reason"].get("value", "")
            if "closed_lost_reason" in block:
                lost_reason = (
                    block["closed_lost_reason"]
                    .get("selected_option", {})
                    .get("value", "")
                )
        if won_reason:
            properties["closed_won_reason"] = won_reason
        if lost_reason:
            properties["closed_lost_reason"] = lost_reason
        if not deal_id:
            logger.warning("Missing deal_id for post_mortem_submission")
            return
        async with slack_error_handling(
            "record post-mortem",
            payload,
            messaging_service,
            response_url=response_url,
        ):
            await self.hubspot.update_deal(
                workspace_id=integration.workspace_id,
                deal_id=deal_id,
                properties=properties,
            )
            note = f"Post-Mortem for {stage_id}: "
            if won_reason:
                note += f"Won Reason: {won_reason}. "
            if lost_reason:
                note += f"Lost Reason: {lost_reason}."
            if not deal_id:
                logger.warning("Missing deal_id for post_mortem_note")
            else:
                await self.hubspot.create_note(
                    workspace_id=integration.workspace_id,
                    content=note,
                    associated_id=deal_id,
                    associated_type="deal",
                )
            user_id = context.user_id
            msg = f"✅ Post-mortem recorded and deal stage updated to {stage_id}!"
            if response_url:
                await messaging_service.send_via_response_url(
                    response_url=response_url, text=msg
                )
            elif channel_id and user_id:
                client = await self.integration_service.get_slack_client(integration)
                try:
                    await client.chat_postEphemeral(
                        channel=str(channel_id), user=user_id, text=msg
                    )
                except Exception:
                    pass
        return

    @interaction_handler("calculator_submission")
    async def _handle_calculator_submission(
        self,
        *,
        payload: Mapping[str, Any],
        integration: IntegrationRecord,
        messaging_service: SlackMessagingService,
        context: InteractionContext,
        **kwargs: Any,
    ) -> None:
        view = payload.get("view", {})
        metadata = self._parse_modal_metadata(view.get("private_metadata", ""))
        deal_id = metadata.deal_id
        channel_id = metadata.channel_id
        response_url = metadata.response_url
        values = view.get("state", {}).get("values", {})
        qty = 1.0
        price = 0.0
        disc = 0.0
        for block in values.values():
            if "quantity" in block:
                qty = float(block["quantity"].get("value", "1") or "1")
            if "unit_price" in block:
                price = float(block["unit_price"].get("value", "0") or "0")
            if "discount_percent" in block:
                disc = float(block["discount_percent"].get("value", "0") or "0")
        total = qty * price * (1 - disc / 100)
        if not deal_id:
            logger.warning("Missing deal_id in metadata for calculator_submission")
            return
        async with slack_error_handling(
            "calculate deal amount",
            payload,
            messaging_service,
            response_url=response_url,
        ):
            await self.hubspot.update_deal(
                workspace_id=integration.workspace_id,
                deal_id=deal_id,
                properties={"amount": str(total)},
            )
            user_id = context.user_id
            msg = f"✅ Calculated total `${total:,.2f}` saved to deal amount!"
            if response_url:
                await messaging_service.send_via_response_url(
                    response_url=response_url, text=msg
                )
            elif channel_id and user_id:
                client = await self.integration_service.get_slack_client(integration)
                try:
                    await client.chat_postEphemeral(
                        channel=str(channel_id), user=user_id, text=msg
                    )
                except Exception:
                    pass
        return

    @interaction_handler("next_step_enforcement_submission")
    async def _handle_next_step_enforcement_submission(
        self,
        *,
        payload: Mapping[str, Any],
        integration: IntegrationRecord,
        messaging_service: SlackMessagingService,
        context: InteractionContext,
        **kwargs: Any,
    ) -> None:
        view = payload.get("view", {})
        metadata = self._parse_modal_metadata(view.get("private_metadata", ""))
        deal_id = metadata.deal_id
        stage_id = metadata.stage_id
        channel_id = metadata.channel_id
        response_url = metadata.response_url
        values = view.get("state", {}).get("values", {})
        next_step = ""
        for block in values.values():
            if "next_step" in block:
                next_step = block["next_step"].get("value", "")
                break
        if not deal_id:
            logger.warning("Missing deal_id in metadata for next_step_enforcement")
            return
        async with slack_error_handling(
            "enforce next step",
            payload,
            messaging_service,
            response_url=response_url,
        ):
            try:
                await self.hubspot.update_deal(
                    workspace_id=integration.workspace_id,
                    deal_id=deal_id,
                    properties={"dealstage": stage_id, "hs_next_step": next_step},
                )
                msg = f"✅ Next step set and deal stage updated to {stage_id}!"
            except Exception as exc:
                if "PROPERTY_DOESNT_EXIST" in str(exc) or "VALIDATION_ERROR" in str(
                    exc
                ):
                    logger.warning(
                        "Property hs_next_step failed, falling back to dealstage only"
                    )
                    await self.hubspot.update_deal(
                        workspace_id=integration.workspace_id,
                        deal_id=deal_id,
                        properties={"dealstage": stage_id},
                    )
                    msg = (
                        f"✅ Deal stage updated to {stage_id}, "
                        "but Next Step property is missing in HubSpot."
                    )
                else:
                    raise exc

            user_id = context.user_id
            if response_url:
                await messaging_service.send_via_response_url(
                    response_url=response_url, text=msg
                )
            elif channel_id and user_id:
                client = await self.integration_service.get_slack_client(integration)
                try:
                    await client.chat_postEphemeral(
                        channel=str(channel_id), user=user_id, text=msg
                    )
                except Exception:
                    pass
        return

    @interaction_handler("reassign_owner_submission")
    async def _handle_reassign_owner_submission(
        self,
        *,
        payload: Mapping[str, Any],
        integration: IntegrationRecord,
        messaging_service: SlackMessagingService,
        context: InteractionContext,
        **kwargs: Any,
    ) -> None:
        view = payload.get("view", {})
        metadata = view.get("private_metadata", "")
        try:
            meta = json.loads(metadata)
            object_type = meta.get("object_type")
            object_id = meta.get("object_id")
            channel_id = meta.get("channel_id")
            response_url = meta.get("response_url")
        except Exception:
            PARTS_MIN_LEN = 2
            parts = str(metadata).split(":")
            if len(parts) >= PARTS_MIN_LEN:
                object_type, object_id = (parts[0], parts[1])
            else:
                object_type, object_id = ("deal", parts[0])
            channel_id = None
            response_url = None
        values = view.get("state", {}).get("values", {})
        new_owner_id = ""
        for block in values.values():
            if "hubspot_owner_id" in block:
                new_owner_id = (
                    block["hubspot_owner_id"].get("selected_option", {}).get("value")
                )
                break
        async with slack_error_handling(
            "reassign owner", payload, messaging_service, response_url=response_url
        ):
            if object_type == "contact":
                await self.hubspot.update_contact(
                    workspace_id=integration.workspace_id,
                    contact_id=object_id,
                    properties={"hubspot_owner_id": new_owner_id},
                )
            else:
                await self.hubspot.update_deal(
                    workspace_id=integration.workspace_id,
                    deal_id=object_id,
                    properties={"hubspot_owner_id": new_owner_id},
                )
            user_id = context.user_id
            msg = "✅ Owner successfully reassigned!"
            if response_url:
                await messaging_service.send_via_response_url(
                    response_url=response_url, text=msg
                )
            elif channel_id and user_id:
                client = await self.integration_service.get_slack_client(integration)
                try:
                    await client.chat_postEphemeral(
                        channel=str(channel_id), user=user_id, text=msg
                    )
                except Exception:
                    pass

    @interaction_handler(CREATE_RECORD_CALLBACK_ID)
    async def _handle_create_record_submission(
        self,
        *,
        payload: Mapping[str, Any],
        integration: IntegrationRecord,
        messaging_service: SlackMessagingService,
        context: InteractionContext,
        **kwargs: Any,
    ) -> None:
        """Process the generic record creation modal submission."""
        view = payload.get("view", {})
        callback_id = view.get("callback_id", "")
        parts = callback_id.split(":")
        if len(parts) < 2:
            return
        object_type = parts[1]
        state_values = view.get("state", {}).get("values", {})
        properties = {}
        for block_id, actions in state_values.items():
            for action_id, action_data in actions.items():
                value = action_data.get("value")
                if value is None:
                    value = action_data.get("selected_date")
                if value is None:
                    selected_option = action_data.get("selected_option")
                    if selected_option:
                        value = selected_option.get("value")
                if value:
                    properties[action_id] = value
        association = None
        assoc_actions = state_values.get("block_association", {})
        if "association_search" in assoc_actions:
            association = (
                assoc_actions["association_search"]
                .get("selected_option", {})
                .get("value")
            )
        if object_type == "task":
            await self._handle_task_submission(
                integration=integration,
                properties=properties,
                association=association,
                messaging_service=messaging_service,
                response_url=view.get("private_metadata"),
                channel_id=None,
                user_id=context.user_id,
                context=context,
            )
            return
        if object_type == "ticket":
            await self._handle_ticket_submission(
                integration=integration,
                properties=properties,
                association=association,
                messaging_service=messaging_service,
                user_id=context.user_id,
                context=context,
            )
            return
        hubspot_client = await self.hubspot.get_client(integration.workspace_id)
        try:
            result = await hubspot_client.create_object(object_type, properties)
            logger.info("Created %s: %s", object_type, result.get("id"))
            metadata = view.get("private_metadata")
            channel_id = None
            response_url = None
            if metadata:
                try:
                    meta = json.loads(metadata)
                    channel_id = meta.get("channel_id")
                    response_url = meta.get("response_url")
                except Exception:
                    pass
            user_id = context.user_id
            msg = f"✅ Successfully created {object_type.capitalize()}!"
            if response_url:
                await messaging_service.send_via_response_url(
                    response_url=response_url, text=msg
                )
            elif channel_id and user_id:
                client = AsyncWebClient(
                    token=integration.credentials.get("slack_bot_token")
                )
                await client.chat_postEphemeral(
                    channel=str(channel_id), user=user_id, text=msg
                )
            elif user_id:
                client = AsyncWebClient(
                    token=integration.credentials.get("slack_bot_token")
                )
                await client.chat_postMessage(channel=user_id, text=msg)
        except Exception as exc:
            logger.exception("Failed to create object: %s")
            user_id = context.user_id
            if user_id:
                client = AsyncWebClient(
                    token=integration.credentials.get("slack_bot_token")
                )
                await client.chat_postMessage(
                    channel=user_id,
                    text=f"❌ Failed to create {object_type}: {str(exc)}",
                )

    def _parse_modal_metadata(self, metadata: str) -> ModalMetadata:
        """Parses Slack modal metadata string into a typed ModalMetadata object.

        Handles both JSON-serialized metadata and legacy colon-separated strings.
        Ensures robust parsing to prevent hidden KeyErrors and improves readability.

        Args:
            metadata (str): The raw metadata string from Slack view payload.

        Returns:
            ModalMetadata: A typed representation of the metadata fields.

        """
        if not metadata:
            return ModalMetadata()
        try:
            return ModalMetadata.model_validate_json(metadata)
        except Exception:
            pass
        try:
            raw = json.loads(metadata)
            return ModalMetadata(**raw)
        except Exception:
            pass
        parts = metadata.split(":")
        if len(parts) >= 2:
            if parts[0] in ("deal", "contact", "company", "task", "ticket"):
                return ModalMetadata(object_type=parts[0], object_id=parts[1])
            return ModalMetadata(deal_id=parts[0], stage_id=parts[1])
        return ModalMetadata(deal_id=metadata)

    @interaction_handler("open_add_note_modal")
    async def _handle_open_add_note_modal(
        self,
        value: str,
        integration: IntegrationRecord,
        messaging_service: SlackMessagingService,
        context: InteractionContext,
        trigger_id: str | None,
        **kwargs: Any,
    ) -> None:
        parts = value.split(":")
        if len(parts) < 3:
            logger.warning("Malformed add_note value=%s", value)
            return
        obj_type = parts[1]
        object_id = parts[2]
        if not trigger_id:
            logger.error("Missing trigger_id for modal")
            return
        if not await self.integration_service.check_feature_access(
            integration.workspace_id, "note_logging"
        ):
            return await self._handle_gated_click(
                "note_logging", trigger_id, integration, messaging_service
            )
        try:
            channel_id = context.channel_id
            response_url = context.response_url
            metadata = json.dumps(
                {
                    "object_type": obj_type,
                    "object_id": object_id,
                    "channel_id": channel_id,
                    "response_url": response_url,
                }
            )
            modal = messaging_service.cards.build_note_modal(
                obj_type, object_id, metadata=metadata
            )
            slack_channel = messaging_service.integration_service.slack_channel
            await slack_channel.open_view(
                bot_token=integration.credentials["slack_bot_token"],
                trigger_id=trigger_id,
                view=modal,
            )
            logger.info("Opened add_note modal for object_id=%s", object_id)
        except Exception as exc:
            logger.exception("Failed to open add note modal: %s")
            response_url = context.response_url
            if response_url:
                await messaging_service.send_via_response_url(
                    response_url=response_url,
                    text=f"❌ Failed to open note modal: {str(exc)}",
                )
            else:
                user_id = str(kwargs.get("payload", {}).get("user", {}).get("id", ""))
                if user_id:
                    client = AsyncWebClient(
                        token=integration.credentials.get("slack_bot_token")
                    )
                    error_msg = f"❌ Failed to open note modal: {str(exc)}"
                    channel_id = context.channel_id
                    if channel_id:
                        await client.chat_postEphemeral(
                            channel=str(channel_id), user=user_id, text=error_msg
                        )
                    else:
                        try:
                            await client.chat_postMessage(
                                channel=user_id, text=error_msg
                            )
                        except Exception:
                            pass

    @interaction_handler("open_update_lead_type_modal")
    async def _handle_open_update_lead_type_modal(
        self,
        value: str,
        integration: IntegrationRecord,
        messaging_service: SlackMessagingService,
        context: InteractionContext,
        trigger_id: str | None,
        **kwargs: Any,
    ) -> None:
        parts = value.split(":")
        if len(parts) < 2:
            logger.warning("Malformed update_lead_type value=%s", value)
            return
        deal_id = parts[1]
        if not trigger_id:
            return
        view_id = await self._show_loading(trigger_id, "Loading...", integration)
        try:
            deal = await self.hubspot.get_deal(
                workspace_id=integration.workspace_id, object_id=deal_id
            )
            current_value = (
                (deal.get("properties") or {}).get("hs_lead_type", "") if deal else ""
            )
            modal = messaging_service.cards.build_update_lead_type_modal(
                deal_id, current_value
            )
            if view_id:
                await self._update_modal(
                    view_id, modal, "Update Lead Type", integration
                )
            else:
                await self._open_modal(
                    trigger_id, modal, "Update Lead Type", integration
                )
        except Exception:
            logger.exception("Failed to open lead type modal: %s")

    @interaction_handler("reassign_owner")
    async def _handle_open_reassign_modal(
        self,
        value: str,
        integration: IntegrationRecord,
        messaging_service: SlackMessagingService,
        context: InteractionContext,
        trigger_id: str | None,
        **kwargs: Any,
    ) -> None:
        """Fetch owners and open reassign modal."""
        parts = value.split(":")
        if len(parts) < 2:
            return
        PARTS_OBJECT_ID_INDEX = 2
        PARTS_TYPE_INDEX = 1
        PARTS_REQ_LEN = 3
        if len(parts) >= PARTS_REQ_LEN:
            obj_type = parts[PARTS_TYPE_INDEX]
            object_id = parts[PARTS_OBJECT_ID_INDEX]
        else:
            obj_type = "deal"
            object_id = parts[1]
        if not trigger_id:
            return
        view_id = await self._show_loading(trigger_id, "Loading Owners...", integration)
        try:
            hubspot_client = await self.hubspot.get_client(integration.workspace_id)
            owners = await hubspot_client.get_owners()
            channel_id = context.channel_id
            response_url = context.response_url
            metadata = json.dumps(
                {
                    "object_type": obj_type,
                    "object_id": object_id,
                    "channel_id": channel_id,
                    "response_url": response_url,
                }
            )
            modal = messaging_service.cards.build_reassign_modal(
                f"{obj_type}:{object_id}", owners, metadata=metadata
            )
            if view_id:
                await self._update_modal(view_id, modal, "Reassign Owner", integration)
            else:
                await self._open_modal(trigger_id, modal, "Reassign Owner", integration)
        except Exception as exc:
            logger.exception("Failed to open reassign modal: %s")
            response_url = context.response_url
            if response_url:
                await messaging_service.send_via_response_url(
                    response_url=response_url,
                    text=f"❌ Failed to open reassign modal: {str(exc)}",
                )

    @interaction_handler("open_calculator")
    async def _handle_open_calculator_modal(
        self,
        value: str,
        integration: IntegrationRecord,
        messaging_service: SlackMessagingService,
        context: InteractionContext,
        trigger_id: str | None,
        **kwargs: Any,
    ) -> None:
        """Fetch deal and open calculator modal."""
        parts = value.split(":")
        if len(parts) < 2:
            return
        deal_id = parts[1]
        if not trigger_id:
            return
        if not await self.integration_service.check_feature_access(
            integration.workspace_id, "pricing_calculator"
        ):
            return await self._handle_gated_click(
                "pricing_calculator", trigger_id, integration, messaging_service
            )
        view_id = await self._show_loading(
            trigger_id, "Fetching Deal Details...", integration
        )
        try:
            deal = await self.hubspot.get_deal(
                workspace_id=integration.workspace_id, object_id=deal_id
            )
            if not deal:
                logger.warning("Deal not found for id=%s", deal_id)
                return
            props = deal.get("properties") or {}
            amount_str = props.get("amount", "0")
            amount = float(amount_str) if amount_str else 0.0
            channel_id = context.channel_id
            response_url = context.response_url
            metadata = json.dumps(
                {
                    "deal_id": deal_id,
                    "channel_id": channel_id,
                    "response_url": response_url,
                }
            )
            modal = messaging_service.cards.build_pricing_calculator_modal(
                deal_id, amount, metadata=metadata
            )
            if view_id:
                await self._update_modal(view_id, modal, "Deal Calculator", integration)
            else:
                await self._open_modal(
                    trigger_id, modal, "Deal Calculator", integration
                )
        except Exception as exc:
            logger.exception("Failed to open calculator modal: %s")
            response_url = context.response_url
            if response_url:
                await messaging_service.send_via_response_url(
                    response_url=response_url,
                    text=f"❌ Failed to open calculator modal: {str(exc)}",
                )

    @interaction_handler("schedule_meeting")
    async def _handle_open_meeting_modal(
        self,
        value: str,
        integration: IntegrationRecord,
        messaging_service: SlackMessagingService,
        context: InteractionContext,
        trigger_id: str | None,
        **kwargs: Any,
    ) -> None:
        """Open meeting modal for contact."""
        parts = value.split(":")
        if len(parts) < 2:
            return
        contact_id = parts[1]
        if not trigger_id:
            return
        if not await self.integration_service.check_feature_access(
            integration.workspace_id, "meeting_scheduler"
        ):
            return await self._handle_gated_click(
                "meeting_scheduler", trigger_id, integration, messaging_service
            )
        view_id = await self._show_loading(trigger_id, "Loading...", integration)
        try:
            channel_id = context.channel_id
            response_url = context.response_url
            metadata = json.dumps(
                {
                    "contact_id": contact_id,
                    "channel_id": channel_id,
                    "response_url": response_url,
                }
            )
            modal = messaging_service.cards.build_meeting_modal(
                contact_id, metadata=metadata
            )
            if view_id:
                await self._update_modal(
                    view_id, modal, "Schedule Meeting", integration
                )
            else:
                await self._open_modal(
                    trigger_id, modal, "Schedule Meeting", integration
                )
        except Exception as exc:
            logger.exception("Failed to open meeting modal: %s")
            response_url = context.response_url
            if response_url:
                await messaging_service.send_via_response_url(
                    response_url=response_url,
                    text=f"❌ Failed to open meeting modal: {str(exc)}",
                )

    @interaction_handler("open_ai_recap_modal")
    async def _handle_open_ai_recap_modal(
        self,
        value: str,
        integration: IntegrationRecord,
        messaging_service: SlackMessagingService,
        context: InteractionContext,
        trigger_id: str | None,
        **kwargs: Any,
    ) -> None:
        """Fetch thread, summarize, and show review modal."""
        parts = value.split(":")
        if len(parts) < 3:
            return
        obj_type = parts[1]
        obj_id = parts[2]
        if not trigger_id:
            return
        if not await self.integration_service.check_feature_access(
            integration.workspace_id, "ai_insights"
        ):
            return await self._handle_gated_click(
                "ai_insights", trigger_id, integration, messaging_service
            )
        view_id = await self._show_loading(
            trigger_id, "Summarizing Thread...", integration
        )
        try:
            workspace_id = integration.workspace_id
            slack_channel = messaging_service.integration_service.slack_channel
            storage = self.integration_service.storage
            mapping = await storage.thread_mappings.fetch_single(
                {"workspace_id": workspace_id, "object_id": obj_id}
            )
            if not mapping:
                response_url = context.response_url
                if response_url:
                    await messaging_service.send_via_response_url(
                        response_url=response_url,
                        text=f"No Slack thread found for {obj_type} {obj_id} to recap.",
                    )
                else:
                    client = AsyncWebClient(
                        token=integration.credentials["slack_bot_token"]
                    )
                    await client.chat_postMessage(
                        channel=kwargs.get("payload", {}).get("user", {}).get("id", ""),
                        text=f"No Slack thread found for {obj_type} {obj_id} to recap.",
                    )
                return
            replies = await slack_channel.get_thread_replies(
                channel_id=mapping.channel_id, thread_ts=mapping.thread_ts
            )
            from app.domains.ai.service import AIThreadSummary

            analysis = await self.ai.analyze_conversation({"messages": replies})
            summary = AIThreadSummary(
                summary=analysis.summary, key_points=[], sentiment=analysis.status
            )
            channel_id = context.channel_id
            response_url = context.response_url
            metadata = json.dumps(
                {
                    "object_type": obj_type,
                    "object_id": obj_id,
                    "channel_id": channel_id,
                    "response_url": response_url,
                }
            )
            modal = messaging_service.cards.build_ai_recap_modal(
                obj_type, obj_id, summary, metadata=metadata
            )
            if view_id:
                await self._update_modal(view_id, modal, "AI Recap Review", integration)
            else:
                await slack_channel.open_view(
                    bot_token=integration.credentials["slack_bot_token"],
                    trigger_id=trigger_id,
                    view=modal,
                )
        except Exception as exc:
            logger.exception("Failed to open AI Recap modal: %s")
            response_url = context.response_url
            if response_url:
                await messaging_service.send_via_response_url(
                    response_url=response_url,
                    text=f"❌ Failed to open AI Recap modal: {str(exc)}",
                )

    async def _open_modal(
        self,
        trigger_id: str | None,
        view_or_card: dict[str, Any] | UnifiedCard,
        title: str,
        integration: IntegrationRecord,
    ) -> str | None:
        """Helper to render a UnifiedCard or use a raw View and open it as a
        Slack modal.

        # noqa: E501
        """
        if not trigger_id:
            logger.error("Missing trigger_id for opening modal: %s", title)
            return None
        bot_token = integration.credentials.get("slack_bot_token")
        if not bot_token:
            logger.error("Missing bot token for opening modal")
            return None
        try:
            from app.domains.crm.ui.card_builder import CardBuilder

            if isinstance(view_or_card, dict):
                modal = view_or_card
            else:
                builder = CardBuilder()
                modal = builder.build_card_modal(view_or_card, title=title)
            resp = await self.integration_service.slack_channel.open_view(
                bot_token=bot_token, trigger_id=trigger_id, view=modal
            )
            if not resp or not resp.get("ok"):
                logger.error(
                    "Failed to open modal '%s': %s",
                    title,
                    resp.get("error") if resp else "No response",
                )
                return None
            view = resp.get("view")
            if not view or not isinstance(view, dict):
                return None
            logger.info("Modal '%s' opened for trigger_id=%s", title, trigger_id[:8])
            return str(view.get("id"))
        except Exception as exc:
            logger.error("Failed to open modal '%s': %s", title, exc, exc_info=True)
            return None

    @interaction_handler("ai_recap_submission_modal")
    async def _handle_ai_recap_submission(
        self,
        *,
        payload: Mapping[str, Any],
        integration: IntegrationRecord,
        messaging_service: SlackMessagingService,
        context: InteractionContext,
        **kwargs: Any,
    ) -> None:
        """Save the AI summary to HubSpot as a note."""
        view = payload.get("view", {})
        metadata = view.get("private_metadata", "")
        try:
            meta = json.loads(metadata)
            object_type = meta.get("object_type")
            object_id = meta.get("object_id")
            channel_id = meta.get("channel_id")
            response_url = meta.get("response_url")
        except Exception:
            parts = str(metadata).split(":")
            object_type = parts[0] if len(parts) > 0 else ""
            object_id = parts[1] if len(parts) > 1 else ""
            channel_id = None
            response_url = None
        if not object_id or not object_type:
            return
        obj_type = object_type
        obj_id = object_id
        blocks = view.get("blocks", [])
        summary_text = "AI Recap Summary"
        for block in blocks:
            if block.get("type") == "section" and "*Summary:*" in block.get(
                "text", {}
            ).get("text", ""):
                summary_text = block["text"]["text"]
                break
        try:
            await self.hubspot.create_note(
                workspace_id=integration.workspace_id,
                content=f"--- AI RECAP ---\n{summary_text}",
                associated_id=obj_id,
                associated_type=obj_type,
            )
            logger.info("AI Recap saved as note for %s %s", obj_type, obj_id)
            user_id = context.user_id
            msg = f"✅ AI Recap saved to HubSpot as a note for {obj_type} {obj_id}!"
            if response_url:
                await messaging_service.send_via_response_url(
                    response_url=response_url, text=msg
                )
            elif channel_id and user_id:
                client = AsyncWebClient(
                    token=integration.credentials.get("slack_bot_token")
                )
                try:
                    await client.chat_postEphemeral(
                        channel=str(channel_id), user=user_id, text=msg
                    )
                except Exception:
                    pass
        except Exception as exc:
            logger.exception("Failed to save AI Recap: %s")
            user_id = context.user_id
            if user_id:
                error_msg = f"❌ Failed to save AI Recap: {str(exc)}"
                if response_url:
                    await messaging_service.send_via_response_url(
                        response_url=response_url, text=error_msg
                    )
                elif channel_id:
                    client = AsyncWebClient(
                        token=integration.credentials.get("slack_bot_token")
                    )
                    try:
                        await client.chat_postEphemeral(
                            channel=str(channel_id), user=user_id, text=error_msg
                        )
                    except Exception:
                        pass

    @interaction_handler("schedule_meeting_modal")
    async def _handle_schedule_meeting_submission(
        self,
        *,
        payload: Mapping[str, Any],
        integration: IntegrationRecord,
        messaging_service: SlackMessagingService,
        context: InteractionContext,
        **kwargs: Any,
    ) -> None:
        """Process the schedule meeting modal submission."""
        view = payload.get("view", {})
        metadata = view.get("private_metadata", "")
        try:
            meta = json.loads(metadata)
            contact_id = meta.get("contact_id") or meta.get("object_id")
            channel_id = meta.get("channel_id")
            response_url = meta.get("response_url")
        except Exception:
            contact_id = str(metadata)
            channel_id = None
            response_url = None
        state_values = view.get("state", {}).get("values", {})
        title = ""
        date_str = ""
        time_str = ""
        body = ""
        for block_id, actions in state_values.items():
            if "title_input" in actions:
                title = actions["title_input"].get("value")
            elif "date_input" in actions:
                date_str = actions["date_input"].get("selected_date")
            elif "time_input" in actions:
                time_str = actions["time_input"].get("selected_time")
            elif "body_input" in actions:
                body = actions["body_input"].get("value")
        if not title or not date_str or (not time_str):
            logger.warning("Incomplete meeting data submitted")
            return
        from datetime import datetime

        try:
            dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            int(dt.timestamp() * 1000)
        except Exception:
            logger.exception("Failed to parse meeting date/time: %s")
            return
        from datetime import datetime, timedelta

        from app.utils.transformers import to_hubspot_iso8601

        properties = {
            "hs_meeting_title": title,
            "hs_meeting_body": body or "Scheduled via Slack",
            "hs_meeting_start_time": to_hubspot_iso8601(dt),
            "hs_meeting_end_time": to_hubspot_iso8601(dt + timedelta(minutes=30)),
            "hs_timestamp": to_hubspot_iso8601(dt),
        }
        try:
            result = await self.hubspot.create_meeting(
                workspace_id=integration.workspace_id,
                properties=properties,
                contact_id=contact_id,
            )
            meeting_id = result.get("id", "unknown")
            logger.info("Meeting successfully created meeting_id=%s", meeting_id)
            user_id = context.user_id
            if user_id:
                msg = f"✅ *Meeting Scheduled!* \n_{title}_ at `{date_str} {time_str}`"
                if response_url:
                    await messaging_service.send_via_response_url(
                        response_url=response_url, text=msg
                    )
                elif channel_id:
                    client = AsyncWebClient(
                        token=integration.credentials.get("slack_bot_token")
                    )
                    await client.chat_postEphemeral(
                        channel=str(channel_id), user=user_id, text=msg
                    )
                else:
                    client = AsyncWebClient(
                        token=integration.credentials.get("slack_bot_token")
                    )
                    try:
                        await client.chat_postMessage(channel=user_id, text=msg)
                    except Exception:
                        pass
        except Exception as exc:
            logger.exception("Failed to create meeting: %s")
            user_id = context.user_id
            if user_id:
                error_msg = f"❌ Failed to schedule meeting: {str(exc)}"
                if response_url:
                    await messaging_service.send_via_response_url(
                        response_url=response_url, text=error_msg
                    )
                elif channel_id:
                    client = AsyncWebClient(
                        token=integration.credentials.get("slack_bot_token")
                    )
                    await client.chat_postEphemeral(
                        channel=str(channel_id), user=user_id, text=error_msg
                    )
                else:
                    client = AsyncWebClient(
                        token=integration.credentials.get("slack_bot_token")
                    )
                    try:
                        await client.chat_postMessage(channel=user_id, text=error_msg)
                    except Exception:
                        pass

    async def _handle_task_submission(
        self,
        integration: IntegrationRecord,
        properties: dict[str, Any],
        association: str | None,
        messaging_service: SlackMessagingService,
        context: InteractionContext,
        response_url: str | None,
        channel_id: str | None,
        user_id: str | None,
    ) -> None:
        """Specialized handler for task creation with associations."""
        from datetime import UTC, datetime

        from app.utils.transformers import to_hubspot_timestamp

        if "hs_task_due_date" in properties:
            date_str = properties.pop("hs_task_due_date")
            try:
                dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
                properties["hs_timestamp"] = str(to_hubspot_timestamp(dt))
            except ValueError:
                pass
        if "hs_timestamp" not in properties:
            properties["hs_timestamp"] = str(to_hubspot_timestamp(datetime.now(UTC)))
        hubspot_client = await self.hubspot.get_client(integration.workspace_id)
        task = await hubspot_client.create_object("tasks", properties)
        task_id = task["id"]
        if association:
            assoc_type, assoc_id = association.split(":")
            await self.hubspot.associate_object(
                workspace_id=integration.workspace_id,
                from_type="task",
                from_id=task_id,
                to_type=assoc_type,
                to_id=assoc_id,
            )

    async def _handle_ticket_submission(
        self,
        integration: IntegrationRecord,
        properties: dict[str, Any],
        association: str | None,
        messaging_service: SlackMessagingService,
        context: InteractionContext,
        user_id: str,
    ) -> None:
        """Handles complex ticket creation, channel
        provisioning, and Slack onboarding.
        """
        try:
            hubspot_client = await self.hubspot.get_client(integration.workspace_id)
            ticket = await hubspot_client.create_object("tickets", properties)
            ticket_id = ticket["id"]
            subject = properties.get("subject", "Support Ticket")
            logger.info("Created HubSpot ticket: %s", ticket_id)
            if association:
                assoc_type, assoc_id = association.split(":")
                await self.hubspot.associate_object(
                    workspace_id=integration.workspace_id,
                    from_type="ticket",
                    from_id=ticket_id,
                    to_type=assoc_type,
                    to_id=assoc_id,
                )
            channel_inst = await messaging_service.get_slack_channel()
            slack_client = channel_inst.get_slack_client()
            raw_name = f"ticket-{ticket_id}-{subject.lower()}"
            channel_name = re.sub("[^a-z0-9-]", "-", raw_name)[:80].strip("-")
            create_resp = await slack_client.conversations_create(
                name=channel_name, is_private=True
            )
            if not create_resp.get("ok"):
                logger.error(
                    "Failed to create Slack channel: %s", create_resp.get("error")
                )
                await slack_client.chat_postMessage(
                    channel=user_id,
                    text=(
                        f"✅ Created HubSpot ticket #{ticket_id}, "
                        f"but failed to create a private channel: "
                        f"`{create_resp.get('error')}`"
                    ),
                )
                return
            new_channel_id = create_resp["channel"]["id"]
            logger.info("Provisioned Slack channel: %s", new_channel_id)
            await slack_client.conversations_invite(
                channel=new_channel_id, users=[user_id]
            )
            builder = ModalBuilder()
            control_panel_blocks = builder.build_ticket_control_panel(
                ticket_id, subject
            )
            await slack_client.chat_postMessage(
                channel=new_channel_id,
                text=f"🎫 Ticket #{ticket_id} created!",
                blocks=control_panel_blocks,
            )
            success_msg = (
                f"✅ Ticket created! Join your support channel: <#{new_channel_id}>"
            )
            await slack_client.chat_postMessage(channel=user_id, text=success_msg)
        except Exception as exc:
            logger.exception("Ticket submission failed: %s")
            if user_id:
                try:
                    client = AsyncWebClient(
                        token=integration.credentials.get("slack_bot_token")
                    )
                    await client.chat_postMessage(
                        channel=user_id, text=f"❌ Failed to create ticket: {str(exc)}"
                    )
                except Exception:
                    pass
