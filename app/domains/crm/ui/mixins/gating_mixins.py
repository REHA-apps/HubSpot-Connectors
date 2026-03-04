from __future__ import annotations

from typing import Any


class GatingMixin:
    """Mixin for handling Pro-tier gating UI elements and modals."""

    def build_upgrade_nudge_modal(self, feature_name: str) -> dict[str, Any]:
        """Builds a Slack modal nudging the user to upgrade to Professional.

        Args:
            feature_name: The name of the feature they tried to access.

        Returns:
            A Slack modal payload.

        """
        feature_display = feature_name.replace("_", " ").title()

        return {
            "type": "modal",
            "title": {"type": "plain_text", "text": "Upgrade to Pro", "emoji": True},
            "blocks": [
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": (
                            f"✨ *{feature_display}* is a Professional feature.\n\n"
                            "Unlock advanced automation, AI-powered deals insights, "
                            "and deep CRM integrations by upgrading your workspace."
                        ),
                    },
                },
                {
                    "type": "section",
                    "text": {
                        "type": "mrkdwn",
                        "text": "• *AI Insights*: Get deep summaries of CRM objects.\n"
                        "• *Advanced Tools*: Access pricing calculators/schedulers.\n"
                        "• *Unlimited Activity*: Log unlimited notes and tasks.",
                    },
                },
                {"type": "divider"},
                {
                    "type": "actions",
                    "elements": [
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "🚀 Upgrade Now",
                                "emoji": True,
                            },
                            "style": "primary",
                            # TODO: Load from settings
                            "url": "https://reha-apps.com/pricing",
                            "action_id": "upgrade_link_click",
                        },
                        {
                            "type": "button",
                            "text": {
                                "type": "plain_text",
                                "text": "Contact Sales",
                                "emoji": True,
                            },
                            # TODO: Load from settings
                            "url": "https://reha-apps.com/contact",
                            "action_id": "contact_sales_click",
                        },
                    ],
                },
            ],
        }

    def _apply_gating_to_button(
        self,
        button: dict[str, Any],
        is_pro: bool,
        feature_id: str | None = None,
    ) -> None:
        """Modifies a Slack Block Kit button to visually indicate Pro gating.

        If `is_pro` is True, the button remains unaffected.
        If `is_pro` is False, a lock emoji is prepended to the button text,
        and the `action_id` is prefixed or changed so a gating modal can intercept it.

        Args:
            button: The Slack button block dict.
            is_pro: Whether the workspace has a Pro subscription.
            feature_id: Identifier for the gated capability (e.g., 'object_creation').

        """
        if is_pro:
            return  # No transformation needed for Pro workspaces

        # It's a free workspace, visual lockdown
        original_text = button.get("text", {}).get("text", "Action")
        button["text"]["text"] = f"🔒 {original_text}"

        # If it's gated, change the action_id so our service can intercept
        # and show the modal
        if feature_id:
            button["action_id"] = f"gated_feature_click:{feature_id}"
