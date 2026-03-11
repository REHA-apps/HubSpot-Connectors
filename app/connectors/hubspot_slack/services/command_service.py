from __future__ import annotations

from typing import Any

from fastapi import BackgroundTasks

from app.core.logging import get_logger, run_task_with_context
from app.domains.ai.service import AIService
from app.domains.crm.hubspot.service import HubSpotService
from app.domains.crm.integration_service import IntegrationService
from app.domains.messaging.slack.service import SlackMessagingService
from app.utils.constants import EXPLICIT_COMMANDS

logger = get_logger("slack.command.service")


class CommandService:
    """Description:
    Broker service for processing and delegating Slack slash commands.
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
        self.integration = integration

        # Shared per-request dependencies
        self.ai = ai or AIService(corr_id)
        self.hubspot = HubSpotService(corr_id)

        _integration_service = integration_service or IntegrationService(corr_id)
        self.messaging_service = SlackMessagingService(
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
        # 1. Resolve Tier
        is_pro = await self.messaging_service.integration_service.is_pro_workspace(
            workspace_id
        )

        # 2. Gate Pro commands
        if command == "/hs-tasks" and not is_pro:
            return {
                "response_type": "ephemeral",
                "text": (
                    "Your Pro trial has ended. To continue creating tasks from Slack, "
                    "upgrade to the Professional plan [Upgrade Now](https://app.crm-connectors.com/upgrade)."
                ),
            }

        if not command:
            return {"response_type": "ephemeral", "text": "Unknown command."}

        query = text.strip()

        if (
            query.lower() == "help"
            or command == "/hs-help"
            or (command == "/hs" and query == "")
        ):
            return self._usage_for("/hs")

        if command == "/hs-reports" or (
            command == "/hs" and query.lower().startswith("report")
        ):
            background_tasks.add_task(
                run_task_with_context,
                self.corr_id,
                self._send_report_command,
                workspace_id,
                response_url,
            )
            return {"response_type": "ephemeral", "text": "Fetching reports..."}

        if command == "/hs":
            command = "/hs-contacts"

        if not query:
            return self._usage_for(command)

        if command not in EXPLICIT_COMMANDS:
            return {"response_type": "ephemeral", "text": "Unknown command."}

        cfg = EXPLICIT_COMMANDS[command]
        object_type = cfg["object_type"]
        prefix = cfg["prefix"]

        # 3. Schedule in background
        background_tasks.add_task(
            run_task_with_context,
            self.corr_id,
            self.messaging_service.search_and_send,
            workspace_id,
            query,
            channel_id,
            response_url,
            object_type,
            self.corr_id,
            user_id,
        )

        return {
            "response_type": "ephemeral",
            "text": f"{prefix} for *{query}*...",
        }

    async def _handle_hs_task_creation(
        self, workspace_id: str, text: str, user_id: str, response_url: str
    ) -> None:
        """Process advanced /hs-task parameters and create hit HubSpot task."""
        from app.utils.parsers import parse_hs_task_command
        from app.utils.transformers import to_hubspot_timestamp

        try:
            parsed = parse_hs_task_command(text)
            subject = parsed["subject"]
            slack_owner_id = parsed["slack_user_id"]
            due_date = parsed["due_date"]

            properties: dict[str, Any] = {
                "hs_task_subject": subject,
                "hs_task_status": "NOT_STARTED",
            }

            owner_msg = ""
            # 1. Resolve HubSpot Owner
            if slack_owner_id:
                channel_inst = await self.messaging_service.get_slack_channel()
                slack_client = channel_inst.get_slack_client()

                # Get mentioned user email
                user_info = await slack_client.users_info(user=slack_owner_id)
                if user_info.get("ok"):
                    email = user_info["user"]["profile"].get("email")
                    if email:
                        owners = await self.hubspot.get_owners(workspace_id)
                        hs_owner = next(
                            (o for o in owners if o.get("email") == email), None
                        )
                        if hs_owner:
                            properties["hubspot_owner_id"] = hs_owner["id"]
                            owner_msg = f" assigned to <@{slack_owner_id}>"

            # 2. Set Due Date
            if due_date:
                properties["hs_timestamp"] = to_hubspot_timestamp(
                    due_date, corr_id=self.corr_id
                )

            # 3. Create Task
            await self.hubspot.create_task(workspace_id, properties)

            due_msg = f" (Due: {due_date.strftime('%Y-%m-%d')})" if due_date else ""
            success_text = f"✅ Created HubSpot task: *{subject}*{owner_msg}{due_msg}"

            await self.messaging_service.send_via_response_url(
                response_url=response_url, text=success_text
            )

        except Exception:
            logger.exception("Task creation failed: %s")
            await self.messaging_service.send_via_response_url(
                response_url=response_url, text="❌ Failed to create HubSpot task."
            )

    async def _send_report_command(self, workspace_id: str, response_url: str) -> None:
        """Handle /hs report command in the background."""
        try:
            client = await self.hubspot.get_client(workspace_id)
            details = await client.get_account_details()
            portal_id = details.get("portalId") if details else None

            if not portal_id:
                await self.messaging_service.send_via_response_url(
                    response_url=response_url,
                    text="Could not determine HubSpot Portal ID.",
                )
                return

            dashboard_url = f"https://app.hubspot.com/reports-dashboard/{portal_id}"
            analytics_url = f"https://app.hubspot.com/reports-list/{portal_id}"

            blocks = [
                {
                    "type": "section",
                    "text": {"type": "mrkdwn", "text": "📊 *HubSpot Reporting*"},
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            "Access your dashboards and reports directly in HubSpot:"
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
            ]
            await self.messaging_service.send_via_response_url(
                response_url=response_url, text="HubSpot Reporting", blocks=blocks
            )
        except Exception:
            logger.exception("Report command failed: %s")
            await self.messaging_service.send_via_response_url(
                response_url=response_url, text="Failed to fetch reporting details."
            )

    def _usage_for(self, command: str) -> dict[str, str]:
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
        }
        if command == "/hs":
            text = "Here are the available commands:\n" + "\n".join(
                f"• {u}" for u in usage.values()
            )
            text += (
                "\n• Usage: `/hs-reports <query>` - View HubSpot reports and dashboards"
            )
            text += "\n• Usage: `/hs-help` - Show this help message"
        else:
            text = usage.get(command, "Usage: `/<command> <query>`.")
            text += "\nTry `/hs help` for a list of all commands."

        return {"response_type": "ephemeral", "text": text}
