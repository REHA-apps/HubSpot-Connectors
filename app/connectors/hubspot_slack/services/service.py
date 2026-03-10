from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.connectors.hubspot_slack.services.handlers.registry import InteractionRegistry
from app.core.logging import get_logger
from app.domains.ai.service import AIService
from app.domains.crm.hubspot.service import HubSpotService
from app.domains.crm.integration_service import IntegrationService
from app.domains.messaging.slack.service import SlackMessagingService

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
        integration: Any,
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
        integration: Any,
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
