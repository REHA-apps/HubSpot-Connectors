# app/services/channel_service.py
from __future__ import annotations

from app.api.slack.schemas import SlackSearchResponse
from app.core.logging import CorrelationAdapter, get_logger
from app.integrations.ai_service import AIService
from app.integrations.slack_ui import (
    build_contact_card,
)

logger = get_logger("channel.service")


class ChannelService:
    """Channel-agnostic message delivery.
    Converts domain objects into Slack/WhatsApp messages.
    """

    def __init__(self, corr_id: str) -> None:
        self.corr_id = corr_id
        self.log = CorrelationAdapter(logger, corr_id)

    async def send_contact_to_slack(
        self,
        connector,
        contact: dict,
        channel: str,
    ):
        ai_summary = AIService.generate_contact_insight(contact)

        response = SlackSearchResponse(
            contact_name=f"{contact['properties'].get('firstname', '')} {contact['properties'].get('lastname', '')}".strip(),
            contact_email=contact["properties"].get("email", ""),
            current_status=contact["properties"].get("lifecyclestage", "unknown"),
            last_contacted="Never",
            ai_summary=ai_summary,
        )

        blocks = build_contact_card(contact, ai_summary)["blocks"]

        return await connector.send_event(
            {"type": "contact", "object_id": contact.get("id")},
            channel=channel,
            blocks=blocks,
        )
