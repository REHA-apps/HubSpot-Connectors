# app/services/event_router.py
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any

from app.core.logging import CorrelationAdapter, get_logger
from app.core.models.events import NormalizedEvent
from app.services.channel_service import ChannelService

logger = get_logger("event.router")


class EventRouter:
    """Central event routing layer.
    Converts domain events into channel-agnostic NormalizedEvent objects
    and delegates delivery to ChannelService.
    """

    def __init__(self, corr_id: str) -> None:
        self.corr_id = corr_id
        self.log = CorrelationAdapter(logger, corr_id)
        self.channel_service = ChannelService(corr_id)

    # ---------------------------------------------------------
    # Contact updated
    # ---------------------------------------------------------
    async def route_contact_update(
        self,
        workspace_id: str,
        contact: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        event = NormalizedEvent(
            channel="hubspot",
            event_type="contact.updated",
            user_id=None,
            raw={
                "contact": contact,
                "timestamp": datetime.utcnow().isoformat(),
            },
        )

        self.log.info("Routing contact.updated event")

        return await self.channel_service.send_contact_update(
            workspace_id=workspace_id,
            event=event,
        )
