# app/integrations/hubspot_cards.py
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.api.slack.card_builder import build_card
from app.integrations.ai_service import AIContactAnalysis
from app.core.config import settings


def build_crm_card_result(
    object_id: str,
    obj: Mapping[str, Any],
    analysis: AIContactAnalysis,
) -> dict[str, Any]:
    slack_card = build_card(obj, analysis)

    sections: list[str] = []
    for block in slack_card.get("blocks", []):
        if block.get("type") == "section":
            text = block.get("text", {}).get("text")
            if text:
                sections.append(text)

    return {
        "objectId": object_id,
        "title": "Slack AI Insights",
        "properties": [
            {
                "label": "Summary",
                "value": "\n".join(sections),
            }
        ],
        "actions": [
            {
                "type": "ACTION_HOOK",
                "httpMethod": "POST",
                "label": "Send to Slack",
                "url": f"{settings.API_BASE_URL}/hubspot/actions/send-to-slack",
            }
        ],
    }


def build_crm_card_response(results: list[dict[str, Any]]) -> dict[str, Any]:
    return {"results": results}