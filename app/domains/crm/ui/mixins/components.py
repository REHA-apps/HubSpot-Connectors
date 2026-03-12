from __future__ import annotations

import re
from typing import Any

from app.core.models.ui import UnifiedCard

MAX_LIST_DISPLAY = 25
MAX_OWNERS_DISPLAY = 100


class ComponentsMixin:
    def _input(
        self,
        label: str,
        action_id: str,
        placeholder: str = "",
        initial_value: str = "",
        multiline: bool = False,
        optional: bool = False,
    ) -> dict[str, Any]:
        element: dict[str, Any] = {"type": "plain_text_input", "action_id": action_id}
        if placeholder:
            element["placeholder"] = {"type": "plain_text", "text": placeholder}
        if initial_value:
            element["initial_value"] = initial_value
        if multiline:
            element["multiline"] = True

        return {
            "type": "input",
            "block_id": f"block_{action_id}",
            "element": element,
            "label": {"type": "plain_text", "text": label},
            "optional": optional,
        }

    def _select(
        self,
        label: str,
        action_id: str,
        options: list[tuple[str, str]],
        initial_option: str | None = None,
        optional: bool = False,
    ) -> dict[str, Any]:
        select_options = [
            {"text": {"type": "plain_text", "text": lbl}, "value": val}
            for lbl, val in options
        ]

        element: dict[str, Any] = {
            "type": "static_select",
            "action_id": action_id,
            "options": select_options,
            "placeholder": {"type": "plain_text", "text": "Select..."},
        }

        if initial_option:
            opt_obj = next(
                (o for o in select_options if o["value"] == initial_option), None
            )
            if opt_obj:
                element["initial_option"] = opt_obj

        return {
            "type": "input",
            "block_id": f"block_{action_id}",
            "element": element,
            "label": {"type": "plain_text", "text": label},
            "optional": optional,
        }

    def _datepicker(
        self,
        label: str,
        action_id: str,
        initial_date: str | None = None,
        optional: bool = False,
    ) -> dict[str, Any]:
        element: dict[str, Any] = {
            "type": "datepicker",
            "action_id": action_id,
        }
        if initial_date:
            element["initial_date"] = initial_date

        return {
            "type": "input",
            "block_id": f"block_{action_id}",
            "element": element,
            "label": {"type": "plain_text", "text": label},
            "optional": optional,
        }

    def _strip_html(self, text: str) -> str:
        """Remove HTML tags from text."""
        if not text:
            return ""
        # Remove tags
        clean = re.sub(r"<[^>]+>", "", text)
        # Restore logical newlines if implied by BR or P
        # (This simple regex just deletes tags. For better formatting,
        # replace <br> with \n before stripping)
        # Let's try to be slightly smarter: replace <br> and </p> with newlines first
        text_with_newlines = re.sub(r"(?i)<br\s*/?>", "\n", text)
        text_with_newlines = re.sub(r"(?i)</p>", "\n", text_with_newlines)
        clean = re.sub(r"<[^>]+>", "", text_with_newlines)
        return clean.strip()

    def build_empty(self, message: str) -> UnifiedCard:
        return UnifiedCard(
            title="Notification",
            emoji="ℹ️",
            content=message,
        )
