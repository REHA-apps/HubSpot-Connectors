from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

from app.core.models.channel import (
    Identity,
    NormalizedEvent,
    OutboundMessage,
)


class BaseOAuthResult(BaseModel):
    """Standardized result for OAuth exchanges."""

    model_config = ConfigDict(frozen=True, extra="ignore")
    access_token: str
    refresh_token: str | None = None
    expires_at: int | None = None
    raw: dict[str, Any] = Field(default_factory=dict)


class BaseChannel(ABC):
    """Description:
        Unified abstract base class for all communication channels (Slack, WhatsApp).

    Rules Applied:
        - Combines infrastructure (OAuth) with domain logic (Normalization, Messaging).
        - Every channel must implement transport, normalization, and lifecycle hooks.
    """

    channel_name: str = "unknown"
    supports_cards: bool = False
    supports_ephemeral: bool = False
    supports_threading: bool = False

    # -----------------------------
    # Authentication & Transport
    # -----------------------------
    @abstractmethod
    async def exchange_token(
        self, code: str, redirect_uri: str | None = None
    ) -> BaseOAuthResult:
        """Handles the OAuth code-to-token exchange for this channel."""
        raise NotImplementedError

    # -----------------------------
    # Inbound Event Normalization
    # -----------------------------
    @abstractmethod
    async def normalize_event(
        self,
        workspace_id: str,
        raw_event: Mapping[str, Any],
    ) -> NormalizedEvent:
        """Converts raw provider webhooks into a standard NormalizedEvent."""
        raise NotImplementedError

    # -----------------------------
    # Identity Resolution
    # -----------------------------
    @abstractmethod
    async def resolve_identity(
        self,
        event: NormalizedEvent,
    ) -> Identity | None:
        """Maps a channel-specific user ID to a CRM identity."""
        raise NotImplementedError

    # -----------------------------
    # Outbound Communication
    # -----------------------------
    @abstractmethod
    async def send_message(
        self,
        message: OutboundMessage,
        **kwargs: Any,
    ) -> Mapping[str, Any] | None:
        """Sends an outbound message or notification to the channel."""
        raise NotImplementedError

    # -----------------------------
    # Lifecycle Hooks
    # -----------------------------
    @abstractmethod
    async def install(self, payload: Mapping[str, Any]) -> None:
        """Hook called during the installation/OAuth flow."""
        raise NotImplementedError

    @abstractmethod
    async def uninstall(self, payload: Mapping[str, Any]) -> None:
        """Hook called during the uninstallation/deauthorization flow."""
        raise NotImplementedError

    async def validate_install_payload(self, payload: Mapping[str, Any]) -> None:
        """Optional hook to validate installation data."""
        return
