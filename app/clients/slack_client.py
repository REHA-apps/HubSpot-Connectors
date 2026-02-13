# app/clients/slack_client.py
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.clients.base_client import BaseClient
from app.core.logging import CorrelationAdapter, get_logger

logger = get_logger("slack.client")


class SlackClient(BaseClient):
    """Slack HTTP client with:
    - shared httpx client (via BaseClient)
    - correlation ID logging
    - Python 3.12 typing
    - Pyright-clean
    """

    def __init__(self, token: str, *, corr_id: str | None = None) -> None:
        self.token = token

        super().__init__(
            base_url="https://slack.com/api",
            headers={
                "Authorization": f"Bearer {token}",
                "Content-Type": "application/json; charset=utf-8",
            },
            corr_id=corr_id,
        )

        self.log = CorrelationAdapter(logger, corr_id or "slack_unknown")

    # Messaging
    async def send_message(
        self,
        channel: str,
        text: str,
        *,
        blocks: list[Mapping[str, Any]] | None = None,
    ) -> Mapping[str, Any]:
        payload: dict[str, Any] = {"channel": channel, "text": text}

        if blocks:
            payload["blocks"] = blocks

        self.log.info("Sending Slack message to channel=%s", channel)

        return await self.post(
            "chat.postMessage",
            json=payload,
        )

    # Users
    async def get_user_info(self, user_id: str) -> Mapping[str, Any]:
        self.log.info("Fetching Slack user info for user_id=%s", user_id)

        return await self.get(
            "users.info",
            params={"user": user_id},
        )

    # Channels
    async def list_channels(self) -> Mapping[str, Any]:
        self.log.info("Listing Slack channels")

        return await self.get("conversations.list")
