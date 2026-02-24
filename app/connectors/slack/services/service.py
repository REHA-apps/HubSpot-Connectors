from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any, cast

from slack_sdk.web.async_client import AsyncWebClient

from app.connectors.slack.services.channel_service import ChannelService
from app.connectors.slack.ui import ModalBuilder
from app.core.logging import CorrelationAdapter, get_logger
from app.core.models.ui import ModalMetadata, UnifiedCard
from app.domains.ai.service import AIService
from app.domains.crm.hubspot.service import HubSpotService
from app.domains.crm.integration_service import IntegrationService
from app.utils.constants import CREATE_RECORD_CALLBACK_ID

logger = get_logger("interaction.service")


class InteractionService:
    """Description:
    Core service for handling Slack interactive components (buttons, modals, menus).
    """

    def __init__(
        self,
        corr_id: str,
        *,
        integration_service: IntegrationService | None = None,
        ai: AIService | None = None,
    ):
        self.corr_id = corr_id
        self.log = CorrelationAdapter(logger, corr_id)
        self.integration_service = integration_service or IntegrationService(corr_id)
        self.hubspot = HubSpotService(corr_id)
        self.ai = ai or AIService(corr_id)

    async def handle_interaction(self, payload: Mapping[str, Any]) -> None:
        """Main entry point for Slack interaction payloads."""
        try:
            interaction_type = payload.get("type")
            team = payload.get("team")
            if not team:
                self.log.error("Missing team in Slack interaction payload")
                return

            team_id = str(team.get("id"))

            self.log.info(
                "Handling Slack interaction type=%s team_id=%s",
                interaction_type,
                team_id,
            )

            # Resolve integration
            integration = (
                await self.integration_service.get_integration_by_slack_team_id(team_id)
            )
            if not integration:
                self.log.error("No integration found for Slack team_id=%s", team_id)
                return

            # Initialize ChannelService with this specific integration
            channel_service = ChannelService(
                corr_id=self.corr_id,
                integration_service=self.integration_service,
                slack_integration=integration,
            )

            interaction_type = str(payload.get("type", ""))

            # Dispatcher for main interaction types
            dispatch = {
                "block_actions": self._handle_block_actions,
                "view_submission": self._handle_view_submission,
            }

            handler = dispatch.get(interaction_type)
            if handler:
                await handler(payload, integration, channel_service)
            else:
                self.log.warning("No handler for interaction type=%s", interaction_type)

        except Exception as exc:
            self.log.error("Failed to handle Slack interaction: %s", exc, exc_info=True)

    async def _handle_block_actions(
        self,
        payload: Mapping[str, Any],
        integration: Any,
        channel_service: ChannelService,
    ) -> None:
        actions = payload.get("actions", [])
        if not actions:
            return

        action = actions[0]
        action_id = action.get("action_id")
        value = str(action.get("value", ""))
        channel_id = payload.get("channel", {}).get("id")

        self.log.info("Processing block_action action_id=%s value=%s", action_id, value)

        # Action Handler Dispatcher
        if action_id == "select_object_type":
            return await self._handle_select_object_type(
                payload, integration, channel_service
            )

        # Prefix-based routing
        prefixes = {
            "view_object": self._handle_view_object,
            "select_object": self._handle_view_object,
            "view_contact_company": self._handle_view_contact_company,
            "view_contact_deals": self._handle_view_contact_deals,
            "view_company_deals": self._handle_view_company_deals,
            "update_deal_stage": self._handle_update_deal_stage,
            "view_deals": self._handle_view_deals,
            "view_contacts": self._handle_view_contacts,
            "open_add_note_modal": self._handle_open_add_note_modal,
            "view_contact_meetings": self._handle_view_contact_meetings,
            "open_update_lead_type_modal": self._handle_open_update_lead_type_modal,
            "open_ai_recap_modal": self._handle_open_ai_recap_modal,
            "reassign_owner": self._handle_open_reassign_modal,
            "open_calculator": self._handle_open_calculator_modal,
            "schedule_meeting": self._handle_open_meeting_modal,
        }

        for prefix, handler in prefixes.items():
            if action_id.startswith(prefix):
                # Normalize arguments for unified handler signature
                kwargs = {
                    "value": value if prefix != "update_deal_stage" else action_id,
                    "integration": integration,
                    "channel_service": channel_service,
                    "channel_id": channel_id,
                    "response_url": payload.get("response_url"),  # Pass response_url
                }

                # Special cases for extra payload data
                if prefix == "update_deal_stage":
                    kwargs["payload"] = payload
                elif (
                    prefix.startswith("open")
                    or "modal" in prefix
                    or prefix.startswith("view")
                ):
                    kwargs["trigger_id"] = payload.get("trigger_id")
                    # Keep channel_id and response_url for metadata

                return await handler(**kwargs)

        self.log.warning("Unhandled action_id=%s", action_id)

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

        # 1. Try Pydantic/JSON parsing
        try:
            return ModalMetadata.model_validate_json(metadata)
        except Exception:
            pass

        # 2. Try raw JSON parsing (fallback for non-Pydantic JSON)
        try:
            raw = json.loads(metadata)
            return ModalMetadata(**raw)
        except Exception:
            pass

        # 3. Legacy colon-separated fallback
        parts = metadata.split(":")
        if len(parts) >= 2:  # noqa: PLR2004
            # Heuristic mapping for legacy formats:
            # post_mortem or next_step: deal_id:stage_id:channel_id:response_url
            # note: object_type:object_id
            if parts[0] in ("deal", "contact", "company", "task", "ticket"):
                return ModalMetadata(object_type=parts[0], object_id=parts[1])
            return ModalMetadata(deal_id=parts[0], stage_id=parts[1])

        # 4. Single value fallback (often just a deal_id)
        return ModalMetadata(deal_id=metadata)

    async def _handle_view_submission(  # noqa: PLR0911, PLR0912, PLR0915
        self,
        payload: Mapping[str, Any],
        integration: Any,
        channel_service: ChannelService,
    ) -> None:
        view = payload.get("view", {})
        callback_id = view.get("callback_id")

        if callback_id and callback_id.startswith(f"{CREATE_RECORD_CALLBACK_ID}:"):
            await self._handle_create_record_submission(
                payload, integration, channel_service
            )
            return

        if callback_id == "add_note_modal":
            metadata = self._parse_modal_metadata(view.get("private_metadata", ""))
            object_type = metadata.object_type
            object_id = metadata.object_id
            channel_id = metadata.channel_id
            response_url = metadata.response_url

            if not object_type or not object_id:
                self.log.warning("Missing object context in metadata")
                return

            values = view.get("state", {}).get("values", {})

            note_content = ""
            for block_id, actions in values.items():
                if "content" in actions:
                    note_content = actions["content"].get("value", "")
                    break

            if not note_content:
                self.log.warning("Empty note content submitted")
                return

            await self.hubspot.create_note(
                workspace_id=integration.workspace_id,
                content=note_content,
                associated_id=object_id,
                associated_type=object_type,
            )

            # Notify user
            user_id = str(payload.get("user", {}).get("id", ""))
            msg = "✅ Note successfully logged to HubSpot!"

            if response_url:
                await channel_service.send_via_response_url(
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

        if callback_id == "schedule_meeting_modal":
            await self._handle_schedule_meeting_submission(
                payload, integration, channel_service
            )
            return

        if callback_id == "update_lead_type_modal":
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
                self.log.warning(
                    "Missing deal_id in metadata for update_lead_type_modal"
                )
                return

            try:
                await self.hubspot.update_deal(
                    workspace_id=integration.workspace_id,
                    deal_id=deal_id,
                    properties={"hs_lead_type": lead_type},
                )
            except Exception as exc:
                if "PROPERTY_DOESNT_EXIST" in str(exc):
                    msg = (
                        "❌ Failed to update Lead Type: The property `hs_lead_type` "
                        "does not exist for Deals in your HubSpot portal."
                    )
                else:
                    msg = f"❌ Failed to update Lead Type: {str(exc)}"

                user_id = str(payload.get("user", {}).get("id", ""))
                if response_url:
                    await channel_service.send_via_response_url(
                        response_url=response_url, text=msg
                    )
                elif channel_id and user_id:
                    client = AsyncWebClient(
                        token=integration.credentials.get("slack_bot_token")
                    )
                    await client.chat_postEphemeral(
                        channel=str(channel_id), user=user_id, text=msg
                    )
                return

            # Notify user
            user_id = str(payload.get("user", {}).get("id", ""))
            msg = "✅ Lead Type updated for deal!"

            if response_url:
                await channel_service.send_via_response_url(
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

        if callback_id == "ai_recap_submission_modal":
            await self._handle_ai_recap_submission(
                payload, integration, channel_service
            )
            return

        if callback_id == "post_mortem_submission":
            metadata = self._parse_modal_metadata(view.get("private_metadata", ""))
            deal_id = metadata.deal_id
            stage_id = metadata.stage_id
            channel_id = metadata.channel_id
            response_url = metadata.response_url

            values = view.get("state", {}).get("values", {})
            properties = {"dealstage": stage_id}

            # Extract reasons
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
                self.log.warning("Missing deal_id for post_mortem_submission")
                return

            # Update stage and reasons
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
                self.log.warning("Missing deal_id for post_mortem_note")
            else:
                await self.hubspot.create_note(
                    workspace_id=integration.workspace_id,
                    content=note,
                    associated_id=deal_id,
                    associated_type="deal",
                )

            # Notify user
            user_id = str(payload.get("user", {}).get("id", ""))
            msg = f"✅ Post-mortem recorded and deal stage updated to {stage_id}!"
            if response_url:
                await channel_service.send_via_response_url(
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

        if callback_id == "calculator_submission":
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

            total = (qty * price) * (1 - (disc / 100))
            if not deal_id:
                self.log.warning(
                    "Missing deal_id in metadata for calculator_submission"
                )
                return

            await self.hubspot.update_deal(
                workspace_id=integration.workspace_id,
                deal_id=deal_id,
                properties={"amount": str(total)},
            )

            # Notify user
            user_id = str(payload.get("user", {}).get("id", ""))
            msg = f"✅ Calculated total `${total:,.2f}` saved to deal amount!"
            if response_url:
                await channel_service.send_via_response_url(
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

        if callback_id == "next_step_enforcement_submission":
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
                self.log.warning(
                    "Missing deal_id in metadata for next_step_enforcement"
                )
                return

            try:
                await self.hubspot.update_deal(
                    workspace_id=integration.workspace_id,
                    deal_id=deal_id,
                    properties={"dealstage": stage_id, "hs_next_step": next_step},
                )
            except Exception as exc:
                if "PROPERTY_DOESNT_EXIST" in str(exc) or "VALIDATION_ERROR" in str(
                    exc
                ):
                    # Fallback update without hs_next_step if it fails
                    self.log.warning(
                        "Property hs_next_step failed, falling back to dealstage "
                        "only update"
                    )
                    try:
                        await self.hubspot.update_deal(
                            workspace_id=integration.workspace_id,
                            deal_id=deal_id,
                            properties={"dealstage": stage_id},
                        )
                        msg = (
                            f"✅ Deal stage updated to {stage_id}, but Next Step "
                            "property could not be updated (property missing in "
                            "HubSpot)."
                        )
                    except Exception as fallback_exc:
                        msg = f"❌ Failed to update deal: {str(fallback_exc)}"
                else:
                    msg = f"❌ Failed to update deal: {str(exc)}"

                user_id = str(payload.get("user", {}).get("id", ""))
                if response_url:
                    await channel_service.send_via_response_url(
                        response_url=response_url, text=msg
                    )
                elif channel_id and user_id:
                    client = AsyncWebClient(
                        token=integration.credentials.get("slack_bot_token")
                    )
                    await client.chat_postEphemeral(
                        channel=str(channel_id), user=user_id, text=msg
                    )
                return

            # Notify user on success
            user_id = str(payload.get("user", {}).get("id", ""))
            msg = f"✅ Next step set and deal stage updated to {stage_id}!"
            if response_url:
                await channel_service.send_via_response_url(
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

        if callback_id == "reassign_owner_submission":
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
                    object_type, object_id = parts[0], parts[1]
                else:
                    object_type, object_id = "deal", parts[0]
                channel_id = None
                response_url = None

            values = view.get("state", {}).get("values", {})
            new_owner_id = ""
            for block in values.values():
                if "hubspot_owner_id" in block:
                    new_owner_id = (
                        block["hubspot_owner_id"]
                        .get("selected_option", {})
                        .get("value")
                    )
                    break

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

            # Notify user
            user_id = str(payload.get("user", {}).get("id", ""))
            msg = "✅ Owner successfully reassigned!"
            if response_url:
                await channel_service.send_via_response_url(
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

    async def _handle_view_object(
        self,
        *,
        value: str,
        integration: Any,
        channel_service: ChannelService,
        channel_id: str | None,
        **kwargs: Any,
    ) -> None:
        parts = value.split(":")
        if len(parts) < 3:  # noqa: PLR2004
            self.log.warning("Malformed interaction value=%s", value)
            return

        obj_type = parts[1]
        obj_id = parts[2]

        try:
            obj = await self.hubspot.get_object(
                workspace_id=integration.workspace_id,
                object_type=obj_type,
                object_id=obj_id,
            )
            if not obj:
                self.log.warning(
                    "Could not find HubSpot object type=%s id=%s", obj_type, obj_id
                )
                return

            analysis = await self.ai.analyze_polymorphic(obj, obj_type)

            await channel_service.send_card(
                workspace_id=integration.workspace_id,
                obj=obj,
                analysis=analysis,
                channel=channel_id,
                response_url=kwargs.get("response_url"),  # Pass response_url
            )
        except Exception as exc:
            self.log.error("Failed to view object: %s", exc)
            response_url = kwargs.get("response_url")
            if response_url:
                await channel_service.send_via_response_url(
                    response_url=response_url,
                    text=f"❌ Failed to fetch HubSpot object: {str(exc)}",
                )
            else:
                user_id = str(kwargs.get("payload", {}).get("user", {}).get("id", ""))
                if user_id:
                    client = AsyncWebClient(
                        token=integration.credentials.get("slack_bot_token")
                    )
                    await client.chat_postMessage(
                        channel=user_id,
                        text=f"❌ Failed to fetch HubSpot object: {str(exc)}",
                    )

    async def _handle_view_company_deals(
        self,
        *,
        value: str,
        integration: Any,
        channel_service: ChannelService,
        channel_id: str | None,
        **kwargs: Any,
    ) -> None:
        # value: view_company_deals:company_id
        parts = value.split(":")
        if len(parts) < 2:  # noqa: PLR2004
            self.log.warning("Malformed view_company_deals value=%s", value)
            return

        company_id = parts[1]
        trigger_id = kwargs.get("trigger_id")
        view_id = None

        if trigger_id:
            view_id = await self._show_loading(
                trigger_id, "Associated Deals", integration
            )

        try:
            deals = await self.hubspot.get_company_deals(
                workspace_id=integration.workspace_id,
                company_id=company_id,
            )

            cards = channel_service.cards
            if not deals:
                card = cards.build_empty("No deals found for this company.")
            else:
                card = cards.build_deals_list(deals)

            success = False
            if view_id:
                success = await self._update_modal(
                    view_id, card, "Associated Deals", integration
                )

            if not success:
                rendered = channel_service.slack_renderer.render(card)
                response_url = cast(str, kwargs.get("response_url"))
                if response_url:
                    await channel_service.send_via_response_url(
                        response_url=response_url,
                        text="Associated Deals",
                        blocks=rendered["blocks"],
                    )

        except Exception as exc:
            self.log.error("Failed to view company deals: %s", exc)
            response_url = cast(str, kwargs.get("response_url"))
            if response_url:
                await channel_service.send_via_response_url(
                    response_url=response_url,
                    text=f"❌ Failed to fetch associated deals: {str(exc)}",
                )
            else:
                user_id = str(kwargs.get("payload", {}).get("user", {}).get("id", ""))
                if user_id:
                    client = AsyncWebClient(
                        token=integration.credentials.get("slack_bot_token")
                    )
                    await client.chat_postMessage(
                        channel=user_id,
                        text=f"❌ Failed to fetch associated deals: {str(exc)}",
                    )

    async def _handle_view_deals(
        self,
        *,
        value: str,
        integration: Any,
        channel_service: ChannelService,
        channel_id: str | None,
        **kwargs: Any,
    ) -> None:
        # value: view_deals:contact_id
        parts = value.split(":")
        if len(parts) < 2:  # noqa: PLR2004
            self.log.warning("Malformed view_deals value=%s", value)
            return

        contact_id = parts[1]
        trigger_id = kwargs.get("trigger_id")
        view_id = None

        if trigger_id:
            view_id = await self._show_loading(
                trigger_id, "Associated Deals", integration
            )

        try:
            deals = await self.hubspot.get_contact_deals(
                workspace_id=integration.workspace_id,
                contact_id=contact_id,
            )

            cards = channel_service.cards
            if not deals:
                card = cards.build_empty("No deals found for this contact.")
            else:
                card = cards.build_deals_list(deals)

            success = False
            if view_id:
                success = await self._update_modal(
                    view_id, card, "Associated Deals", integration
                )

            if not success:
                rendered = channel_service.slack_renderer.render(card)
                response_url = cast(str, kwargs.get("response_url"))
                if response_url:
                    await channel_service.send_via_response_url(
                        response_url=response_url,
                        text="Associated Deals",
                        blocks=rendered["blocks"],
                    )

        except Exception as exc:
            self.log.error("Failed to view contact deals: %s", exc)
            response_url = cast(str, kwargs.get("response_url"))
            if response_url:
                await channel_service.send_via_response_url(
                    response_url=response_url,
                    text=f"❌ Failed to fetch associated deals: {str(exc)}",
                )
            else:
                user_id = str(kwargs.get("payload", {}).get("user", {}).get("id", ""))
                if user_id:
                    client = AsyncWebClient(
                        token=integration.credentials.get("slack_bot_token")
                    )
                    await client.chat_postMessage(
                        channel=user_id,
                        text=f"❌ Failed to fetch associated deals: {str(exc)}",
                    )

    async def _handle_view_contacts(
        self,
        *,
        value: str,
        integration: Any,
        channel_service: ChannelService,
        channel_id: str | None,
        **kwargs: Any,
    ) -> None:
        # value: view_contacts:company_id
        parts = value.split(":")
        if len(parts) < 2:  # noqa: PLR2004
            self.log.warning("Malformed view_contacts value=%s", value)
            return

        company_id = parts[1]
        trigger_id = kwargs.get("trigger_id")
        view_id = None

        if trigger_id:
            view_id = await self._show_loading(
                trigger_id, "Associated Contacts", integration
            )

        try:
            contacts = await self.hubspot.get_company_contacts(
                workspace_id=integration.workspace_id,
                company_id=company_id,
            )

            cards = channel_service.cards
            if not contacts:
                card = cards.build_empty("No contacts found for this company.")
            else:
                card = cards.build_contacts_list(contacts)

            success = False
            if view_id:
                success = await self._update_modal(
                    view_id, card, "Associated Contacts", integration
                )

            if not success:
                rendered = channel_service.slack_renderer.render(card)
                response_url = cast(str, kwargs.get("response_url"))
                if response_url:
                    await channel_service.send_via_response_url(
                        response_url=response_url,
                        text="Associated Contacts",
                        blocks=rendered["blocks"],
                    )
        except Exception as exc:
            self.log.error("Failed to view contacts: %s", exc)
            response_url = kwargs.get("response_url")
            if response_url:
                await channel_service.send_via_response_url(
                    response_url=response_url,
                    text=f"❌ Failed to fetch associated contacts: {str(exc)}",
                )
            else:
                user_id = str(kwargs.get("payload", {}).get("user", {}).get("id", ""))
                if user_id:
                    client = AsyncWebClient(
                        token=integration.credentials.get("slack_bot_token")
                    )
                    await client.chat_postMessage(
                        channel=user_id,
                        text=f"❌ Failed to fetch associated contacts: {str(exc)}",
                    )

    async def _handle_open_add_note_modal(
        self,
        value: str,
        integration: Any,
        channel_service: ChannelService,
        trigger_id: str | None,
        **kwargs: Any,
    ) -> None:
        # value: add_note:type:id
        parts = value.split(":")
        if len(parts) < 3:  # noqa: PLR2004
            self.log.warning("Malformed add_note value=%s", value)
            return

        obj_type = parts[1]
        object_id = parts[2]

        if not trigger_id:
            self.log.error("Missing trigger_id for modal")
            return

        try:
            # Build metadata
            channel_id = kwargs.get("channel_id")
            response_url = kwargs.get("response_url")
            metadata = json.dumps(
                {
                    "object_type": obj_type,
                    "object_id": object_id,
                    "channel_id": channel_id,
                    "response_url": response_url,
                }
            )

            # Build modal
            modal = channel_service.cards.build_note_modal(
                obj_type, object_id, metadata=metadata
            )

            # Open modal
            slack_channel = channel_service.integration_service.slack_channel
            await slack_channel.open_view(
                bot_token=integration.credentials["slack_bot_token"],
                trigger_id=trigger_id,
                view=modal,
            )
            self.log.info("Opened add_note modal for object_id=%s", object_id)
        except Exception as exc:
            self.log.error("Failed to open add note modal: %s", exc)
            response_url = kwargs.get("response_url")
            if response_url:
                await channel_service.send_via_response_url(
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
                    channel_id = kwargs.get("channel_id")
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

    async def _handle_open_update_lead_type_modal(
        self,
        value: str,
        integration: Any,
        channel_service: ChannelService,
        trigger_id: str | None,
        **kwargs: Any,
    ) -> None:
        # value: update_lead_type:deal_id
        parts = value.split(":")
        if len(parts) < 2:  # noqa: PLR2004
            self.log.warning("Malformed update_lead_type value=%s", value)
            return

        deal_id = parts[1]
        if not trigger_id:
            return

        view_id = await self._show_loading(trigger_id, "Loading...", integration)

        try:
            # Fetch deal to get current value
            deal = await self.hubspot.get_deal(
                workspace_id=integration.workspace_id,
                object_id=deal_id,
            )
            current_value = (
                (deal.get("properties") or {}).get("hs_lead_type", "") if deal else ""
            )

            modal = channel_service.cards.build_update_lead_type_modal(
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
        except Exception as exc:
            self.log.error("Failed to open lead type modal: %s", exc)

    async def _handle_view_contact_deals(
        self,
        *,
        value: str,
        integration: Any,
        channel_service: ChannelService,
        channel_id: str | None,
        **kwargs: Any,
    ) -> None:
        # value: view_contact_deals:contact_id
        parts = value.split(":")
        if len(parts) < 2:  # noqa: PLR2004
            self.log.warning("Malformed view_contact_deals value=%s", value)
            return

        try:
            contact_id = parts[1]
            trigger_id = kwargs.get("trigger_id")
            view_id = None
            if trigger_id:
                view_id = await self._show_loading(
                    trigger_id, "Associated Deals", integration
                )

            deals = await self.hubspot.get_contact_deals(
                workspace_id=integration.workspace_id,
                contact_id=contact_id,
            )

            cards = channel_service.cards
            if not deals:
                card = cards.build_empty("No deals found for this contact.")
            else:
                card = cards.build_deals_list(deals)

            success = False
            if view_id:
                success = await self._update_modal(
                    view_id, card, "Associated Deals", integration
                )

            if not success:
                rendered = channel_service.slack_renderer.render(card)
                response_url = cast(str, kwargs.get("response_url"))
                if response_url:
                    await channel_service.send_via_response_url(
                        response_url=response_url,
                        text="Contact's Deals",
                        blocks=rendered["blocks"],
                    )
        except Exception as exc:
            self.log.error("Failed to view contact deals: %s", exc)
            response_url = kwargs.get("response_url")
            if response_url:
                await channel_service.send_via_response_url(
                    response_url=response_url,
                    text=f"❌ Failed to fetch contact's deals: {str(exc)}",
                )
            else:
                user_id = str(kwargs.get("payload", {}).get("user", {}).get("id", ""))
                if user_id:
                    client = AsyncWebClient(
                        token=integration.credentials.get("slack_bot_token")
                    )
                    await client.chat_postMessage(
                        channel=user_id,
                        text=f"❌ Failed to fetch contact's deals: {str(exc)}",
                    )

    async def _handle_view_contact_company(  # noqa: PLR0912, PLR0915
        self,
        *,
        value: str,
        integration: Any,
        channel_service: ChannelService,
        channel_id: str | None,
        **kwargs: Any,
    ) -> None:
        # value: view_contact_company:contact_id
        parts = value.split(":")
        if len(parts) < 2:  # noqa: PLR2004
            self.log.warning("Malformed view_contact_company value=%s", value)
            return

        try:
            contact_id = parts[1]
            trigger_id = kwargs.get("trigger_id")
            view_id = None
            if trigger_id:
                view_id = await self._show_loading(
                    trigger_id, "Associated Companies", integration
                )

            companies = await self.hubspot.get_contact_companies(
                workspace_id=integration.workspace_id,
                contact_id=contact_id,
            )

            cards = channel_service.cards

            if not companies:
                card = cards.build_empty("No companies found for this contact.")
                success = False
                if view_id:
                    success = await self._update_modal(
                        view_id, card, "Associated Companies", integration
                    )
                if not success:
                    response_url = cast(str, kwargs.get("response_url"))
                    await channel_service.send_via_response_url(
                        response_url=response_url,
                        text="Contact's Company",
                        blocks=channel_service.slack_renderer.render(card)["blocks"],
                    )
                return

            if len(companies) == 1:
                company = companies[0]
                analysis = await self.ai.analyze_polymorphic(company, "company")
                from app.domains.ai.service import AICompanyAnalysis  # noqa: PLC0415

                card = channel_service.cards.build_company(
                    company, cast(AICompanyAnalysis, analysis), include_actions=False
                )
                success = False
                if view_id:
                    success = await self._update_modal(
                        view_id, card, "Associated Company", integration
                    )
                if not success:
                    await channel_service.send_card(
                        workspace_id=integration.workspace_id,
                        obj=company,
                        analysis=analysis,
                        channel=channel_id,
                        response_url=kwargs.get("response_url"),
                    )
                return
            else:
                card = cards.build_search_results(companies)

            success = False
            if view_id:
                success = await self._update_modal(
                    view_id, card, "Associated Companies", integration
                )
            if not success:
                rendered = channel_service.slack_renderer.render(card)
                response_url = cast(str, kwargs.get("response_url"))
                if response_url:
                    await channel_service.send_via_response_url(
                        response_url=response_url,
                        text="Contact's Company",
                        blocks=rendered["blocks"],
                    )
                else:
                    await channel_service.send_message(
                        workspace_id=integration.workspace_id,
                        text="Contact's Company",
                        blocks=rendered["blocks"],
                        channel=channel_id,
                    )
        except Exception as exc:
            self.log.error("Failed to view contact company: %s", exc)
            response_url = kwargs.get("response_url")
            if response_url:
                await channel_service.send_via_response_url(
                    response_url=response_url,
                    text=f"❌ Failed to fetch contact's company: {str(exc)}",
                )
            else:
                user_id = str(kwargs.get("payload", {}).get("user", {}).get("id", ""))
                if user_id:
                    client = AsyncWebClient(
                        token=integration.credentials.get("slack_bot_token")
                    )
                    await client.chat_postMessage(
                        channel=user_id,
                        text=f"❌ Failed to fetch contact's company: {str(exc)}",
                    )

    async def _handle_update_deal_stage(
        self,
        *,
        value: str,
        payload: Mapping[str, Any],
        integration: Any,
        channel_service: ChannelService,
        channel_id: str | None,
        **kwargs: Any,
    ) -> None:
        # value: update_deal_stage:deal_id
        parts = value.split(":")
        if len(parts) < 2:  # noqa: PLR2004
            self.log.warning("Malformed update_deal_stage value=%s", value)
            return

        deal_id = parts[1]

        # Extract selected option
        actions = payload.get("actions", [])
        if not actions:
            return

        selected_option = actions[0].get("selected_option")
        if not selected_option:
            return

        new_stage_id = selected_option.get("value")

        try:
            # 1. Pro check for Enforcement
            is_pro = await self.integration_service.is_pro_workspace(
                integration.workspace_id
            )

            if is_pro:
                # Fetch deal to check properties
                deal = await self.hubspot.get_deal(
                    workspace_id=integration.workspace_id,
                    object_id=deal_id,
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

                # A. Win/Loss Post-Mortem Enforcement
                if "won" in new_stage_id.lower() or "lost" in new_stage_id.lower():
                    modal = channel_service.cards.build_post_mortem_modal(
                        deal_id, new_stage_id, metadata=metadata
                    )
                    await channel_service.integration_service.slack_channel.open_view(
                        bot_token=integration.credentials["slack_bot_token"],
                        trigger_id=payload.get("trigger_id"),
                        view=modal,
                    )
                    return

                # B. Next Step Enforcement
                if not props.get("hs_next_step"):
                    modal = channel_service.cards.build_next_step_enforcement_modal(
                        deal_id, new_stage_id, metadata=metadata
                    )
                    await channel_service.integration_service.slack_channel.open_view(
                        bot_token=integration.credentials["slack_bot_token"],
                        trigger_id=payload.get("trigger_id"),
                        view=modal,
                    )
                    return

            # 2. Update HubSpot (Starter or no enforcement hit)
            await self.hubspot.update_deal(
                workspace_id=integration.workspace_id,
                deal_id=deal_id,
                properties={"dealstage": new_stage_id},
            )

            # 2. Re-fetch deal and pipelines to re-render card
            deal = await self.hubspot.get_deal(
                workspace_id=integration.workspace_id,
                object_id=deal_id,
            )
            pipelines = await self.hubspot.get_deal_pipelines(integration.workspace_id)

            if not deal:
                await channel_service.send_message(
                    workspace_id=integration.workspace_id,
                    channel=channel_id,
                    text="Error: Could not reload deal after update.",
                )
                return

            # 3. Analyze and Render
            analysis = await self.ai.analyze_polymorphic(deal, "deal")
            unified_card = channel_service.cards.build(
                deal, analysis, pipelines=pipelines, is_pro=is_pro
            )
            rendered = channel_service.slack_renderer.render(unified_card)

            # 4. Reply
            response_url = payload.get("response_url")

            if response_url:
                await channel_service.send_via_response_url(
                    response_url=response_url,
                    replace_original=True,
                    blocks=rendered["blocks"],
                    text=f"Deal stage updated to {new_stage_id}",
                )
            else:
                await channel_service.send_message(
                    workspace_id=integration.workspace_id,
                    channel=channel_id,
                    blocks=rendered["blocks"],
                    text="Deal stage updated.",
                )
        except Exception as exc:
            self.log.error("Failed to update deal stage: %s", exc)
            user_id = str(payload.get("user", {}).get("id", ""))
            if user_id:
                client = AsyncWebClient(
                    token=integration.credentials.get("slack_bot_token")
                )
                await client.chat_postMessage(
                    channel=user_id, text=f"❌ Failed to update deal stage: {str(exc)}"
                )

    async def _handle_select_object_type(
        self,
        payload: Mapping[str, Any],
        integration: Any,
        channel_service: ChannelService,
    ) -> None:
        """Handle selection of object type in creation modal."""
        actions = payload.get("actions", [])
        if not actions:
            return

        selected_option = actions[0].get("selected_option")
        if not selected_option:
            return

        object_type = selected_option.get("value")
        view_id = payload.get("view", {}).get("id")

        # Preserve context
        private_metadata = payload.get("view", {}).get("private_metadata", "{}")

        # Fetch HubSpot prerequisites
        hubspot_client = await self.hubspot.get_client(integration.workspace_id)

        pipelines = None
        owners = None

        # Load pipelines and owners based on type
        if object_type == "deal":
            pipelines = await hubspot_client.get_pipelines("deals")
            owners = await hubspot_client.get_owners()
        elif object_type == "ticket":
            pipelines = await hubspot_client.get_pipelines("tickets")
            owners = await hubspot_client.get_owners()
        elif object_type in ("task", "contact", "company"):
            # Owners might be useful for assignment
            owners = await hubspot_client.get_owners()

        # Build new modal
        modals = ModalBuilder()
        modal = modals.build_creation_modal(
            object_type=object_type,
            callback_id=CREATE_RECORD_CALLBACK_ID,
            pipelines=pipelines,
            owners=owners,
        )

        # Restore metadata
        if private_metadata:
            if isinstance(private_metadata, dict):
                modal["private_metadata"] = json.dumps(private_metadata)
            else:
                modal["private_metadata"] = str(private_metadata)

        # Update view
        client = AsyncWebClient(token=integration.credentials.get("slack_bot_token"))
        try:
            await client.views_update(view_id=view_id, view=modal)

        except Exception as exc:
            self.log.error("Failed to update creation modal: %s", exc)
            # Notify user of failure
            user_id = str(payload.get("user", {}).get("id", ""))
            if user_id:
                try:
                    await client.chat_postMessage(
                        channel=user_id,
                        text=f"❌ Failed to update the creation modal: {str(exc)}",
                    )
                except Exception:
                    pass

    async def _handle_create_record_submission(  # noqa: PLR0912, PLR0915
        self,
        payload: Mapping[str, Any],
        integration: Any,
        channel_service: ChannelService,
    ) -> None:
        """Process the generic record creation modal submission."""
        view = payload.get("view", {})
        callback_id = view.get("callback_id", "")
        # Format: create_hubspot_record:object_type
        parts = callback_id.split(":")
        if len(parts) < 2:  # noqa: PLR2004
            return

        object_type = parts[1]
        state_values = view.get("state", {}).get("values", {})

        # Flatten values
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

        if object_type == "task":
            # Map hs_task_due_date (YYYY-MM-DD) to hs_timestamp (milliseconds)
            if "hs_task_due_date" in properties:
                from datetime import UTC, datetime  # noqa: PLC0415

                from app.utils.transformers import to_hubspot_timestamp  # noqa: PLC0415

                date_str = properties.pop("hs_task_due_date")
                try:
                    # Slack datepicker returns YYYY-MM-DD
                    dt = datetime.strptime(date_str, "%Y-%m-%d").replace(tzinfo=UTC)
                    properties["hs_timestamp"] = str(to_hubspot_timestamp(dt))
                except ValueError:
                    self.log.error("Failed to parse hs_task_due_date: %s", date_str)

            if "hs_timestamp" not in properties:
                from datetime import UTC, datetime  # noqa: PLC0415

                from app.utils.transformers import to_hubspot_timestamp  # noqa: PLC0415

                properties["hs_timestamp"] = str(
                    to_hubspot_timestamp(datetime.now(UTC))
                )

        # Create Object
        hubspot_client = await self.hubspot.get_client(integration.workspace_id)

        try:
            result = await hubspot_client.create_object(object_type, properties)
            self.log.info("Created %s: %s", object_type, result.get("id"))

            # Notify user
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

            user_id = str(payload.get("user", {}).get("id", ""))
            msg = f"✅ Successfully created {object_type.capitalize()}!"

            if response_url:
                await channel_service.send_via_response_url(
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
            self.log.error("Failed to create object: %s", exc)
            user_id = str(payload.get("user", {}).get("id", ""))
            if user_id:
                client = AsyncWebClient(
                    token=integration.credentials.get("slack_bot_token")
                )
                await client.chat_postMessage(
                    channel=user_id,
                    text=f"❌ Failed to create {object_type}: {str(exc)}",
                )

    async def _handle_view_contact_meetings(  # noqa: PLR0912
        self,
        *,
        value: str,
        integration: Any,
        channel_service: ChannelService,
        channel_id: str | None,
        **kwargs: Any,
    ) -> None:
        """Fetch and display meetings associated with a contact."""
        # value: view_contact_meetings:contact_id
        parts = value.split(":")
        if len(parts) < 2:  # noqa: PLR2004
            self.log.warning("Malformed view_contact_meetings value=%s", value)
            return

        try:
            contact_id = parts[1]
            trigger_id = kwargs.get("trigger_id")
            view_id = None
            if trigger_id:
                view_id = await self._show_loading(
                    trigger_id, "Associated Meetings", integration
                )

            meetings = await self.hubspot.get_contact_meetings(
                workspace_id=integration.workspace_id,
                contact_id=contact_id,
            )

            cards = channel_service.cards
            if not meetings:
                card = cards.build_empty("No meetings found for this contact.")
            else:
                from app.utils.transformers import to_datetime  # noqa: PLC0415

                # Sort by start time descending
                meetings.sort(
                    key=lambda x: to_datetime(
                        x.get("properties", {}).get("hs_meeting_start_time")
                    ),
                    reverse=True,
                )
                card = cards.build_meetings_list(meetings)

            if view_id:
                await self._update_modal(
                    view_id, card, "Associated Meetings", integration
                )
            elif trigger_id:
                await self._open_modal(
                    trigger_id=trigger_id,
                    view_or_card=card,
                    title="Associated Meetings",
                    integration=integration,
                )
            else:
                rendered = channel_service.slack_renderer.render(card)
                response_url = cast(str, kwargs.get("response_url"))
                await channel_service.send_via_response_url(
                    response_url=response_url,
                    text="Contact's Meetings",
                    blocks=rendered["blocks"],
                )
        except Exception as exc:
            self.log.error("Failed to view contact meetings: %s", exc)
            response_url = kwargs.get("response_url")
            if response_url:
                await channel_service.send_via_response_url(
                    response_url=response_url,
                    text=f"❌ Failed to fetch contact's meetings: {str(exc)}",
                )
            else:
                user_id = str(kwargs.get("payload", {}).get("user", {}).get("id", ""))
                if user_id:
                    client = AsyncWebClient(
                        token=integration.credentials.get("slack_bot_token")
                    )
                    if channel_id:
                        await client.chat_postEphemeral(
                            channel=channel_id,
                            user=user_id,
                            text=f"❌ Failed to fetch contact's meetings: {str(exc)}",
                        )
                    else:
                        try:
                            await client.chat_postMessage(
                                channel=user_id,
                                text=(
                                    f"❌ Failed to fetch contact's meetings: {str(exc)}"
                                ),
                            )
                        except Exception:
                            pass

    async def _handle_schedule_meeting_submission(  # noqa: PLR0912, PLR0915
        self,
        payload: Mapping[str, Any],
        integration: Any,
        channel_service: ChannelService,
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

        # Extract values
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

        if not title or not date_str or not time_str:
            self.log.warning("Incomplete meeting data submitted")
            return

        # Combine date and time
        from datetime import datetime  # noqa: PLC0415

        try:
            dt = datetime.strptime(f"{date_str} {time_str}", "%Y-%m-%d %H:%M")
            int(dt.timestamp() * 1000)
            # end_time_ms = start_time_ms + (30 * 60 * 1000)
        except Exception as exc:
            self.log.error("Failed to parse meeting date/time: %s", exc)
            return

        from datetime import datetime, timedelta  # noqa: PLC0415

        from app.utils.transformers import to_hubspot_iso8601  # noqa: PLC0415

        # Use naive dt as base if we assume local, or UTC if we want to be safe.
        # Given the Slack picker, we'll assume the string is the wall time.
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
            self.log.info("Meeting successfully created meeting_id=%s", meeting_id)

            # Notify user
            user_id = str(payload.get("user", {}).get("id", ""))
            if user_id:
                msg = f"✅ *Meeting Scheduled!* \n_{title}_ at `{date_str} {time_str}`"

                if response_url:
                    await channel_service.send_via_response_url(
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
            self.log.error("Failed to create meeting: %s", exc)
            user_id = str(payload.get("user", {}).get("id", ""))
            if user_id:
                error_msg = f"❌ Failed to schedule meeting: {str(exc)}"
                if response_url:
                    await channel_service.send_via_response_url(
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

    async def _handle_open_reassign_modal(
        self,
        value: str,
        integration: Any,
        channel_service: ChannelService,
        trigger_id: str | None,
        **kwargs: Any,
    ) -> None:
        """Fetch owners and open reassign modal."""
        # value: reassign_owner:type:id
        parts = value.split(":")
        if len(parts) < 2:  # noqa: PLR2004
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

            channel_id = kwargs.get("channel_id")
            response_url = kwargs.get("response_url")
            metadata = json.dumps(
                {
                    "object_type": obj_type,
                    "object_id": object_id,
                    "channel_id": channel_id,
                    "response_url": response_url,
                }
            )

            modal = channel_service.cards.build_reassign_modal(
                f"{obj_type}:{object_id}", owners, metadata=metadata
            )

            if view_id:
                await self._update_modal(view_id, modal, "Reassign Owner", integration)
            else:
                await self._open_modal(trigger_id, modal, "Reassign Owner", integration)
        except Exception as exc:
            self.log.error("Failed to open reassign modal: %s", exc)
            response_url = kwargs.get("response_url")
            if response_url:
                await channel_service.send_via_response_url(
                    response_url=response_url,
                    text=f"❌ Failed to open reassign modal: {str(exc)}",
                )

    async def _handle_open_calculator_modal(
        self,
        value: str,
        integration: Any,
        channel_service: ChannelService,
        trigger_id: str | None,
        **kwargs: Any,
    ) -> None:
        """Fetch deal and open calculator modal."""
        # value: open_calculator:deal_id
        parts = value.split(":")
        if len(parts) < 2:  # noqa: PLR2004
            return

        deal_id = parts[1]
        if not trigger_id:
            return

        view_id = await self._show_loading(
            trigger_id, "Fetching Deal Details...", integration
        )

        try:
            deal = await self.hubspot.get_deal(
                workspace_id=integration.workspace_id,
                object_id=deal_id,
            )
            if not deal:
                self.log.warning("Deal not found for id=%s", deal_id)
                return

            props = deal.get("properties") or {}
            amount_str = props.get("amount", "0")
            amount = float(amount_str) if amount_str else 0.0

            channel_id = kwargs.get("channel_id")
            response_url = kwargs.get("response_url")
            metadata = json.dumps(
                {
                    "deal_id": deal_id,
                    "channel_id": channel_id,
                    "response_url": response_url,
                }
            )

            modal = channel_service.cards.build_pricing_calculator_modal(
                deal_id, amount, metadata=metadata
            )

            if view_id:
                await self._update_modal(view_id, modal, "Deal Calculator", integration)
            else:
                await self._open_modal(
                    trigger_id, modal, "Deal Calculator", integration
                )

        except Exception as exc:
            self.log.error("Failed to open calculator modal: %s", exc)
            response_url = kwargs.get("response_url")
            if response_url:
                await channel_service.send_via_response_url(
                    response_url=response_url,
                    text=f"❌ Failed to open calculator modal: {str(exc)}",
                )

    async def _handle_open_meeting_modal(
        self,
        value: str,
        integration: Any,
        channel_service: ChannelService,
        trigger_id: str | None,
        **kwargs: Any,
    ) -> None:
        """Open meeting modal for contact."""
        parts = value.split(":")
        if len(parts) < 2:  # noqa: PLR2004
            return

        contact_id = parts[1]
        if not trigger_id:
            return

        view_id = await self._show_loading(trigger_id, "Loading...", integration)

        try:
            channel_id = kwargs.get("channel_id")
            response_url = kwargs.get("response_url")
            metadata = json.dumps(
                {
                    "contact_id": contact_id,
                    "channel_id": channel_id,
                    "response_url": response_url,
                }
            )
            modal = channel_service.cards.build_meeting_modal(
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
            self.log.error("Failed to open meeting modal: %s", exc)
            response_url = kwargs.get("response_url")
            if response_url:
                await channel_service.send_via_response_url(
                    response_url=response_url,
                    text=f"❌ Failed to open meeting modal: {str(exc)}",
                )

    async def _handle_open_ai_recap_modal(
        self,
        value: str,
        integration: Any,
        channel_service: ChannelService,
        trigger_id: str | None,
        **kwargs: Any,
    ) -> None:
        """Fetch thread, summarize, and show review modal."""
        # value: ai_recap:type:id
        parts = value.split(":")
        if len(parts) < 3:  # noqa: PLR2004
            return

        obj_type = parts[1]
        obj_id = parts[2]

        if not trigger_id:
            return

        view_id = await self._show_loading(
            trigger_id, "Summarizing Thread...", integration
        )

        try:
            # 1. Resolve thread from mapping
            workspace_id = integration.workspace_id
            slack_channel = channel_service.integration_service.slack_channel

            # We need the thread_ts for this object
            storage = self.integration_service.storage
            mapping = await storage.thread_mappings.fetch_single(
                {"workspace_id": workspace_id, "object_id": obj_id}
            )

            if not mapping:
                # Inform user no thread found
                response_url = kwargs.get("response_url")
                if response_url:
                    await channel_service.send_via_response_url(
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

            # 2. Fetch replies
            replies = await slack_channel.get_thread_replies(
                bot_token=integration.credentials["slack_bot_token"],
                channel_id=mapping.channel_id,
                thread_ts=mapping.thread_ts,
            )

            # 3. Summarize
            summary = await self.ai.summarize_thread(replies)

            # 4. Show modal
            channel_id = kwargs.get("channel_id")
            response_url = kwargs.get("response_url")
            metadata = json.dumps(
                {
                    "object_type": obj_type,
                    "object_id": obj_id,
                    "channel_id": channel_id,
                    "response_url": response_url,
                }
            )

            modal = channel_service.cards.build_ai_recap_modal(
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
            self.log.error("Failed to open AI Recap modal: %s", exc)
            response_url = kwargs.get("response_url")
            if response_url:
                await channel_service.send_via_response_url(
                    response_url=response_url,
                    text=f"❌ Failed to open AI Recap modal: {str(exc)}",
                )

    async def _open_modal(
        self,
        trigger_id: str | None,
        view_or_card: dict[str, Any] | UnifiedCard,
        title: str,
        integration: Any,
    ) -> str | None:
        """Helper to render a UnifiedCard or use a raw View and open it as a
        Slack modal.

        # noqa: E501
        """
        if not trigger_id:
            self.log.error("Missing trigger_id for opening modal: %s", title)
            return None

        bot_token = integration.credentials.get("slack_bot_token")
        if not bot_token:
            self.log.error("Missing bot token for opening modal")
            return None

        try:
            from app.connectors.slack.ui import CardBuilder  # noqa: PLC0415

            if isinstance(view_or_card, dict):
                modal = view_or_card
            else:
                builder = CardBuilder()
                modal = builder.build_card_modal(view_or_card, title=title)

            resp = await self.integration_service.slack_channel.open_view(
                bot_token=bot_token,
                trigger_id=trigger_id,
                view=modal,
            )
            if not resp or not resp.get("ok"):
                self.log.error(
                    "Failed to open modal '%s': %s",
                    title,
                    resp.get("error") if resp else "No response",
                )
                return None

            view = resp.get("view")
            if not view or not isinstance(view, dict):
                return None

            self.log.info("Modal '%s' opened for trigger_id=%s", title, trigger_id[:8])
            return str(view.get("id"))
        except Exception as exc:
            self.log.error("Failed to open modal '%s': %s", title, exc, exc_info=True)
            return None

    async def _show_loading(
        self, trigger_id: str, title: str, integration: Any
    ) -> str | None:
        """Opens a loading modal immediately to secure the trigger_id window."""
        bot_token = integration.credentials.get("slack_bot_token")
        if not bot_token:
            return None

        try:
            from app.connectors.slack.ui import CardBuilder  # noqa: PLC0415

            builder = CardBuilder()
            modal = builder.build_loading_modal(title=title)

            resp = await self.integration_service.slack_channel.open_view(
                bot_token=bot_token,
                trigger_id=trigger_id,
                view=modal,
            )
            if not resp or not resp.get("ok"):
                self.log.error(
                    "Failed to show loading modal: %s",
                    resp.get("error") if resp else "No response",
                )
                return None

            view = resp.get("view")
            if not view or not isinstance(view, dict):
                return None

            return str(view.get("id"))
        except Exception as exc:
            self.log.error("Failed to show loading modal: %s", exc)
            return None

    async def _update_modal(
        self,
        view_id: str,
        view_or_card: dict[str, Any] | UnifiedCard,
        title: str,
        integration: Any,
    ) -> bool:
        """Updates an existing Slack modal with final content."""
        bot_token = integration.credentials.get("slack_bot_token")
        if not bot_token:
            return False

        try:
            from app.connectors.slack.ui import CardBuilder  # noqa: PLC0415

            if isinstance(view_or_card, dict):
                modal = view_or_card
            else:
                builder = CardBuilder()
                modal = builder.build_card_modal(view_or_card, title=title)

            client = AsyncWebClient(token=bot_token)
            await client.views_update(view_id=view_id, view=modal)
            self.log.info("Modal updated for view_id=%s", view_id[:8])
            return True
        except Exception as exc:
            self.log.error("Failed to update modal '%s': %s", title, exc)
            return False

    async def _handle_ai_recap_submission(
        self,
        payload: Mapping[str, Any],
        integration: Any,
        channel_service: ChannelService,
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

        # Extract summary from blocks
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
            self.log.info("AI Recap saved as note for %s %s", obj_type, obj_id)

            # Notify user
            user_id = str(payload.get("user", {}).get("id", ""))
            msg = f"✅ AI Recap saved to HubSpot as a note for {obj_type} {obj_id}!"

            if response_url:
                await channel_service.send_via_response_url(
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
            self.log.error("Failed to save AI Recap: %s", exc)
            user_id = str(payload.get("user", {}).get("id", ""))
            if user_id:
                error_msg = f"❌ Failed to save AI Recap: {str(exc)}"
                if response_url:
                    await channel_service.send_via_response_url(
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
