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
            if action.value.startswith("view:"):
                button["action_id"] = f"view_object:{action.value}"
            elif action.value.startswith("select:"):
                button["action_id"] = f"select_object:{action.value}"
            elif "add_note" in action.value:
                button["action_id"] = f"open_add_note_modal:{action.value}"
            elif action.value.startswith("view_contact_deals"):
                button["action_id"] = f"view_contact_deals:{action.value}"
            elif action.value.startswith("view_contact_company"):
                button["action_id"] = f"view_contact_company:{action.value}"
            elif "view_deals" in action.value:
                button["action_id"] = f"view_deals:{action.value}"
            elif "view_contacts" in action.value:
                button["action_id"] = f"view_contacts:{action.value}"
            elif action.value.startswith("view_contact_meetings"):
                button["action_id"] = f"view_contact_meetings:{action.value}"
            elif "schedule_meeting" in action.value:
                button["action_id"] = f"open_schedule_meeting_modal:{action.value}"

            elements.append(button)

        return {"type": "actions", "elements": elements}
