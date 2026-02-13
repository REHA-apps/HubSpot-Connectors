# app/services/routing_service.py
from __future__ import annotations

from collections.abc import Mapping
from datetime import datetime
from typing import Any, Protocol

from app.core.logging import CorrelationAdapter, get_logger

logger = get_logger("routing")


class ChannelConnector(Protocol):
    async def send_event(
        self,
        event: Mapping[str, Any],
        *,
        channel: str | None = None,
        blocks: list[Mapping[str, Any]] | None = None,
    ) -> Mapping[str, Any] | None: ...


async def route_contact_update(
    connector: ChannelConnector,
    contact: Mapping[str, Any],
    *,
    corr_id: str,
    channel: str | None = None,
) -> Mapping[str, Any] | None:
    """Generic routing service for contact updates.
    Adds correlation ID, timestamp, and consistent event structure.
    """
    log = CorrelationAdapter(logger, corr_id)

    event = {
        "type": "contact.updated",
        "object_id": contact.get("id"),
        "contact_data": contact,
        "corr_id": corr_id,
        "timestamp": datetime.utcnow().isoformat(),
        "source": "hubspot.webhook",
    }

    log.info("Routing contact update event to connector")

    return await connector.send_event(
        event,
        channel=channel,
    )
