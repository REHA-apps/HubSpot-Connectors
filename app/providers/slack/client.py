from __future__ import annotations

import time
from collections.abc import Awaitable, Callable
from typing import Any

from slack_sdk.web.async_client import AsyncWebClient

from app.core.config import settings
from app.core.logging import CorrelationAdapter, get_logger

logger = get_logger("slack.client")


class SlackClient:
    """Description:
        Wrapper around Slack's AsyncWebClient that handles automatic token rotation.

    Rules Applied:
        - Checks for token expiration before making requests.
        - Refreshes tokens using the SlackPlatform if needed.
        - Notifies the service layer of token updates for persistence.
    """

    def __init__(
        self,
        corr_id: str,
        bot_token: str,
        refresh_token: str | None = None,
        expires_at: int | None = None,
    ) -> None:
        self.corr_id = corr_id
        self.bot_token = bot_token
        self.refresh_token = refresh_token
        self.expires_at = expires_at
        self.log = CorrelationAdapter(logger, corr_id)

        # Callback: (new_token, new_refresh, new_expires) -> None
        self.on_token_refresh: (
            Callable[[str, str | None, int | None], Awaitable[None]]
            | Callable[[str, str | None, int | None], None]
            | None
        ) = None

        self._client = AsyncWebClient(token=bot_token)

    async def _ensure_fresh_token(self) -> None:
        """Refreshes the token if it is expired or about to expire."""
        if not self.refresh_token or not self.expires_at:
            return

        # Refresh 5 minutes before expiration
        now = int(time.time())
        if now + 300 < self.expires_at:
            return

        self.log.info("Slack token expiring soon; attempting refresh")

        # We need a channel instance to do the exchange
        # Note: app.channels will eventually become app.connectors
        from app.connectors.hubspot_slack.slack_channel import SlackChannel

        platform = SlackChannel(corr_id=self.corr_id)

        # Slack uses the same v2.access for refresh, but with grant_type=refresh_token
        data = {
            "client_id": settings.SLACK_CLIENT_ID,
            "client_secret": settings.SLACK_CLIENT_SECRET.get_secret_value(),
            "grant_type": "refresh_token",
            "refresh_token": self.refresh_token,
        }

        # Use platform's http client
        resp = await platform.http_client.post(
            "https://slack.com/api/oauth.v2.access", data=data
        )
        resp.raise_for_status()
        payload = resp.json()

        if not payload.get("ok"):
            error = payload.get("error", "unknown_refresh_error")
            self.log.error("Slack token refresh failed: %s", error)
            raise RuntimeError(f"Slack token refresh failed: {error}")

        # Update local state
        self.bot_token = payload["access_token"]
        self.refresh_token = payload.get("refresh_token")

        expires_in = payload.get("expires_in")
        self.expires_at = int(time.time()) + expires_in if expires_in else None

        # Update client
        self._client.token = self.bot_token

        self.log.info("Slack token refreshed successfully")

        # Notify
        if self.on_token_refresh:
            res = self.on_token_refresh(
                self.bot_token, self.refresh_token, self.expires_at
            )
            if isinstance(res, Awaitable):
                await res

    async def chat_postMessage(self, **kwargs) -> Any:
        await self._ensure_fresh_token()
        channel = kwargs.get("channel")
        token_prefix = self.bot_token[:15] if self.bot_token else "None"
        self.log.info(
            "Attempting Slack chat.postMessage channel=%s token_prefix=%s",
            channel,
            token_prefix,
        )
        return await self._client.chat_postMessage(**kwargs)

    async def users_info(self, **kwargs) -> Any:
        await self._ensure_fresh_token()
        return await self._client.users_info(**kwargs)

    # Proxy other method as needed, or use a __getattr__ if appropriate
    def __getattr__(self, name: str) -> Any:
        # For simplicity in this demo, we wrap common ones or return the client method
        # Real implementation should probably ensure refresh before ANY call.
        attr = getattr(self._client, name)
        if callable(attr):

            async def wrapper(*args, **kwargs):
                await self._ensure_fresh_token()
                method: Any = attr
                return await method(*args, **kwargs)

            return wrapper
        return attr
