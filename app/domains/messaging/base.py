from __future__ import annotations

from abc import ABC, abstractmethod
from collections.abc import Mapping
from typing import Any


class MessagingService(ABC):
    """Abstract base class for all messaging services (Slack, WhatsApp, Teams).

    Ensures a consistent interface for sending basic messages and rich CRM
    entity notifications across different platforms.
    """

    @abstractmethod
    async def send_message(
        self,
        *,
        workspace_id: str,
        channel: str | None,
        text: str | None = None,
        blocks: list[dict[str, Any]] | None = None,
        metadata: Mapping[str, Any] | None = None,
        thread_ts: str | None = None,
    ) -> Mapping[str, Any] | None:
        """Sends a generic message to the specified destination."""
        pass

    @abstractmethod
    async def send_card(
        self,
        *,
        workspace_id: str,
        obj: Mapping[str, Any],
        channel: str | None = None,
        analysis: Any = None,
        is_pro: bool = False,
        thread_ts: str | None = None,
    ) -> str | None:
        """Sends a rich CRM object card to the specified destination."""
        pass

    @abstractmethod
    async def send_ai_insights(
        self,
        *,
        workspace_id: str,
        channel: str | None,
        user_email: str | None = None,
        analysis: Any,
    ) -> None:
        """Sends AI insights/recap to the specified destination or user DM."""
        pass

    @abstractmethod
    async def send_dm(
        self,
        *,
        user_id: str | None = None,
        user_email: str | None = None,
        text: str,
    ) -> bool:
        """Sends a direct message to a user by ID or email."""
        pass
