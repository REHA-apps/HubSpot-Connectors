from __future__ import annotations

from fastapi import BackgroundTasks

from app.core.logging import CorrelationAdapter, get_logger
from app.integrations.ai_service import AIService
from app.services.channel_service import ChannelService

logger = get_logger("command.service")


class CommandService:
    """Handles Slack slash commands and delegates to ChannelService.

    Responsibilities:
    - Interpret /hs, /hs-contacts, /hs-leads, /hs-deals
    - Use AIService for intent detection on /hs
    - Schedule background tasks for HubSpot searches
    - Return immediate ephemeral responses to Slack
    """

    def __init__(self, corr_id: str) -> None:
        self.corr_id = corr_id
        self.log = CorrelationAdapter(logger, corr_id)
        self.channel_service = ChannelService(corr_id)

    async def handle_slack_command(
        self,
        *,
        command: str | None,
        text: str,
        workspace_id: str,
        response_url: str,
        background_tasks: BackgroundTasks,
    ) -> dict[str, str]:
        """Entry point for all Slack slash commands.
        Returns the immediate response payload to Slack.
        """
        if not command:
            self.log.warning("Missing command in Slack payload")
            return {"text": "Unknown command."}

        self.log.info(
            "Handling Slack command=%s text=%s workspace_id=%s",
            command,
            text,
            workspace_id,
        )

        # Normalize text
        query = text.strip()

        # Guard: empty query
        if not query:
            return self._usage_for(command)

        # Smart intent detection for /hs
        if command == "/hs":
            intent = AIService.detect_intent(query)
            self.log.info("Detected intent=%s for /hs query=%s", intent, query)

            if intent == "deal":
                command = "/hs-deals"
            elif intent == "lead":
                command = "/hs-leads"
            else:
                command = "/hs-contacts"

        # Contacts
        if command == "/hs-contacts":
            background_tasks.add_task(
                self.channel_service.search_and_respond_contacts,
                workspace_id,
                query,
                response_url,
            )
            return {
                "response_type": "ephemeral",
                "text": f"🔍 Searching HubSpot contacts for *{query}*...",
            }

        # Leads
        if command == "/hs-leads":
            background_tasks.add_task(
                self.channel_service.search_and_respond_leads,
                workspace_id,
                query,
                response_url,
            )
            return {
                "response_type": "ephemeral",
                "text": f"🟩 Searching HubSpot leads for *{query}*...",
            }

        # Deals
        if command == "/hs-deals":
            background_tasks.add_task(
                self.channel_service.search_and_respond_deals,
                workspace_id,
                query,
                response_url,
            )
            return {
                "response_type": "ephemeral",
                "text": f"💼 Searching HubSpot deals for *{query}*...",
            }

        self.log.warning("Unknown Slack command received: %s", command)
        return {"text": "Unknown command."}

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------
    def _usage_for(self, command: str) -> dict[str, str]:
        if command == "/hs-contacts":
            return {
                "text": "❌ Please provide an email: `/hs-contacts user@example.com`"
            }
        if command == "/hs-leads":
            return {"text": "❌ Usage: `/hs-leads john`"}
        if command == "/hs-deals":
            return {"text": "❌ Usage: `/hs-deals renewal`"}
        if command == "/hs":
            return {"text": "❌ Usage: `/hs <query>`"}
        return {"text": "❌ Missing query."}
