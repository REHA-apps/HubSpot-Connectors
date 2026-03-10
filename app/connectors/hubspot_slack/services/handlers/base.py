from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from slack_sdk.web.async_client import AsyncWebClient

from app.core.logging import get_logger
from app.core.models.ui import UnifiedCard
from app.domains.ai.service import AIService
from app.domains.crm.hubspot.service import HubSpotService
from app.domains.crm.integration_service import IntegrationService
from app.domains.crm.ui.card_builder import CardBuilder
from app.domains.messaging.slack.service import SlackMessagingService

logger = get_logger("base_handler")


class InteractionHandler(ABC):
    def __init__(
        self,
        corr_id: str,
        hubspot: HubSpotService,
        ai: AIService,
        integration_service: IntegrationService,
    ):
        self.corr_id = corr_id
        self.hubspot = hubspot
        self.ai = ai
        self.integration_service = integration_service

    @abstractmethod
    async def handle(
        self,
        payload: Mapping[str, Any],
        integration: Any,
        messaging_service: SlackMessagingService,
        **kwargs: Any,
    ) -> Any:
        pass

    async def _show_loading(
        self, trigger_id: str, title: str, integration: Any
    ) -> str | None:
        """Opens a loading modal immediately to secure the trigger_id window."""
        bot_token = integration.credentials.get("slack_bot_token")
        if not bot_token:
            return None
        try:
            from app.domains.crm.ui.card_builder import CardBuilder

            builder = CardBuilder()
            modal = builder.build_loading_modal(title=title)
            resp = await self.integration_service.slack_channel.open_view(
                bot_token=bot_token, trigger_id=trigger_id, view=modal
            )
            if not resp or not resp.get("ok"):
                logger.error(
                    "Failed to show loading modal: %s",
                    resp.get("error") if resp else "No response",
                )
                return None
            view = resp.get("view")
            if not view or not isinstance(view, dict):
                return None
            return str(view.get("id"))
        except Exception as exc:
            logger.error("Failed to show loading modal: %s", exc)
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
            from app.domains.crm.ui.card_builder import CardBuilder

            if isinstance(view_or_card, dict):
                modal = view_or_card
            else:
                builder = CardBuilder()
                modal = builder.build_card_modal(view_or_card, title=title)
            client = AsyncWebClient(token=bot_token)
            await client.views_update(view_id=view_id, view=modal)
            logger.info("Modal updated for view_id=%s", view_id[:8])
            return True
        except Exception as exc:
            logger.error("Failed to update modal '%s': %s", title, exc)
            return False

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
