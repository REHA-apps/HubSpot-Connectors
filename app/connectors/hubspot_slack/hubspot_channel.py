from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.connectors.common.base import BaseChannel, BaseOAuthResult
from app.core.config import settings
from app.core.logging import get_logger
from app.core.models.channel import Identity, NormalizedEvent, OutboundMessage
from app.utils.helpers import HTTPClient

logger = get_logger("hubspot.channel")


class HubSpotOAuthResult(BaseOAuthResult):
    """HubSpot-specific OAuth metadata."""

    portal_id: str


# Map HubSpot subscription types -> internal event types
EVENT_TYPE_MAP: dict[str, str] = {
    "contact.creation": "contact_created",
    "contact.propertyChange": "contact_updated",
    "deal.creation": "deal_created",
    "deal.propertyChange": "deal_updated",
    "ticket.creation": "ticket_created",
    "ticket.propertyChange": "ticket_updated",
    "task.creation": "task_created",
    "task.propertyChange": "task_updated",
    "meeting.creation": "meeting_created",
    "meeting.propertyChange": "meeting_updated",
    "company.creation": "company_created",
    "company.propertyChange": "company_updated",
}


class HubSpotChannel(BaseChannel):
    """Description:
    Unified HubSpot channel implementation.
    Handles both infrastructure (OAuth) and domain logic (Normalization).
    """

    channel_name: str = "hubspot"
    supports_cards: bool = False
    supports_ephemeral: bool = False
    supports_threading: bool = False

    def __init__(self, corr_id: str) -> None:
        self.corr_id = corr_id
        self.http_client = HTTPClient.get_client(corr_id=corr_id)

    # -----------------------------
    # Authentication & Transport
    # -----------------------------
    async def exchange_token(
        self, code: str, redirect_uri: str | None = None
    ) -> HubSpotOAuthResult:
        """Exchanges a HubSpot authorization code for access and refresh tokens."""
        logger.info("Exchanging HubSpot OAuth code")

        data = {
            "grant_type": "authorization_code",
            "client_id": settings.HUBSPOT_CLIENT_ID,
            "client_secret": settings.HUBSPOT_CLIENT_SECRET.get_secret_value(),
            "redirect_uri": redirect_uri
            or settings.HUBSPOT_REDIRECT_URI.unicode_string(),
            "code": code,
        }

        resp = await self.http_client.post(
            "https://api.hubapi.com/oauth/v1/token", data=data
        )
        resp.raise_for_status()
        payload = resp.json()

        if "access_token" not in payload:
            logger.error("Invalid HubSpot OAuth response: %s", payload)
            raise RuntimeError("HubSpot OAuth response missing access_token")

        logger.info("HubSpot OAuth token exchange successful")

        return HubSpotOAuthResult(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token"),
            portal_id=str(payload.get("hub_id", "")),
            raw=payload,
        )

    # -----------------------------
    # Inbound Event Normalization
    # -----------------------------
    async def normalize_event(
        self, workspace_id: str, raw_event: Mapping[str, Any]
    ) -> NormalizedEvent:
        """Converts HubSpot webhook payloads to standard internal events."""
        subscription_type = raw_event.get("subscriptionType", "unknown")
        event_type = EVENT_TYPE_MAP.get(subscription_type, "unknown")

        identity = self._extract_identity(raw_event)

        return NormalizedEvent(
            workspace_id=workspace_id,
            source="hubspot",
            event_type=event_type,
            identity=identity,
            payload=dict(raw_event),
            timestamp=str(raw_event.get("occurredAt", "")),
        )

    def _extract_identity(self, raw_event: Mapping[str, Any]) -> Identity:
        """Helper to extract object identity from HubSpot event data."""
        return Identity(
            external_id=str(raw_event.get("objectId", "")),
            provider="hubspot",
            email=raw_event.get("email"),
            source="hubspot",
        )

    # -----------------------------
    # Identity Resolution
    # -----------------------------
    async def resolve_identity(self, event: NormalizedEvent) -> Identity | None:
        """Resolves a HubSpot identity (currently returns embedded identity)."""
        return event.identity

    # -----------------------------
    # Outbound Communication
    # -----------------------------
    async def send_message(
        self,
        message: OutboundMessage,
        **kwargs: Any,
    ) -> Mapping[str, Any] | None:
        """HubSpot is not a chat channel; outbound handled via dedicated services."""
        logger.info("HubSpotChannel.send_message called (noop)")
        return None

    # -----------------------------
    # Lifecycle Hooks
    # -----------------------------
    async def install(self, payload: Mapping[str, Any]) -> None:
        """Post-install hook for HubSpot integration."""
        logger.info("HubSpot install event received (handled upstream)")

    async def uninstall(self, payload: Mapping[str, Any]) -> None:
        """Post-uninstall hook for HubSpot integration."""
        logger.info("HubSpot uninstall event received (handled upstream)")

    async def validate_install_payload(self, payload: Mapping[str, Any]) -> None:
        """Validates HubSpot installation metadata."""
        if "hub_id" not in payload and "portalId" not in payload:
            logger.error("Invalid HubSpot install payload")
            raise ValueError("Invalid HubSpot install payload")
