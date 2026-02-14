# app/services/event_router.py
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from app.core.logging import CorrelationAdapter, get_logger
from app.services.channel_service import ChannelService

logger = get_logger("event.router")


class EventRouter:
    """Normalized event routing across channels.

    Responsibilities:
    - Normalize inbound events (e.g. HubSpot webhooks)
    - Attach correlation IDs, timestamps, and source metadata
    - Delegate to ChannelService for AI + UI + outbound delivery
    """

    def __init__(self, corr_id: str) -> None:
        self.corr_id = corr_id
        self.log = CorrelationAdapter(logger, corr_id)
        self.channel_service = ChannelService(corr_id)

    # ---------------------------------------------------------
    # HubSpot contact updated → Slack
    # ---------------------------------------------------------
    async def route_contact_update(
        self,
        *,
        workspace_id: str,
        contact: Mapping[str, Any],
        channel: str,
    ) -> Mapping[str, Any] | None:
        event = {
            "type": "contact.updated",
            "object_id": contact.get("id"),
            "corr_id": self.corr_id,
            "timestamp": datetime.utcnow().isoformat(),
            "source": "hubspot.webhook",
        }

        self.log.info(
            "Routing HubSpot contact update id=%s to Slack channel=%s",
            contact.get("id"),
            channel,
        )

        # ChannelService handles:
        # - AI analysis
        # - Slack UI building
        # - SlackConnector resolution
        # - Slack message sending
        return await self.channel_service.send_slack_card(
            workspace_id=workspace_id,
            obj=contact,
            channel=channel,
        )

    # ---------------------------------------------------------
    # Generic HubSpot object routing (contact / lead / deal)
    # ---------------------------------------------------------
    async def route_hubspot_object_to_slack(
        self,
        *,
        workspace_id: str,
        obj: Mapping[str, Any],
        channel: str | None = None,
    ) -> Mapping[str, Any] | None:
        self.log.info(
            "Routing HubSpot object id=%s to Slack channel=%s",
            obj.get("id"),
            channel,
        )

        return await self.channel_service.send_slack_card(
            workspace_id=workspace_id,
            obj=obj,
            channel=channel,
        )
