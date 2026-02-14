# app/clients/slack_client.py
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.clients.base_client import BaseClient
from app.core.logging import CorrelationAdapter, get_logger

logger = get_logger("slack.client")


class SlackClient(BaseClient):
    """Slack HTTP client.

    Responsibilities:
    - Send messages to Slack
    - Validate Slack API responses (`ok: false`)
    - Handle rate limits (429)
    - No workspace logic
    """

    def __init__(self, token: str, *, corr_id: str | None = None) -> None:
        self.token = token

        super().__init__(
            base_url="https://slack.com/api",
            headers=self._headers(token),
            corr_id=corr_id,
        )

        self.log = CorrelationAdapter(logger, corr_id or "slack_unknown")

    # ---------------------------------------------------------
    # Core Slack request wrapper
    # ---------------------------------------------------------
    async def slack_request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
    ) -> Mapping[str, Any]:
        """Slack returns 200 OK even when failing, so we validate `ok`."""
        resp = await self.request(method, path, params=params, json=json)

        if not isinstance(resp, Mapping):
            self.log.error("Slack returned non-JSON response: %s", resp)
            raise RuntimeError("Invalid Slack response")

        if not resp.get("ok", False):
            error = resp.get("error", "unknown_error")
            self.log.error("Slack API error: %s", error)
            raise RuntimeError(f"Slack API error: {error}")

        return resp

    # ---------------------------------------------------------
    # Headers
    # ---------------------------------------------------------
    def _headers(self, token: str) -> Mapping[str, str]:
        return {
            "Authorization": f"Bearer {token}",
            "Content-Type": "application/json; charset=utf-8",
        }

    # ---------------------------------------------------------
    # Messaging
    # ---------------------------------------------------------
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

        return await self.slack_request(
            "POST",
            "chat.postMessage",
            json=payload,
        )

    async def send_ephemeral(
        self,
        channel: str,
        user: str,
        text: str,
        *,
        blocks: list[Mapping[str, Any]] | None = None,
    ) -> Mapping[str, Any]:
        """Send an ephemeral message visible only to a specific user."""
        payload: dict[str, Any] = {
            "channel": channel,
            "user": user,
            "text": text,
        }

        if blocks:
            payload["blocks"] = blocks

        self.log.info("Sending Slack ephemeral message to user=%s", user)

        return await self.slack_request(
            "POST",
            "chat.postEphemeral",
            json=payload,
        )

    # ---------------------------------------------------------
    # Response URL (for slash commands)
    # ---------------------------------------------------------
    async def send_response_url(
        self,
        response_url: str,
        payload: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        """Send a delayed response to a Slack slash command."""
        self.log.info("Sending Slack response_url message")

        client = self.get_client()

        resp = await client.post(
            response_url,
            json=payload,
            headers={"Content-Type": "application/json"},
        )

        try:
            data = resp.json()
        except ValueError:
            self.log.error("Invalid JSON from response_url: %s", resp.text)
            raise

        if not data.get("ok", True):
            self.log.error("Slack response_url error: %s", data.get("error"))
            raise RuntimeError(f"Slack response_url error: {data.get('error')}")

        return data

    # ---------------------------------------------------------
    # Users
    # ---------------------------------------------------------
    async def get_user_info(self, user_id: str) -> Mapping[str, Any]:
        self.log.info("Fetching Slack user info for user_id=%s", user_id)

        return await self.slack_request(
            "GET",
            "users.info",
            params={"user": user_id},
        )

    # ---------------------------------------------------------
    # Channels
    # ---------------------------------------------------------
    async def list_channels(self) -> Mapping[str, Any]:
        self.log.info("Listing Slack channels")

        return await self.slack_request("GET", "conversations.list")
