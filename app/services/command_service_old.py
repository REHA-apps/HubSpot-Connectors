# app/services/command_service.py
from __future__ import annotations

from fastapi import BackgroundTasks

from app.core.logging import CorrelationAdapter, get_logger
from app.integrations.ai_service import AIService
from app.services.channel_service import ChannelService
from app.services.hubspot_service import HubSpotService

logger = get_logger("command.service")


class CommandService:
    """Handles Slack slash commands."""

    def __init__(self, corr_id: str) -> None:
        self.corr_id = corr_id
        self.log = CorrelationAdapter(logger, corr_id)

    async def handle_slack_command(
        self,
        command: str,
        text: str,
        workspace_id: str,
        response_url: str,
        background_tasks: BackgroundTasks,
    ) -> dict[str, str]:
        if not text:
            return {"text": "❌ Please provide a search query."}

        hubspot = HubSpotService(self.corr_id)
        channel = ChannelService(self.corr_id)

        # Smart intent detection for /hs
        if command == "/hs":
            intent = AIService.detect_intent(text)
            if intent == "deal":
                command = "/hs-deals"
            elif intent == "lead":
                command = "/hs-leads"
            else:
                command = "/hs-contacts"

        # Contacts
        if command == "/hs-contacts":
            background_tasks.add_task(
                channel.search_and_respond_contacts,
                workspace_id,
                text,
                response_url,
            )
            return {
                "response_type": "ephemeral",
                "text": f"🔍 Searching HubSpot contacts for *{text}*...",
            }

        # Deals
        if command == "/hs-deals":
            background_tasks.add_task(
                channel.search_and_respond_deals,
                workspace_id,
                text,
                response_url,
            )
            return {
                "response_type": "ephemeral",
                "text": f"💼 Searching HubSpot deals for *{text}*...",
            }

        # Leads
        if command == "/hs-leads":
            background_tasks.add_task(
                channel.search_and_respond_leads,
                workspace_id,
                text,
                response_url,
            )
            return {
                "response_type": "ephemeral",
                "text": f"🟩 Searching HubSpot leads for *{text}*...",
            }

        return {"text": "Unknown command."}
