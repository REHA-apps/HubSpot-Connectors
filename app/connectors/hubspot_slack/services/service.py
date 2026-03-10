from __future__ import annotations

import json
from collections.abc import Mapping
from typing import Any

from fastapi.responses import Response

from app.connectors.hubspot_slack.services.handlers.registry import InteractionRegistry
from app.connectors.hubspot_slack.ui import ModalBuilder
from app.core.logging import get_logger
from app.db.records import IntegrationRecord
from app.domains.ai.service import AIService
from app.domains.crm.hubspot.service import HubSpotService
from app.domains.crm.integration_service import IntegrationService
from app.domains.crm.ui.card_builder import CardBuilder
from app.domains.messaging.slack.service import SlackMessagingService
from app.utils.constants import CREATE_RECORD_CALLBACK_ID

logger = get_logger("interaction.service")


class InteractionService:
    """Refactored InteractionService that delegates to specific handlers."""

    def __init__(
        self,
        hubspot: HubSpotService,
        ai: AIService,
        integration_service: IntegrationService,
    ):
        self.hubspot = hubspot
        self.ai = ai
        self.integration_service = integration_service

    async def handle_interaction(
        self,
        payload: Mapping[str, Any],
        integration: IntegrationRecord,
        messaging_service: SlackMessagingService,
        corr_id: str,
    ) -> Any:
        """Main entry point for Slack interactions."""
        registry = InteractionRegistry(
            corr_id=corr_id,
            hubspot=self.hubspot,
            ai=self.ai,
            integration_service=self.integration_service,
        )

        interaction_type = str(payload.get("type", ""))

        # Determine unique routing keys
        action_id = None
        actions = payload.get("actions", [])
        if actions:
            action_id = str(actions[0].get("action_id", ""))
        elif interaction_type == "view_submission":
            action_id = str(payload.get("view", {}).get("callback_id", ""))

        handler = registry.get_handler(payload, action_id=action_id)

        if not handler:
            logger.warning(
                "No handler found for interaction: %s (action_id=%s)",
                interaction_type,
                action_id,
            )
            return None

        # Prepare kwargs for the handler
        kwargs: dict[str, Any] = {
            "action_id": action_id,
            "corr_id": corr_id,
        }

        if actions:
            kwargs["value"] = str(
                actions[0].get("value")
                or (actions[0].get("selected_option") or {}).get("value")
                or ""
            )
            kwargs["trigger_id"] = str(payload.get("trigger_id", ""))
            kwargs["response_url"] = str(payload.get("response_url", ""))
            kwargs["channel_id"] = str(payload.get("channel", {}).get("id", ""))

        return await handler.handle(
            payload=payload,
            integration=integration,
            messaging_service=messaging_service,
            **kwargs,
        )

    async def handle_suggestion(
        self,
        payload: Mapping[str, Any],
        integration: IntegrationRecord,
        messaging_service: SlackMessagingService,
        corr_id: str,
    ) -> dict[str, Any]:
        """Handles real-time search suggestions via SuggestionHandler."""
        from app.connectors.hubspot_slack.services.handlers.object_handlers import (
            SuggestionHandler,
        )

        handler = SuggestionHandler(
            corr_id=corr_id,
            hubspot=self.hubspot,
            ai=self.ai,
            integration_service=self.integration_service,
        )

        return await handler.handle(
            payload=payload,
            integration=integration,
            messaging_service=messaging_service,
        )

    async def handle_fast_path_block_actions(
        self,
        payload: dict,
        corr_id: str,
    ) -> Response | None:
        """Fast-path for modal opens within the 3s window."""
        actions = payload.get("actions", [])
        action_id = str(actions[0].get("action_id", "")) if actions else ""

        if not action_id.startswith(
            ("open_add_note_modal", "open_schedule_meeting_modal")
        ):
            return None

        trigger_id = payload.get("trigger_id")
        value = str(actions[0].get("value", ""))
        parts = value.split(":")

        if not (trigger_id and len(parts) >= 2):  # noqa: PLR2004
            return None

        # Resolve integration & token
        team_id = str(payload.get("team", {}).get("id", ""))
        integration = await self.integration_service.get_integration_by_slack_team_id(
            team_id
        )
        if not integration:
            return None

        bot_token = integration.credentials.get("slack_bot_token")
        if not bot_token:
            return None

        # Tier check for Pro actions
        is_pro = await self.integration_service.is_pro_workspace(
            integration.workspace_id
        )
        if not is_pro:
            # Prompt to upgrade via ephemeral message instead of modal
            response_url = payload.get("response_url")
            if response_url:
                try:
                    from app.connectors.hubspot_slack.slack_channel import SlackChannel

                    slack_channel = SlackChannel(corr_id=corr_id, bot_token=bot_token)
                    await slack_channel.send_via_response_url(
                        response_url=response_url,
                        text=(
                            "Update fields, indexing notes, and scheduling "
                            "meetings are Professional features. [Upgrade to Pro]"
                            "(https://app.crm-connectors.com/upgrade) to continue."
                        ),
                    )
                except Exception:
                    logger.exception("Failed to send upgrade prompt: %s")
            return Response(status_code=200)

        # Build modal
        object_id = parts[-1]
        obj_type = parts[1] if len(parts) > 2 else "contact"  # noqa: PLR2004
        # Build metadata
        channel_id = payload.get("channel", {}).get("id")
        response_url = payload.get("response_url")
        meta_dict = {
            "object_id": object_id,
            "object_type": obj_type,
            "contact_id": object_id if obj_type == "contact" else None,
        }
        if channel_id:
            meta_dict["channel_id"] = channel_id
        if response_url:
            meta_dict["response_url"] = response_url

        metadata = json.dumps(meta_dict)

        cards = CardBuilder()

        if action_id.startswith("open_add_note_modal"):
            modal = cards.build_note_modal(obj_type, object_id, metadata=metadata)
        else:
            modal = cards.build_meeting_modal(object_id, metadata=metadata)

        logger.info("Fast-path: opening modal for trigger=%s", trigger_id[:8])
        try:
            client = await self.integration_service.get_slack_client(integration)
            await client.views_open(trigger_id=trigger_id, view=modal)
            logger.info("Modal opened for object_id=%s", object_id)
        except Exception:
            logger.exception("Failed to open modal: %s")

        return Response(status_code=200)

    async def handle_fast_path_shortcuts(
        self,
        payload: dict,
        corr_id: str,
    ) -> Response | None:
        """Fast-path for shortcuts (e.g., Global Search / Create)."""
        callback_id = payload.get("callback_id")
        if callback_id not in (
            CREATE_RECORD_CALLBACK_ID,
            "create_hubspot_record_message",
        ):
            return None

        trigger_id = payload.get("trigger_id")
        team_id = str(payload.get("team", {}).get("id", ""))

        integration = await self.integration_service.get_integration_by_slack_team_id(
            team_id
        )
        if not (integration and integration.credentials.get("slack_bot_token")):
            return None

        # Tier check for Pro actions (Create)
        is_pro = await self.integration_service.is_pro_workspace(
            integration.workspace_id
        )
        if not is_pro:
            try:
                modal = {
                    "type": "modal",
                    "title": {"type": "plain_text", "text": "Upgrade to Pro"},
                    "blocks": [
                        {
                            "type": "section",
                            "text": {
                                "type": "mrkdwn",
                                "text": (
                                    "Creating records from Slack is a Professional "
                                    "feature. \n\n"
                                    "<https://app.crm-connectors.com/upgrade|"
                                    "Upgrade to Professional Plan>"
                                ),
                            },
                        }
                    ],
                }
                client = await self.integration_service.get_slack_client(integration)
                await client.views_open(trigger_id=trigger_id, view=modal)
            except Exception:
                logger.exception("Failed to open upgrade modal: %s")
            return Response(status_code=200)

        # Build modal
        modals = ModalBuilder()
        modal = modals.build_type_selection(CREATE_RECORD_CALLBACK_ID)

        channel_id = payload.get("channel", {}).get("id")
        response_url = payload.get("response_url")
        meta_dict = {}
        if channel_id:
            meta_dict["channel_id"] = channel_id
        if response_url:
            meta_dict["response_url"] = response_url

        if meta_dict:
            modal["private_metadata"] = json.dumps(meta_dict)

        try:
            client = await self.integration_service.get_slack_client(integration)
            await client.views_open(trigger_id=trigger_id, view=modal)
        except Exception:
            logger.exception("Failed to open global create modal: %s")

        return Response(status_code=200)
