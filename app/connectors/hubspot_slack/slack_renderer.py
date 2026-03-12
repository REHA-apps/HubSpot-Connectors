from __future__ import annotations

from typing import Any

from app.core.models.ui import CardAction, UnifiedCard


class SlackRenderer:
    """Description:
    Converts a UnifiedCard IR into Slack Block Kit payload.
    """

    def render(self, card: UnifiedCard) -> dict[str, Any]:
        blocks: list[dict[str, Any]] = []

        # Header
        if card.title:
            blocks.append(self._header(card.title, card.emoji))

        # Context (Subtitle)
        if card.subtitle:
            blocks.append(self._context(f"*{card.subtitle}*"))

        # Metrics (Fields)
        if card.metrics:
            blocks.append(self._fields(card.metrics))

        # Primary Content
        if card.content:
            blocks.append(self._markdown(card.content))

        # Secondary Content
        for label, text in card.secondary_content:
            blocks.append(self._markdown(f"*{label}:*\n{text}"))

        # Actions
        if card.actions:
            blocks.append(self._actions(card.actions))

        # Footer
        if card.footer:
            blocks.append(self._context(card.footer))

        return {"blocks": blocks}

    def _header(self, text: str, emoji: str | None = None) -> dict:
        prefix = f"{emoji} " if emoji else ""
        return {
            "type": "header",
            "text": {"type": "plain_text", "text": f"{prefix}{text}", "emoji": True},
        }

    def _markdown(self, text: str) -> dict:
        return {"type": "section", "text": {"type": "mrkdwn", "text": text}}

    def _fields(self, fields: list[tuple[str, str]]) -> dict:
        return {
            "type": "section",
            "fields": [
                {"type": "mrkdwn", "text": f"*{label}:*\n{value}"}
                for label, value in fields
            ],
        }

    def _context(self, text: str) -> dict:
        return {"type": "context", "elements": [{"type": "mrkdwn", "text": text}]}

    def _actions(self, actions: list[CardAction]) -> dict:  # noqa: PLR0912
        elements = []
        for action in actions:
            if action.action_type == "select" and action.options:
                # Render a static select menu
                placeholder_text = action.label
                if len(placeholder_text) > 75:  # noqa: PLR2004
                    placeholder_text = placeholder_text[:72] + "..."

                select: dict[str, Any] = {
                    "type": "static_select",
                    "placeholder": {
                        "type": "plain_text",
                        "text": placeholder_text,
                    },
                    "action_id": action.value,  # ensure this is unique!
                    "options": [],
                }

                for opt_label, value in action.options:
                    if len(opt_label) > 75:  # noqa: PLR2004
                        label_text = opt_label[:72] + "..."
                    else:
                        label_text = opt_label
                    select["options"].append(
                        {
                            "text": {"type": "plain_text", "text": label_text},
                            "value": str(value),
                        }
                    )

                # Set initial option if provided
                if action.selected_option:
                    # Find the option object that matches the selected value
                    initial = next(
                        (
                            opt
                            for opt in select["options"]
                            if opt["value"] == action.selected_option
                        ),
                        None,
                    )
                    if initial:
                        select["initial_option"] = initial

                elements.append(select)
                continue

            # Render a button (default)
            button_text = action.label
            if action.is_gated:
                button_text = f"🔒 {button_text}"

            if len(button_text) > 75:  # noqa: PLR2004
                button_text = button_text[:72] + "..."

            button: dict[str, Any] = {
                "type": "button",
                "text": {"type": "plain_text", "text": button_text},
                "value": action.value,
            }
            if action.action_type == "url" and action.url:
                button["url"] = action.url

            # Map UnifiedCard actions to Slack action_ids for dispatch.
            # Append value to ensure uniqueness (Slack requires unique
            # action_id per actions block when multiple buttons exist).
            # Map UnifiedCard actions to Slack action_ids for dispatch.
            # Append value to ensure uniqueness (Slack requires unique
            # action_id per actions block when multiple buttons exist).
            action_map = {
                "view:": "view_object",
                "select:": "select_object",
                "add_note": "open_add_note_modal",
                "view_contact_deals": "view_contact_deals",
                "view_contact_company": "view_contact_company",
                "view_company_deals": "view_company_deals",
                "view_deals": "view_deals",
                "view_contacts": "view_contacts",
                "view_contact_meetings": "view_contact_meetings",
                "schedule_meeting": "open_schedule_meeting_modal",
                "update_lead_source": "open_update_lead_source_modal",
                "update_deal_type": "open_update_deal_type_modal",
                "update_forecast_amount": "open_update_forecast_amount_modal",
                "add_task": "open_add_task_modal",
                "ai_recap": "open_ai_recap_modal",
                "open_calculator": "open_calculator",
                "reassign_owner": "reassign_owner",
            }

            action_id = next(
                (prefix for prefix in action_map if prefix in action.value), None
            )

            if action.is_gated and action_id:
                # Map internal action id to the pro feature name
                feature_map = {
                    "open_add_note_modal": "note_logging",
                    "open_ai_recap_modal": "ai_insights",
                    "open_calculator": "pricing_calculator",
                    "open_schedule_meeting_modal": "meeting_scheduler",
                }
                feature_name = feature_map.get(
                    action_map[action_id], action_map[action_id]
                )
                button["action_id"] = f"gated_feature_click:{feature_name}"
            elif action_id:
                button["action_id"] = f"{action_map[action_id]}:{action.value}"

            elements.append(button)

        return {"type": "actions", "elements": elements}
