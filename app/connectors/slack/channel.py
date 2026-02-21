from __future__ import annotations

from collections.abc import Mapping
from time import time
from typing import Any, cast

from slack_sdk.web.async_client import AsyncWebClient

from app.connectors.common.base import BaseChannel, BaseOAuthResult
from app.core.config import settings
from app.core.logging import CorrelationAdapter, get_logger
from app.core.models.channel import Identity, NormalizedEvent, OutboundMessage
from app.utils.helpers import HTTPClient

logger = get_logger("slack.channel")


class SlackOAuthResult(BaseOAuthResult):
    """Slack-specific OAuth metadata."""

    bot_user_id: str
    team_id: str


class SlackChannel(BaseChannel):
    """Description:
    Unified Slack channel implementation.
    Handles both infrastructure (OAuth) and domain logic (Normalization, Messaging).
    """

    channel_name: str = "slack"
    supports_cards: bool = True
    supports_ephemeral: bool = True
    supports_threading: bool = True

    def __init__(self, corr_id: str, bot_token: str | None = None) -> None:
        self.corr_id = corr_id
        self.log = CorrelationAdapter(logger, corr_id)
        self.http_client = HTTPClient.get_client(corr_id=corr_id)
        self.bot_token = bot_token
        self._async_client: AsyncWebClient | None = None

    def get_slack_client(self) -> AsyncWebClient:
        """Lazily initialize the Slack AsyncWebClient."""
        if not self._async_client:
            self._async_client = AsyncWebClient(token=self.bot_token)
        return self._async_client

    # -----------------------------
    # Authentication & Transport
    # -----------------------------
    async def exchange_token(
        self, code: str, redirect_uri: str | None = None
    ) -> SlackOAuthResult:
        """Handles Slack-specific OAuth token exchange."""
        self.log.info("Exchanging Slack OAuth code")

        data = {
            "client_id": settings.SLACK_CLIENT_ID,
            "client_secret": settings.SLACK_CLIENT_SECRET.get_secret_value(),
            "code": code,
            "redirect_uri": redirect_uri
            or settings.SLACK_REDIRECT_URI.unicode_string(),
        }

        resp = await self.http_client.post(
            "https://slack.com/api/oauth.v2.access", data=data
        )
        resp.raise_for_status()
        payload = resp.json()

        if not payload.get("ok"):
            error = payload.get("error", "unknown_error")
            self.log.error("Slack OAuth failed: %s", error)
            raise RuntimeError(f"Slack OAuth failed: {error}")

        expires_in = payload.get("expires_in")
        expires_at = int(time()) + expires_in if expires_in else None

        return SlackOAuthResult(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token"),
            expires_at=expires_at,
            bot_user_id=payload["bot_user_id"],
            team_id=payload["team"]["id"],
            raw=payload,
        )

    # -----------------------------
    # Inbound Event Normalization
    # -----------------------------
    async def normalize_event(
        self, workspace_id: str, raw_event: Mapping[str, Any]
    ) -> NormalizedEvent:
        """Maps raw Slack webhook data into a standardized NormalizedEvent."""
        user_id = (
            raw_event.get("user")
            or raw_event.get("actor_id")
            or raw_event.get("event", {}).get("user")
            or "unknown"
        )

        ts = (
            raw_event.get("event_ts")
            or raw_event.get("ts")
            or raw_event.get("event", {}).get("ts")
        )

        return NormalizedEvent(
            workspace_id=workspace_id,
            source="slack",
            event_type=raw_event.get("type", "unknown"),
            identity=Identity(
                external_id=str(user_id),
                provider="slack",
                source="slack",
            ),
            payload=dict(raw_event),
            timestamp=str(ts),
        )

    # -----------------------------
    # Identity Resolution
    # -----------------------------
    async def resolve_identity(self, event: NormalizedEvent) -> Identity | None:
        """Slack identity resolution (currently logic is handled upstream)."""
        return None

    # -----------------------------
    # Outbound Communication
    # -----------------------------
    async def send_message(
        self,
        message: OutboundMessage,
        **kwargs: Any,
    ) -> Mapping[str, Any] | None:
        """Sends a message to Slack using chat.postMessage."""
        self.log.info(
            "SlackChannel.send_message to destination=%s", message.destination
        )

        # Use provided bot_token or fallback to kwargs
        token = self.bot_token or kwargs.get("bot_token")
        if not token:
            self.log.error("No bot token provided for Slack message")
            return None

        client = AsyncWebClient(token=token)

        # Slack-specific validation
        destination = message.destination
        if not destination:
            self.log.error("OutboundMessage missing destination")
            return None

        if not (
            destination
            and len(destination) >= 9  # noqa: PLR2004
            and destination[0] in ("C", "G", "D", "U")
            and destination[1:].isalnum()
            and not any(c.islower() for c in destination)
        ):
            self.log.error(
                "Invalid Slack channel/destination ID format: %s", destination
            )
            return None

        fallback_text = message.text or "New CRM update"

        # Extract Slack-specific fields from provider_metadata
        blocks = message.provider_metadata.get("blocks")
        thread_ts = message.provider_metadata.get("thread_ts")
        # user = message.provider_metadata.get("user")  # For ephemeral messages

        resp = await client.chat_postMessage(
            channel=destination,
            text=fallback_text,
            blocks=blocks,
            thread_ts=thread_ts,
            **kwargs,
        )
        return cast(dict[str, Any], resp.data) if resp and resp.data else None

    # -----------------------------
    # Lifecycle Hooks
    # -----------------------------
    async def install(self, payload: Mapping[str, Any]) -> None:
        """Post-install hook for Slack integration."""
        self.log.info("Slack install event received (handled upstream)")

    async def uninstall(self, payload: Mapping[str, Any]) -> None:
        """Post-uninstall hook for Slack integration."""
        self.log.info("Slack uninstall event received (handled upstream)")

    async def validate_install_payload(self, payload: Mapping[str, Any]) -> None:
        """Validates the Slack OAuth installation payload."""
        if "team" not in payload or "access_token" not in payload:
            self.log.error("Invalid Slack install payload")
            raise ValueError("Invalid Slack install payload")

    # -----------------------------
    # Slack-Specific Methods
    # -----------------------------
    async def open_view(self, trigger_id: str, view: dict[str, Any]) -> Any:
        """Opens a Slack modal view."""
        return await self.get_slack_client().views_open(
            trigger_id=trigger_id, view=view
        )

    async def chat_unfurl(
        self,
        channel: str,
        ts: str,
        unfurls: dict[str, dict[str, Any]],
    ) -> Any:
        """Provides rich previews for shared links via chat.unfurl."""
        return await self.get_slack_client().chat_unfurl(
            channel=channel, ts=ts, unfurls=unfurls
        )

    async def resolve_channel_name(self, name: str) -> str | None:
        """Resolves a channel name (e.g., '#general' or 'general') to a channel ID.

        This uses conversations.list which requires 'channels:read'
        and 'groups:read' scopes.
        """
        clean_name = name.lstrip("#").lower()
        client = self.get_slack_client()

        self.log.info("Attempting to resolve Slack channel name: %s", clean_name)

        try:
            # Types include public and private channels
            types = "public_channel,private_channel"

            cursor = None
            while True:
                resp = await client.conversations_list(
                    types=types, cursor=cursor, limit=1000, exclude_archived=True
                )

                if not resp.get("ok"):
                    self.log.error(
                        "Slack conversations.list failed: %s", resp.get("error")
                    )
                    break

                channels = resp.get("channels", [])
                for channel in channels:
                    if channel.get("name") == clean_name:
                        channel_id = str(channel.get("id"))
                        self.log.info("Resolved %s to %s", name, channel_id)
                        return channel_id

                cursor = resp.get("response_metadata", {}).get("next_cursor")
                if not cursor:
                    break

        except Exception as exc:
            self.log.error("Failed to resolve Slack channel name '%s': %s", name, exc)

        self.log.warning("Could not resolve Slack channel name: %s", name)
        return None

    async def apps_uninstall(self) -> bool:
        """Description:
        Uninstalls the app from the workspace using the current bot token.

        Returns:
            bool: True if successful, False otherwise.

        """
        if not self.bot_token:
            self.log.error("Cannot uninstall: No bot token provided")
            return False

        try:
            resp = await self.get_slack_client().apps_uninstall(
                client_id=settings.SLACK_CLIENT_ID,
                client_secret=settings.SLACK_CLIENT_SECRET.get_secret_value(),
            )
            if not resp.get("ok"):
                self.log.error("Slack apps.uninstall failed: %s", resp.get("error"))
                return False
            self.log.info("App successfully uninstalled from Slack workspace")
            return True
        except Exception as exc:
            self.log.error("Slack apps.uninstall exception: %s", exc)
            return False
