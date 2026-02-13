# app/connectors/base.py
from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from app.core.models.channel import (
    Identity,
    NormalizedEvent,
    OutboundMessage,
)


class Connector(ABC):
    """Base interface for all channel connectors (Slack, WhatsApp, etc.).

    Responsibilities:
    - Normalize inbound events into a common shape
    - Route events to the correct handler
    - Resolve channel user identity → HubSpot identity
    - Send outbound messages/cards
    - Handle install/uninstall flows
    """

    # -----------------------------
    # Inbound event handling
    # -----------------------------
    @abstractmethod
    async def normalize_event(
        self,
        raw_event: Mapping[str, Any],
    ) -> NormalizedEvent:
        """Convert raw platform event into a normalized internal event."""
        raise NotImplementedError

    @abstractmethod
    async def handle_event(
        self,
        event: NormalizedEvent,
    ) -> Mapping[str, Any] | None:
        """Process a normalized inbound event."""
        raise NotImplementedError

    # -----------------------------
    # Identity resolution
    # -----------------------------
    @abstractmethod
    async def resolve_identity(
        self,
        event: NormalizedEvent,
    ) -> Identity | None:
        """Resolve channel user → HubSpot identity."""
        raise NotImplementedError

    # -----------------------------
    # Outbound communication
    # -----------------------------
    @abstractmethod
    async def send_message(
        self,
        message: OutboundMessage,
    ) -> Mapping[str, Any] | None:
        """Send a message/card to the channel."""
        raise NotImplementedError

    # -----------------------------
    # Installation lifecycle
    # -----------------------------
    @abstractmethod
    async def install(self, payload: Mapping[str, Any]) -> None:
        """Handle OAuth installation."""
        raise NotImplementedError

    @abstractmethod
    async def uninstall(self, payload: Mapping[str, Any]) -> None:
        """Handle uninstall/deauthorization."""
        raise NotImplementedError
