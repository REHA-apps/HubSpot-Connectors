from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from slack_sdk.web.async_client import AsyncWebClient

from app.connectors.slack.ui import ModalBuilder
from app.core.logging import CorrelationAdapter, get_logger
from app.domains.ai.service import AIService
from app.domains.crm.channel_service import ChannelService
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
            "update_deal_stage": self._handle_update_deal_stage,
            "view_deals": self._handle_view_deals,
            "view_contacts": self._handle_view_contacts,
            "open_add_note_modal": self._handle_open_add_note_modal,
            "view_contact_meetings": self._handle_view_contact_meetings,
        }

        for prefix, handler in prefixes.items():
            if action_id.startswith(prefix):
                # Normalize arguments for unified handler signature
                # Note: update_deal_stage requires action_value vs value
                kwargs = {
                    "value": value if prefix != "update_deal_stage" else action_id,
                    "integration": integration,
                    "channel_service": channel_service,
                    "channel_id": channel_id,
                }

                # Special cases for extra payload data
                if prefix == "update_deal_stage":
                    kwargs["payload"] = payload
                elif prefix == "open_add_note_modal":
                    kwargs["trigger_id"] = payload.get("trigger_id")
                    del kwargs["channel_id"]

                return await handler(**kwargs)

        self.log.warning("Unhandled action_id=%s", action_id)

    async def _handle_view_submission(
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
            metadata = str(view.get("private_metadata", ""))
            # metadata: type:id
            m_parts = metadata.split(":")
            if len(m_parts) < 2:  # noqa: PLR2004
                self.log.warning("Malformed private_metadata=%s", metadata)
                return

            object_type = m_parts[0]
            object_id = m_parts[1]

            values = view.get("state", {}).get("values", {})

            note_content = ""
            for block_id, actions in values.items():
                if "content" in actions:
                    note_content = actions["content"].get("value", "")
                    break

            if not note_content:
                self.log.warning("Empty note content submitted")
                return

            self.log.info("Submitting %s note for object_id=%s", object_type, object_id)

            result = await self.hubspot.create_note(
                workspace_id=integration.workspace_id,
                content=note_content,
                associated_id=object_id,
                associated_type=object_type,
            )

            note_id = result.get("id", "unknown") if result else "no_response"
            self.log.info(
                "Note successfully logged to HubSpot note_id=%s "
                "associated_type=%s associated_id=%s",
                note_id,
                object_type,
                object_id,
            )
            return

        if callback_id == "schedule_meeting_modal":
            await self._handle_schedule_meeting_submission(
                payload, integration, channel_service
            )

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
            )
        except Exception as exc:
            self.log.error("Failed to view object: %s", exc)
            user_id = str(kwargs.get("payload", {}).get("user", {}).get("id", ""))
            if user_id:
                client = AsyncWebClient(
                    token=integration.credentials.get("slack_bot_token")
                )
                await client.chat_postMessage(
                    channel=user_id,
                    text=f"❌ Failed to fetch HubSpot object: {str(exc)}",
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
        # value: view_deals:company_id
        parts = value.split(":")
        if len(parts) < 2:  # noqa: PLR2004
            self.log.warning("Malformed view_deals value=%s", value)
            return

        company_id = parts[1]
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

            rendered = channel_service.slack_renderer.render(card)

            await channel_service.send_message(
                workspace_id=integration.workspace_id,
                text="Associated Deals",
                blocks=rendered["blocks"],
                channel=channel_id,
            )
        except Exception as exc:
            self.log.error("Failed to view deals: %s", exc)
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

            rendered = channel_service.slack_renderer.render(card)

            await channel_service.send_message(
                workspace_id=integration.workspace_id,
                text="Associated Contacts",
                blocks=rendered["blocks"],
                channel=channel_id,
            )
        except Exception as exc:
            self.log.error("Failed to view contacts: %s", exc)
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
            # Build modal
            modal = channel_service.cards.build_note_modal(obj_type, object_id)

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
            user_id = str(kwargs.get("payload", {}).get("user", {}).get("id", ""))
            if user_id:
                client = AsyncWebClient(
                    token=integration.credentials.get("slack_bot_token")
                )
                await client.chat_postMessage(
                    channel=user_id, text=f"❌ Failed to open note modal: {str(exc)}"
                )

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
            deals = await self.hubspot.get_contact_deals(
                workspace_id=integration.workspace_id,
                contact_id=contact_id,
            )

            cards = channel_service.cards
            if not deals:
                card = cards.build_empty("No deals found for this contact.")
            else:
                card = cards.build_deals_list(deals)

            rendered = channel_service.slack_renderer.render(card)

            await channel_service.send_message(
                workspace_id=integration.workspace_id,
                text="Contact's Deals",
                blocks=rendered["blocks"],
                channel=channel_id,
            )
        except Exception as exc:
            self.log.error("Failed to view contact deals: %s", exc)
            user_id = str(kwargs.get("payload", {}).get("user", {}).get("id", ""))
            if user_id:
                client = AsyncWebClient(
                    token=integration.credentials.get("slack_bot_token")
                )
                await client.chat_postMessage(
                    channel=user_id,
                    text=f"❌ Failed to fetch contact's deals: {str(exc)}",
                )

    async def _handle_view_contact_company(
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
            companies = await self.hubspot.get_contact_companies(
                workspace_id=integration.workspace_id,
                contact_id=contact_id,
            )

            cards = channel_service.cards
            if not companies:
                card = cards.build_empty("No company found for this contact.")
            elif len(companies) == 1:
                # Single company — show detail card with AI analysis
                company = companies[0]
                analysis = await self.ai.analyze_polymorphic(company, "company")
                await channel_service.send_card(
                    workspace_id=integration.workspace_id,
                    obj=company,
                    analysis=analysis,
                    channel=channel_id,
                )
                return
            else:
                card = cards.build_search_results(companies)

            rendered = channel_service.slack_renderer.render(card)

            await channel_service.send_message(
                workspace_id=integration.workspace_id,
                text="Contact's Company",
                blocks=rendered["blocks"],
                channel=channel_id,
            )
        except Exception as exc:
            self.log.error("Failed to view contact company: %s", exc)
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
            # 1. Update HubSpot
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
                deal, analysis, pipelines=pipelines
            )
            rendered = channel_service.slack_renderer.render(unified_card)

            # 4. Reply
            response_url = payload.get("response_url")

            if response_url:
                import httpx  # noqa: PLC0415

                async with httpx.AsyncClient() as client:
                    await client.post(
                        response_url,
                        json={
                            "replace_original": "true",
                            "blocks": rendered["blocks"],
                            "text": f"Deal stage updated to {new_stage_id}",
                        },
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
            modal["private_metadata"] = private_metadata

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

    async def _handle_create_record_submission(  # noqa: PLR0912
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

        # Create Object
        hubspot_client = await self.hubspot.get_client(integration.workspace_id)

        try:
            result = await hubspot_client.create_object(object_type, properties)
            self.log.info("Created %s: %s", object_type, result.get("id"))

            # Notify user
            metadata = view.get("private_metadata")
            channel_id = None
            if metadata:
                try:
                    meta = json.loads(metadata)
                    channel_id = meta.get("channel_id")
                except Exception:
                    pass

            user_id = str(payload.get("user", {}).get("id", ""))
            msg = f"✅ Successfully created {object_type.capitalize()}!"

            client = AsyncWebClient(
                token=integration.credentials.get("slack_bot_token")
            )
            if channel_id and user_id:
                await client.chat_postEphemeral(
                    channel=str(channel_id), user=user_id, text=msg
                )
            elif user_id:
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

    async def _handle_view_contact_meetings(
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
            meetings = await self.hubspot.get_contact_meetings(
                workspace_id=integration.workspace_id,
                contact_id=contact_id,
            )

            cards = channel_service.cards
            if not meetings:
                card = cards.build_empty("No meetings found for this contact.")
            else:
                # Sort by start time descending
                meetings.sort(
                    key=lambda x: int(
                        x.get("properties", {}).get("hs_meeting_start_time") or 0
                    ),
                    reverse=True,
                )
                card = cards.build_meetings_list(meetings)

            rendered = channel_service.slack_renderer.render(card)

            await channel_service.send_message(
                workspace_id=integration.workspace_id,
                text="Contact's Meetings",
                blocks=rendered["blocks"],
                channel=channel_id,
            )
        except Exception as exc:
            self.log.error("Failed to view contact meetings: %s", exc)
            user_id = str(kwargs.get("payload", {}).get("user", {}).get("id", ""))
            if user_id:
                client = AsyncWebClient(
                    token=integration.credentials.get("slack_bot_token")
                )
                await client.chat_postMessage(
                    channel=user_id,
                    text=f"❌ Failed to fetch contact's meetings: {str(exc)}",
                )

    async def _handle_schedule_meeting_submission(
        self,
        payload: Mapping[str, Any],
        integration: Any,
        channel_service: ChannelService,
    ) -> None:
        """Process the schedule meeting modal submission."""
        view = payload.get("view", {})
        contact_id = view.get("private_metadata")
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
            start_time_ms = int(dt.timestamp() * 1000)
            end_time_ms = start_time_ms + (30 * 60 * 1000)
        except Exception as exc:
            self.log.error("Failed to parse meeting date/time: %s", exc)
            return

        properties = {
            "hs_meeting_title": title,
            "hs_meeting_body": body or "Scheduled via Slack",
            "hs_meeting_start_time": f"{start_time_ms}",
            "hs_meeting_end_time": f"{end_time_ms}",
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
                client = AsyncWebClient(
                    token=integration.credentials.get("slack_bot_token")
                )
                msg = f"✅ *Meeting Scheduled!* \n_{title}_ at `{date_str} {time_str}`"
                await client.chat_postMessage(channel=user_id, text=msg)

        except Exception as exc:
            self.log.error("Failed to create meeting: %s", exc)
            user_id = str(payload.get("user", {}).get("id", ""))
            if user_id:
                client = AsyncWebClient(
                    token=integration.credentials.get("slack_bot_token")
                )
                await client.chat_postMessage(
                    channel=user_id, text=f"❌ Failed to schedule meeting: {str(exc)}"
                )
