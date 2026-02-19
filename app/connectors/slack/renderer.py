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

    def _actions(self, actions: list[CardAction]) -> dict:
        buttons = []
        for action in actions:
            button: dict[str, Any] = {
                "type": "button",
                "text": {"type": "plain_text", "text": action.label},
                "value": action.value,
            }
            if action.action_type == "url" and action.url:
                button["url"] = action.url

            # Map UnifiedCard actions to Slack action_ids if needed
            if "add_note" in action.value:
                button["action_id"] = "open_add_note_modal"
            elif "view_deals" in action.value:
                button["action_id"] = "view_deals"
            elif "view_contacts" in action.value:
                button["action_id"] = "view_contacts"

            buttons.append(button)

        return {"type": "actions", "elements": buttons}
