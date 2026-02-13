from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol

from app.core.logging import CorrelationAdapter, get_logger
from app.services.channel_service import ChannelService

logger = get_logger("event.router")


class ChannelConnector(Protocol):
    async def send_event(
        self,
        event: Mapping[str, Any],
        *,
        channel: str | None = None,
        blocks: list[Mapping[str, Any]] | None = None,
    ) -> Mapping[str, Any] | None: ...


class EventRouter:
    """Normalized event routing across channels.

    Responsibilities:
    - Normalize inbound events (e.g. HubSpot webhooks)
    - Attach correlation IDs, timestamps, and source metadata
    - Delegate to ChannelService or connectors
    """

    def __init__(self, corr_id: str) -> None:
        self.corr_id = corr_id
        self.log = CorrelationAdapter(logger, corr_id)
        self.channel_service = ChannelService(corr_id)

    # ---------------------------------------------------------
    # HubSpot contact updated → channel event
    # ---------------------------------------------------------
    async def route_contact_update(
        self,
        *,
        connector: ChannelConnector,
        contact: Mapping[str, Any],
        channel: str | None = None,
    ) -> Mapping[str, Any] | None:
        """Generic routing for contact updates.

        Produces a normalized event and forwards it to the connector.
        """
        event = {
            "type": "contact.updated",
            "object_id": contact.get("id"),
            "contact_data": contact,
            "corr_id": self.corr_id,
            "timestamp": datetime.utcnow().isoformat(),
            "source": "hubspot.webhook",
        }

        self.log.info(
            "Routing contact update event object_id=%s to connector",
            contact.get("id"),
        )

        return await connector.send_event(
            event,
            channel=channel,
        )

    # ---------------------------------------------------------
    # Generic object routing (contact / lead / deal)
    # ---------------------------------------------------------
    async def route_hubspot_object_to_slack(
        self,
        *,
        workspace_id: str,
        obj: Mapping[str, Any],
        channel: str,
    ) -> Mapping[str, Any] | None:
        """High-level helper: take a HubSpot object and send it to Slack
        using ChannelService (AI + UI + connector).
        """
        self.log.info(
            "Routing HubSpot object id=%s to Slack channel=%s",
            obj.get("id"),
            channel,
        )

        # ChannelService handles AI, UI, and SlackConnector
        return await self.channel_service._send_slack_card(
            workspace_id=workspace_id,
            obj=obj,
            channel=channel,
        )
