from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.connectors.slack.ui import CardBuilder
from app.core.config import settings
from app.core.models.ui import UnifiedCard


class HubSpotRenderer:
    """Description:
    Converts a UnifiedCard IR into HubSpot CRM Card JSON.
    """

    def render(self, object_id: str, card: UnifiedCard) -> dict[str, Any]:
        properties = []

        # Convert subtitle, emoji, metrics into properties
        summary_parts = []
        if card.emoji:
            summary_parts.append(f"Type: {card.emoji} {card.subtitle or ''}")
        elif card.subtitle:
            summary_parts.append(f"Type: {card.subtitle}")

        for label, value in card.metrics:
            properties.append({"label": label, "value": value})

        if card.content:
            summary_parts.append(card.content)

        for label, text in card.secondary_content:
            summary_parts.append(f"{label}: {text}")

        # Add a combined "Summary" property for HubSpot's limited UI
        properties.append({"label": "AI Insights", "value": "\n".join(summary_parts)})

        # 4. Badge Handling
        if card.badge:
            properties.insert(0, {"label": "Plan", "value": card.badge})

        actions = []
        # 5. Upgrade Action
        if card.badge == "Free Version":
            actions.append(
                {
                    "type": "IFRAME",
                    "width": 890,
                    "height": 748,
                    "uri": "https://app.crm-connectors.com/upgrade",
                    "label": "🚀 Upgrade to Pro",
                }
            )

        for action in card.actions:
            if action.action_type == "url":
                actions.append(
                    {
                        "type": "IFRAME",  # Or keep ACTION_HOOK if preferred
                        "width": 890,
                        "height": 748,
                        "uri": action.url,
                        "label": action.label,
                    }
                )

        # Keep the standard "Send to Slack" action
        actions.append(
            {
                "type": "ACTION_HOOK",
                "httpMethod": "POST",
                "label": "Send to Slack",
                "url": f"{settings.API_BASE_URL}/hubspot/actions/send-to-slack",
            }
        )

        return {
            "objectId": object_id,
            "title": card.title or "CRM Insights",
            "properties": properties,
            "actions": actions,
        }


def build_crm_card_result(
    object_id: str,
    obj: Mapping[str, Any],
    analysis: Any,
) -> dict[str, Any]:
    # 1. Build the Unified IR
    builder = CardBuilder()
    unified_card = builder.build(obj, analysis)

    # 2. Render for HubSpot
    renderer = HubSpotRenderer()
    return renderer.render(object_id, unified_card)


def build_crm_card_response(results: list[dict[str, Any]]) -> dict[str, Any]:
    return {"results": results}
