# app/connectors/hubspot_connector.py
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.connectors.base import Connector
from app.core.logging import CorrelationAdapter, get_logger
from app.core.models.channel import Identity, NormalizedEvent, OutboundMessage

logger = get_logger("hubspot.connector")


# Optional: map HubSpot subscription types → internal event types
EVENT_TYPE_MAP: dict[str, str] = {
    "contact.creation": "contact_created",
    "contact.propertyChange": "contact_updated",
    "deal.creation": "deal_created",
    "deal.propertyChange": "deal_updated",
    # Fallback: anything unknown will be "unknown"
}


class HubSpotConnector(Connector):
    """HubSpot connector (normalization + outbound only).

    Responsibilities:
    - Normalize HubSpot webhook events
    - Resolve identity (rare for HubSpot)
    - Send outbound HubSpot messages (optional/no-op)
    - Handle install/uninstall

    Note:
    Routing, AI, Slack notifications, and workspace resolution
    are handled by EventRouter + ChannelService.
    """

    # Channel metadata
    channel_name: str = "hubspot"
    supports_cards: bool = False
    supports_ephemeral: bool = False
    supports_threading: bool = False

    def __init__(self, corr_id: str) -> None:
        self.corr_id = corr_id
        self.log = CorrelationAdapter(logger, corr_id)

    # ---------------------------------------------------------
    # Optional: install payload validation
    # ---------------------------------------------------------
    def validate_install_payload(self, payload: Mapping[str, Any]) -> None:
        """Validate HubSpot OAuth installation payload (optional)."""
        # You can tighten this as needed
        if "hub_id" not in payload and "portalId" not in payload:
            self.log.error("Invalid HubSpot install payload: missing hub_id/portalId")
            raise ValueError("Invalid HubSpot install payload")

    # ---------------------------------------------------------
    # Normalization
    # ---------------------------------------------------------
    async def normalize_event(
        self,
        workspace_id: str,
        raw_event: Mapping[str, Any],
    ) -> NormalizedEvent:
        subscription_type = raw_event.get("subscriptionType", "unknown")
        event_type = EVENT_TYPE_MAP.get(subscription_type, "unknown")

        identity = self._extract_identity(raw_event)

        return NormalizedEvent(
            workspace_id=workspace_id,
            source="hubspot",
            event_type=event_type,
            identity=identity,
            payload=dict(raw_event),
            timestamp=str(raw_event.get("occurredAt")),
        )

    def _extract_identity(self, raw_event: Mapping[str, Any]) -> Identity:
        """Extract identity from HubSpot webhook event."""
        return Identity(
            id=str(raw_event.get("objectId", "")),
            email=raw_event.get("email"),
            source="hubspot",
        )

    # ---------------------------------------------------------
    # Identity resolution (HubSpot rarely provides user identity)
    # ---------------------------------------------------------
    async def resolve_identity(
        self,
        event: NormalizedEvent,
    ) -> Identity | None:
        # Typically, HubSpot webhooks already carry the object identity.
        # If you ever need to enrich this (e.g., fetch contact by ID),
        # that should be done in a HubSpotService, not here.
        return event.identity

    # ---------------------------------------------------------
    # Outbound communication (HubSpot rarely receives messages)
    # ---------------------------------------------------------
    async def send_message(
        self,
        message: OutboundMessage,
    ) -> Mapping[str, Any] | None:
        # HubSpot is not a chat channel; outbound is usually handled
        # via HubSpot APIs in a dedicated service, not via this connector.
        self.log.info("HubSpotConnector.send_message called (noop)")
        return None

    # ---------------------------------------------------------
    # Installation lifecycle
    # ---------------------------------------------------------
    async def install(self, payload: Mapping[str, Any]) -> None:
        # Actual token handling + workspace linking is done upstream
        # (IntegrationService / HubSpotService / OAuth router).
        self.log.info("HubSpot install event received (handled upstream)")

    async def uninstall(self, payload: Mapping[str, Any]) -> None:
        self.log.info("HubSpot uninstall event received (handled upstream)")