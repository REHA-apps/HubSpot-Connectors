from __future__ import annotations

from collections.abc import Mapping
from time import time
from typing import Any, cast

from app.connectors.common.base import BaseChannel, BaseOAuthResult
from app.core.config import settings
from app.core.logging import CorrelationAdapter, get_logger
from app.core.models.channel import Identity, NormalizedEvent, OutboundMessage
from app.providers.slack.client import SlackClient
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

    def __init__(
        self,
        corr_id: str,
        bot_token: str | None = None,
        slack_client: SlackClient | None = None,
    ) -> None:
        self.corr_id = corr_id
        self.log = CorrelationAdapter(logger, corr_id)
        self.http_client = HTTPClient.get_client(corr_id=corr_id)
        self.bot_token = bot_token
        self.slack_client = slack_client

    def get_slack_client(self) -> SlackClient:
        """Lazily initialize the SlackClient wrapper."""
        if not self.slack_client:
            self.slack_client = SlackClient(
                corr_id=self.corr_id,
                bot_token=str(self.bot_token),
            )
        return self.slack_client

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
        client = self.slack_client or self.get_slack_client()

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
    async def open_view(
        self, trigger_id: str, view: dict[str, Any], bot_token: str | None = None
    ) -> Any:
        """Opens a Slack modal view."""
        client = self.slack_client
        if bot_token:
            client = SlackClient(corr_id=self.corr_id, bot_token=bot_token)
        elif not client:
            client = self.get_slack_client()

        return await client.views_open(trigger_id=trigger_id, view=view)

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

    async def get_user_by_email(self, email: str) -> str | None:
        """Resolves a Slack user ID by their email address."""
        try:
            resp = await self.get_slack_client().users_lookupByEmail(email=email)
            if resp and resp.get("ok") and "user" in resp:
                user_data = cast(dict[str, Any], resp["user"])
                return str(user_data.get("id"))
        except Exception as exc:
            self.log.error("Failed to lookup Slack user by email '%s': %s", email, exc)
        return None

    async def send_dm(
        self,
        user_id: str,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
    ) -> Mapping[str, Any] | None:
        """Sends a private DM to a Slack user."""
        self.log.info("SlackChannel.send_dm to user_id=%s", user_id)

        message = OutboundMessage(
            workspace_id="DM",  # Arbitrary for DMs
            destination=user_id,
            text=text,
            provider_metadata={"blocks": blocks},
        )
        return await self.send_message(message)

    async def get_thread_replies(
        self, channel_id: str, thread_ts: str
    ) -> list[dict[str, Any]]:
        """Fetches all replies in a Slack thread."""
        try:
            resp = await self.get_slack_client().conversations_replies(
                channel=channel_id,
                ts=thread_ts,
            )
            if resp.get("ok"):
                return cast(list[dict[str, Any]], resp.get("messages", []))
        except Exception as exc:
            self.log.error(
                "Failed to fetch thread replies for channel=%s ts=%s: %s",
                channel_id,
                thread_ts,
                exc,
            )
        return []

    async def send_via_response_url(
        self,
        response_url: str,
        text: str,
        blocks: list[dict[str, Any]] | None = None,
        replace_original: bool = False,
    ) -> bool:
        """Sends a response to a Slack slash command using the response_url webhook.

        This is highly reliable as it bypasses channel discovery/membership issues.
        """
        self.log.info(
            "SlackChannel.send_via_response_url using %s", response_url[:30] + "..."
        )

        payload = {
            "text": text,
            "replace_original": replace_original,
        }
        if blocks:
            payload["blocks"] = blocks

        try:
            resp = await self.http_client.post(response_url, json=payload)
            resp.raise_for_status()
            return True
        except Exception as exc:
            self.log.error("Failed to send to Slack response_url: %s", exc)
            return False
