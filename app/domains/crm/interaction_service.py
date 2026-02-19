from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.core.logging import CorrelationAdapter, get_logger
from app.domains.ai.service import AIService
from app.domains.crm.channel_service import ChannelService
from app.domains.crm.hubspot.service import HubSpotService
from app.domains.crm.integration_service import IntegrationService

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

            if interaction_type == "block_actions":
                await self._handle_block_actions(payload, integration, channel_service)
            elif interaction_type == "view_submission":
                await self._handle_view_submission(
                    payload, integration, channel_service
                )

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

        if action_id in ["view_object", "select_object"]:
            await self._handle_view_object(
                value, integration, channel_service, channel_id
            )

        elif action_id == "view_deals":
            await self._handle_view_deals(
                value, integration, channel_service, channel_id
            )

        elif action_id == "view_contacts":
            await self._handle_view_contacts(
                value, integration, channel_service, channel_id
            )

        elif action_id == "open_add_note_modal":
            trigger_id = payload.get("trigger_id")
            await self._handle_open_add_note_modal(
                value, integration, channel_service, trigger_id
            )

    async def _handle_view_submission(
        self,
        payload: Mapping[str, Any],
        integration: Any,
        channel_service: ChannelService,
    ) -> None:
        view = payload.get("view", {})
        callback_id = view.get("callback_id")

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

    async def _handle_view_object(
        self,
        value: str,
        integration: Any,
        channel_service: ChannelService,
        channel_id: str | None,
    ) -> None:
        parts = value.split(":")
        if len(parts) < 3:  # noqa: PLR2004
            self.log.warning("Malformed interaction value=%s", value)
            return

        obj_type = parts[1]
        obj_id = parts[2]

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

        await channel_service.send_slack_card(
            workspace_id=integration.workspace_id,
            obj=obj,
            analysis=analysis,
            channel=channel_id,
        )

    async def _handle_view_deals(
        self,
        value: str,
        integration: Any,
        channel_service: ChannelService,
        channel_id: str | None,
    ) -> None:
        # value: view_deals:company_id
        parts = value.split(":")
        if len(parts) < 2:  # noqa: PLR2004
            self.log.warning("Malformed view_deals value=%s", value)
            return

        company_id = parts[1]
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

        await channel_service.send_slack_message(
            workspace_id=integration.workspace_id,
            text="Associated Deals",
            blocks=rendered["blocks"],
            channel=channel_id,
        )

    async def _handle_view_contacts(
        self,
        value: str,
        integration: Any,
        channel_service: ChannelService,
        channel_id: str | None,
    ) -> None:
        # value: view_contacts:company_id
        parts = value.split(":")
        if len(parts) < 2:  # noqa: PLR2004
            self.log.warning("Malformed view_contacts value=%s", value)
            return

        company_id = parts[1]
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

        await channel_service.send_slack_message(
            workspace_id=integration.workspace_id,
            text="Associated Contacts",
            blocks=rendered["blocks"],
            channel=channel_id,
        )

    async def _handle_open_add_note_modal(
        self,
        value: str,
        integration: Any,
        channel_service: ChannelService,
        trigger_id: str | None,
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
