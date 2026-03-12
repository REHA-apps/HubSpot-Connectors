from __future__ import annotations

from typing import Any

from app.domains.crm.ui.mixins.action_modals import ActionModalsMixin
from app.domains.crm.ui.mixins.ai_cards import AICardsMixin
from app.domains.crm.ui.mixins.components import ComponentsMixin
from app.domains.crm.ui.mixins.gating_mixins import GatingMixin
from app.domains.crm.ui.mixins.list_cards import ListCardsMixin
from app.domains.crm.ui.mixins.object_cards import ObjectCardsMixin

MAX_LIST_DISPLAY = 25
MAX_OWNERS_DISPLAY = 100


class CardBuilder(
    ObjectCardsMixin,
    AICardsMixin,
    ListCardsMixin,
    ActionModalsMixin,
    GatingMixin,
    ComponentsMixin,
):
    """Description:
        Unified utility for building platform-agnostic CRM and AI insight cards.

    Rules Applied:
        - Returns UnifiedCard IR.
        - Centralizes rendering logic for Contacts, Deals, Companies, Tickets,
          and Tasks.
    """

    def build_app_home_view(self) -> dict[str, Any]:
        """Provides a static Home tab dashboard layout for the App Home view.

        Returns:
            dict[str, Any]: The Slack Home tab view payload.

        """
        blocks = [
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "🏠 Welcome to REHA Connect",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "Search HubSpot contacts, companies, deals, tickets, and tasks "
                        "directly from Slack. Access CRM data seamlessly without "
                        "switching apps!"
                    ),
                },
            },
            {"type": "divider"},
            {
                "type": "header",
                "text": {
                    "type": "plain_text",
                    "text": "⚡ Available Commands",
                    "emoji": True,
                },
            },
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "- `/hs <query>` - Smart AI search across entire CRM\n"
                        "- `/hs` `/hs help` `/hs-help` - "
                        "Show help and available commands\n"
                        "- `/hs report` `/hs-reports` - View HubSpot dashboards\n"
                        "- `/hs-companies <domain or name>` - Search Companies\n"
                        "- `/hs-contacts <email or name>` - Search Contacts\n"
                        "- `/hs-deals <deal name>` - Search Deals\n"
                        "- `/hs-tickets <subject or ID>` - Search Tickets\n"
                        "- `/hs-tasks <task name>` - Search Tasks"
                    ),
                },
            },
            {"type": "divider"},
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "💡 *Quick Tip*: You can quickly create new CRM records "
                        "directly in Slack using the `Create HubSpot Record` "
                        "shortcut from the global Shortcuts menu."
                    ),
                },
            },
        ]

        return {"type": "home", "blocks": blocks}
