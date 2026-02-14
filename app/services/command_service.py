# app/services/command_service.py
from __future__ import annotations

from fastapi import BackgroundTasks

from app.core.logging import CorrelationAdapter, get_logger
from app.integrations.ai_service import AIService
from app.services.channel_service import ChannelService
from app.services.hubspot_service import HubSpotService
from app.services.integration_service import IntegrationService
from app.utils.constants import EXPLICIT_COMMANDS

logger = get_logger("command.service")


class CommandService:
    """Handles Slack slash commands and delegates to ChannelService.

    Responsibilities:
    - Interpret /hs, /hs-contacts, /hs-leads, /hs-deals
    - Use AIService for intent detection on /hs
    - Schedule background tasks for HubSpot searches
    - Return immediate ephemeral responses to Slack
    """

    def __init__(self, corr_id: str, integration):
        self.corr_id = corr_id
        self.log = CorrelationAdapter(logger, corr_id)
        self.integration = integration

        # Shared per-request dependencies
        self.ai = AIService()
        self.ai.set_corr_id(corr_id)

        self.hubspot = HubSpotService(corr_id)

        self.channel_service = ChannelService(
            corr_id=corr_id,
            ai=self.ai,
            hubspot=self.hubspot,
            integration_service=IntegrationService(corr_id),
            slack_integration=integration,
        )

    async def handle_slack_command(
        self,
        *,
        command: str | None,
        text: str,
        workspace_id: str,
        response_url: str,
        channel_id: str,
        background_tasks: BackgroundTasks,
    ) -> dict[str, str]:
        if not command:
            self.log.warning("Missing command in Slack payload")
            return {"text": "Unknown command."}

        self.log.info(
            "Handling Slack command=%s text=%s workspace_id=%s",
            command,
            text,
            workspace_id,
        )

        query = text.strip()
        if not query:
            return self._usage_for(command)
        # Smart intent detection for /hs
        if command not in EXPLICIT_COMMANDS:
            if command == "/hs":
                intent = self.ai.detect_intent(query)
                self.log.info("Detected intent=%s for /hs query=%s", intent, query)

                match intent:
                    case "deal":
                        command = "/hs-deals"
                    case "lead":
                        command = "/hs-leads"
                    case _:
                        command = "/hs-contacts"
            else:
                self.log.warning("Unknown Slack command received: %s", command)
                return {"text": "Unknown command."}

        object_type, prefix = EXPLICIT_COMMANDS[command]
        # Schedule background search
        background_tasks.add_task(
            self.channel_service.search_and_send,
            workspace_id,
            query,
            channel_id,
            response_url,
            object_type,
            self.corr_id,
        )

        # Immediate ephemeral response
        return {
            "response_type": "ephemeral",
            "text": f"{prefix} for *{query}*...",
        }

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------
    def _usage_for(self, command: str) -> dict[str, str]:
        usage = {
            "/hs-contacts": "Usage: `/hs-contacts user@example.com`",
            "/hs-leads": "Usage: `/hs-leads john`",
            "/hs-deals": "Usage: `/hs-deals renewal`",
            "/hs": "Usage: `/hs <query>`",
        }
        return {"text": usage.get(command, "Missing query.")}
