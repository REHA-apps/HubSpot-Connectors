from __future__ import annotations

from typing import Any

from app.core.models.ui import CardAction, UnifiedCard
from app.domains.ai.service import (
    AIThreadSummary,
)

from .components import ComponentsMixin

MAX_LIST_DISPLAY = 25
MAX_OWNERS_DISPLAY = 100


class ActionModalsMixin(ComponentsMixin):
    def build_card_modal(self, card: UnifiedCard, title: str = "Details") -> dict:
        """Wraps a UnifiedCard into a Slack Modal payload.

        Args:
            card (UnifiedCard): The unified card data structure to render.
            title (str, optional): The title of the modal. Defaults to "Details".

        Returns:
            dict: A Slack modal payload containing the rendered card blocks.

        """
        from app.connectors.hubspot_slack.slack_renderer import SlackRenderer

        renderer = SlackRenderer()
        payload = renderer.render(card)

        return {
            "type": "modal",
            "title": {"type": "plain_text", "text": title[:24]},
            "blocks": payload["blocks"],
            "close": {"type": "plain_text", "text": "Close"},
        }

    def build_meeting_modal(self, contact_id: str, metadata: str | None = None) -> dict:
        """Builds the Slack Modal for scheduling a meeting in HubSpot."""
        return {
            "type": "modal",
            "callback_id": "schedule_meeting_modal",
            "private_metadata": metadata or contact_id,
            "title": {"type": "plain_text", "text": "Schedule Meeting"},
            "submit": {"type": "plain_text", "text": "Create"},
            "close": {"type": "plain_text", "text": "Cancel"},
            "blocks": [
                {
                    "type": "input",
                    "block_id": "title_block",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "title_input",
                        "placeholder": {"type": "plain_text", "text": "Meeting Title"},
                    },
                    "label": {"type": "plain_text", "text": "Title"},
                },
                {
                    "type": "input",
                    "block_id": "date_block",
                    "element": {
                        "type": "datepicker",
                        "action_id": "date_input",
                        "placeholder": {"type": "plain_text", "text": "Select date"},
                    },
                    "label": {"type": "plain_text", "text": "Date"},
                },
                {
                    "type": "input",
                    "block_id": "time_block",
                    "element": {
                        "type": "timepicker",
                        "action_id": "time_input",
                        "placeholder": {"type": "plain_text", "text": "Select time"},
                    },
                    "label": {"type": "plain_text", "text": "Time"},
                },
                {
                    "type": "input",
                    "block_id": "body_block",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "body_input",
                        "multiline": True,
                        "placeholder": {
                            "type": "plain_text",
                            "text": "What is this meeting about?",
                        },
                    },
                    "label": {"type": "plain_text", "text": "Description"},
                    "optional": True,
                },
            ],
        }

    def build_loading_modal(self, title: str = "Loading...") -> dict:
        """Builds a simple loading modal payload."""
        return {
            "type": "modal",
            "title": {"type": "plain_text", "text": title[:24]},
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "⏳ *Fetching data from HubSpot...* Please wait.",
                    },
                }
            ],
        }

    def build_update_lead_type_modal(
        self, deal_id: str, current_value: str = "", metadata: str | None = None
    ) -> dict:
        """Builds the Slack Modal for updating a deal's Lead Type."""
        return {
            "type": "modal",
            "callback_id": "update_lead_type_modal",
            "private_metadata": metadata or deal_id,
            "title": {"type": "plain_text", "text": "Update Lead Type"},
            "submit": {"type": "plain_text", "text": "Update"},
            "close": {"type": "plain_text", "text": "Cancel"},
            "blocks": [
                {
                    "type": "input",
                    "block_id": "lead_type_block",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "lead_type_input",
                        "initial_value": current_value,
                        "placeholder": {
                            "type": "plain_text",
                            "text": "e.g. New Business, Renewal, etc.",
                        },
                    },
                    "label": {"type": "plain_text", "text": "Lead Type"},
                },
            ],
        }

    def build_note_modal(
        self, object_type: str, object_id: str, metadata: str | None = None
    ) -> dict:
        """Builds the Slack Modal for logging a note to HubSpot."""
        return {
            "type": "modal",
            "callback_id": "add_note_modal",
            "private_metadata": metadata or f"{object_type}:{object_id}",
            "title": {"type": "plain_text", "text": "Log a Note"},
            "submit": {"type": "plain_text", "text": "Save"},
            "close": {"type": "plain_text", "text": "Cancel"},
            "blocks": [
                {
                    "type": "input",
                    "block_id": "note_input",
                    "element": {
                        "type": "plain_text_input",
                        "action_id": "content",
                        "multiline": True,
                        "placeholder": {
                            "type": "plain_text",
                            "text": "What happened with this record?",
                        },
                    },
                    "label": {"type": "plain_text", "text": "Note Content"},
                }
            ],
        }

    def build_post_mortem_modal(
        self, deal_id: str, stage_id: str, metadata: str | None = None
    ) -> dict:
        """Builds the Win/Loss post-mortem modal."""
        is_won = "won" in stage_id.lower()
        title = "Closed Won Details" if is_won else "Closed Lost Details"

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": (
                        "*Almost there!* Please provide details for this deal "
                        "status change."
                    ),
                },
            }
        ]

        if is_won:
            blocks.append(
                self._input(
                    "Closed Won Reason",
                    "closed_won_reason",
                    placeholder="What was the key factor in winning?",
                )
            )
        else:
            blocks.append(
                self._select(
                    "Closed Lost Reason",
                    "closed_lost_reason",
                    [
                        ("Price", "price"),
                        ("Product Fit", "product_fit"),
                        ("Lost to Competitor", "competitor"),
                        ("Project Shelved", "shelved"),
                    ],
                )
            )

        return {
            "type": "modal",
            "callback_id": "post_mortem_submission",
            "private_metadata": metadata or f"{deal_id}:{stage_id}",
            "title": {"type": "plain_text", "text": title},
            "submit": {"type": "plain_text", "text": "Save & Close"},
            "close": {"type": "plain_text", "text": "Cancel"},
            "blocks": blocks,
        }

    def build_pricing_calculator_modal(
        self, deal_id: str, current_amount: float = 0.0, metadata: str | None = None
    ) -> dict:
        """Builds the pricing calculator modal."""
        return {
            "type": "modal",
            "callback_id": "calculator_submission",
            "private_metadata": metadata or deal_id,
            "title": {"type": "plain_text", "text": "Deal Calculator"},
            "submit": {"type": "plain_text", "text": "Calculate & Update"},
            "close": {"type": "plain_text", "text": "Cancel"},
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"Current Amount: `${current_amount:,}`",
                    },
                },
                self._input("Quantity", "quantity", placeholder="10"),
                self._input("Unit Price", "unit_price", placeholder="100.00"),
                self._input("Discount %", "discount_percent", placeholder="15"),
            ],
        }

    def build_next_step_enforcement_modal(
        self, deal_id: str, stage_id: str, metadata: str | None = None
    ) -> dict:
        """Forces a Next Step input before stage change."""
        return {
            "type": "modal",
            "callback_id": "next_step_enforcement_submission",
            "private_metadata": metadata or f"{deal_id}:{stage_id}",
            "title": {"type": "plain_text", "text": "Next Step Required"},
            "submit": {"type": "plain_text", "text": "Update Status"},
            "close": {"type": "plain_text", "text": "Cancel"},
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            "📈 *Stage Change Enforcement*\nYour manager requires a "
                            "'Next Step' to be set before moving this deal forward."
                        ),
                    },
                },
                self._input(
                    "Next Step",
                    "next_step",
                    placeholder="e.g. Schedule final demo with CTO",
                ),
            ],
        }

    def build_reassign_modal(
        self, object_id: str, owners: list[dict], metadata: str | None = None
    ) -> dict:
        """Builds modal to reassign owner."""
        owner_options = [(o["email"], o["id"]) for o in owners[:100]]
        return {
            "type": "modal",
            "callback_id": "reassign_owner_submission",
            "private_metadata": metadata or object_id,
            "title": {"type": "plain_text", "text": "Reassign Owner"},
            "submit": {"type": "plain_text", "text": "Reassign"},
            "close": {"type": "plain_text", "text": "Cancel"},
            "blocks": [
                self._select("Select New Owner", "hubspot_owner_id", owner_options),
            ],
        }

    def build_ai_recap_modal(
        self,
        object_type: str,
        object_id: str,
        summary: AIThreadSummary,
        metadata: str | None = None,
    ) -> dict[str, Any]:
        """Builds the AI Recap review modal."""
        # Clean summary for Slack
        recap_text = summary.summary
        key_points_text = "\n".join([f"• {p}" for p in summary.key_points])

        blocks = [
            {
                "type": "section",
                "text": {
                    "type": "mrkdwn",
                    "text": f"*AI Recap for {object_type.capitalize()} #{object_id}*",
                },
            },
            {
                "type": "section",
                "text": {"type": "mrkdwn", "text": f"*Summary:*\n{recap_text}"},
            },
        ]

        if key_points_text:
            blocks.append(
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": f"*Key Points:*\n{key_points_text}",
                    },
                }
            )

        blocks.append(
            {
                "type": "context",
                "elements": [
                    {"type": "mrkdwn", "text": f"Sentiment: *{summary.sentiment}*"}
                ],
            }
        )

        return {
            "type": "modal",
            "callback_id": "ai_recap_submission_modal",
            "private_metadata": metadata or f"{object_type}:{object_id}",
            "title": {"type": "plain_text", "text": "Review AI Recap"},
            "submit": {"type": "plain_text", "text": "Save to HubSpot"},
            "close": {"type": "plain_text", "text": "Cancel"},
            "blocks": blocks,
        }

    def build_disambiguation(self, options: list[dict]) -> UnifiedCard:
        actions = []
        for o in options:
            name = (
                o["properties"].get("name")
                or o["properties"].get("dealname")
                or o["properties"].get("subject")
                or o["properties"].get("hs_task_subject")
                or "Unknown"
            )
            actions.append(
                CardAction(
                    label=f"Select {name}",
                    action_type="callback",
                    value=f"select:{o.get('type')}:{o['id']}",
                )
            )

        return UnifiedCard(
            title="Which one did you mean?",
            emoji="❓",
            actions=actions,
        )
