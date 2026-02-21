from __future__ import annotations

from typing import Any

from fastapi import BackgroundTasks

from app.core.logging import CorrelationAdapter, get_logger
from app.domains.ai.service import AIService
from app.domains.crm.channel_service import ChannelService
from app.domains.crm.hubspot.service import HubSpotService
from app.domains.crm.integration_service import IntegrationService
from app.utils.constants import EXPLICIT_COMMANDS

logger = get_logger("command.service")


class CommandService:
    """Description:
        Broker service for processing and delegating Slack slash commands.

    Rules Applied:
        - Harmonizes diverse Slack commands into structured background search tasks.
        - Provides immediate ephemeral acknowledgements to meet Slack latency
          requirements.
        - Leverages AIService for intelligent intent resolution.
    """

    def __init__(
        self,
        corr_id: str,
        integration,
        *,
        ai: AIService | None = None,
        integration_service: IntegrationService | None = None,
    ):
        self.corr_id = corr_id
        self.log = CorrelationAdapter(logger, corr_id)
        self.integration = integration

        # Shared per-request dependencies
        self.ai = ai or AIService(corr_id)

        self.hubspot = HubSpotService(corr_id)

        _integration_service = integration_service or IntegrationService(corr_id)
        self.channel_service = ChannelService(
            corr_id=corr_id,
            integration_service=_integration_service,
            slack_integration=integration,
        )

    async def handle_slack_command(  # noqa: PLR0911
        self,
        *,
        command: str | None,
        text: str,
        workspace_id: str,
        response_url: str,
        channel_id: str,
        user_id: str = "",
        background_tasks: BackgroundTasks,
    ) -> dict[str, Any]:
        # 1. Validate command immediately
        if not command:
            return {"response_type": "ephemeral", "text": "Unknown command."}

        query = text.strip()

        # 2. Resolve command type with minimal logic
        if query.lower() == "help" or (command == "/hs" and query == ""):
            return self._usage_for(command)

        if command == "/hs":
            if query.lower().startswith("report"):
                return await self._handle_report_command(workspace_id)

            # This `if not query` block is now redundant for /hs commands
            # because `(command == "/hs" and query == "")` would have caught it earlier.
            # However, keeping it here for other potential /hs sub-commands that might
            # require a query but are not 'report'.
            if not query:
                return self._usage_for(command)

            # Default /hs to contacts search if not report
            command = "/hs-contacts"

        if not query:
            return self._usage_for(command)

        if command not in EXPLICIT_COMMANDS:
            return {"response_type": "ephemeral", "text": "Unknown command."}

        cfg = EXPLICIT_COMMANDS[command]
        object_type = cfg["object_type"]
        prefix = cfg["prefix"]

        # 3. Schedule ALL heavy work in background
        background_tasks.add_task(
            self.channel_service.search_and_send,
            workspace_id,
            query,
            channel_id,
            response_url,
            object_type,
            self.corr_id,
            user_id,
        )

        # 4. Return instantly (Slack requirement)
        return {
            "response_type": "ephemeral",
            "text": f"{prefix} for *{query}*...",
        }

    async def _handle_report_command(self, workspace_id: str) -> dict[str, Any]:
        """Handle /hs report command."""
        try:
            client = await self.hubspot.get_client(workspace_id)
            details = await client.get_account_details()
            portal_id = details.get("portalId")

            if not portal_id:
                return {
                    "response_type": "ephemeral",
                    "text": "Could not determine HubSpot Portal ID.",
                }

            dashboard_url = f"https://app.hubspot.com/reports/{portal_id}/dashboards"
            analytics_url = (
                f"https://app.hubspot.com/analytics/{portal_id}/reports/list"
            )

            return {
                "response_type": "ephemeral",
                "blocks": [
                    {
                        "type": "section",
                        "text": {"type": "mrkdwn", "text": "📊 *HubSpot Reporting*"},
                    },
                    {
                        "type": "section",
                        "text": {
                            "type": "mrkdwn",
                            "text": (
                                "Access your dashboards and reports "
                                "directly in HubSpot:"
                            ),
                        },
                    },
                    {
                        "type": "actions",
                        "elements": [
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "Open Dashboards",
                                    "emoji": True,
                                },
                                "url": dashboard_url,
                                "action_id": "open_dashboard",
                            },
                            {
                                "type": "button",
                                "text": {
                                    "type": "plain_text",
                                    "text": "View All Reports",
                                    "emoji": True,
                                },
                                "url": analytics_url,
                                "action_id": "open_reports",
                            },
                        ],
                    },
                ],
            }
        except Exception as exc:
            self.log.error("Report command failed: %s", exc)
            return {
                "response_type": "ephemeral",
                "text": "Failed to fetch reporting details.",
            }

    # Helper methods
    def _usage_for(self, command: str) -> dict[str, str]:
        """Returns helpful usage instructions for slash commands."""
        usage = {
            "/hs": (
                "Usage: `/hs <query>` - Searches across CRM (Contacts, Companies, "
                "Deals, etc). You can also type `/hs report` for insights."
            ),
            "/hs-contacts": "Usage: `/hs-contacts <name or email>`",
            "/hs-leads": "Usage: `/hs-leads <name or email>`",
            "/hs-companies": "Usage: `/hs-companies <company name or domain>`",
            "/hs-deals": "Usage: `/hs-deals <deal name>`",
            "/hs-tickets": "Usage: `/hs-tickets <subject or ID>`",
            "/hs-tasks": "Usage: `/hs-tasks <task name>`",
            "/hs-kb": "Usage: `/hs-kb <topic>`",
            "/hs-playbook": "Usage: `/hs-playbook <playbook name>`",
        }
        text = usage.get(command, "Usage: `/<command> <query>`.")
        if command != "/hs":
            text += "\nTry `/hs help` for a list of all commands."

        return {"response_type": "ephemeral", "text": text}
