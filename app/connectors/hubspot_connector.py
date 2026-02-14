# app/connectors/hubspot_connector.py
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.connectors.base import Connector
from app.core.logging import CorrelationAdapter, get_logger
from app.core.models.channel import Identity, NormalizedEvent, OutboundMessage

logger = get_logger("hubspot.connector")


class HubSpotConnector(Connector):
    """HubSpot connector (normalization + outbound only).

    Responsibilities:
    - Normalize HubSpot webhook events
    - Resolve identity (rare for HubSpot)
    - Send outbound HubSpot messages (optional)
    - Handle install/uninstall

    Note:
    Routing, AI, Slack notifications, and workspace resolution
    are handled by EventRouter + ChannelService.

    """

    def __init__(self, corr_id: str) -> None:
        self.corr_id = corr_id
        self.log = CorrelationAdapter(logger, corr_id)

    # ---------------------------------------------------------
    # Normalization
    # ---------------------------------------------------------
    async def normalize_event(
        self,
        workspace_id: str,
        raw_event: Mapping[str, Any],
    ) -> NormalizedEvent:
        return NormalizedEvent(
            workspace_id=workspace_id,
            source="hubspot",
            event_type=raw_event.get("subscriptionType", "unknown"),
            identity=Identity(
                id=str(raw_event.get("objectId", "")),
                email=raw_event.get("email"),
                source="hubspot",
            ),
            payload=dict(raw_event),
            timestamp=str(raw_event.get("occurredAt")),
        )

    # ---------------------------------------------------------
    # Identity resolution (HubSpot rarely provides user identity)
    # ---------------------------------------------------------
    async def resolve_identity(
        self,
        event: NormalizedEvent,
    ) -> Identity | None:
        return None

    # ---------------------------------------------------------
    # Outbound communication (HubSpot rarely receives messages)
    # ---------------------------------------------------------
    async def send_message(
        self,
        message: OutboundMessage,
    ) -> Mapping[str, Any] | None:
        self.log.info("HubSpotConnector.send_message called (noop)")
        return None

    # ---------------------------------------------------------
    # Installation lifecycle
    # ---------------------------------------------------------
    async def install(self, payload: Mapping[str, Any]) -> None:
        self.log.info("HubSpot install event received (handled upstream)")

    async def uninstall(self, payload: Mapping[str, Any]) -> None:
        self.log.info("HubSpot uninstall event received (handled upstream)")
