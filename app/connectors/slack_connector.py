# app/connectors/slack_connector.py
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.connectors.base import Connector
from app.core.logging import CorrelationAdapter, get_logger
from app.core.models.channel import Identity, NormalizedEvent, OutboundMessage

logger = get_logger("slack.connector")


class SlackConnector(Connector):
    """Slack connector (normalization + outbound only).

    Responsibilities:
    - Normalize Slack events
    - Resolve Slack user identity (optional)
    - Send outbound Slack messages
    - Handle Slack install/uninstall

    Note:
    Routing, HubSpot queries, AI scoring, and Slack UI rendering
    are handled by CommandService + ChannelService.
    """

    # Channel metadata
    channel_name: str = "slack"
    supports_cards: bool = True
    supports_ephemeral: bool = True
    supports_threading: bool = True

    def __init__(
        self,
        *,
        slack_client,
        corr_id: str,
        default_channel: str,
    ) -> None:
        self.client = slack_client
        self.corr_id = corr_id
        self.default_channel = default_channel
        self.log = CorrelationAdapter(logger, corr_id)

    # ---------------------------------------------------------
    # Optional: validate Slack OAuth install payload
    # ---------------------------------------------------------
    def validate_install_payload(self, payload: Mapping[str, Any]) -> None:
        if "team" not in payload or "access_token" not in payload:
            self.log.error("Invalid Slack install payload")
            raise ValueError("Invalid Slack install payload")

    # ---------------------------------------------------------
    # Normalization
    # ---------------------------------------------------------
    async def normalize_event(
        self,
        workspace_id: str,
        raw_event: Mapping[str, Any],
    ) -> NormalizedEvent:

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
                id=str(user_id),
                source="slack",
            ),
            payload=dict(raw_event),
            timestamp=str(ts),
        )

    # ---------------------------------------------------------
    # Identity resolution (Slack → HubSpot)
    # ---------------------------------------------------------
    async def resolve_identity(
        self,
        event: NormalizedEvent,
    ) -> Identity | None:
        # Slack user → HubSpot identity mapping (optional)
        return None

    # ---------------------------------------------------------
    # Outbound communication
    # ---------------------------------------------------------
    async def send_message(
        self,
        message: OutboundMessage,
    ) -> Mapping[str, Any] | None:

        self.log.info("SlackConnector.send_message to channel=%s", message.channel)

        payload: dict[str, Any] = {}

        # Required
        if message.channel:
            payload["channel"] = message.channel

        # Slack requires either text or blocks
        if message.text:
            payload["text"] = message.text

        if message.blocks:
            payload["blocks"] = message.blocks

        if message.attachments:
            payload["attachments"] = message.attachments

        # Threading support
        if message.thread_ts and self.supports_threading:
            payload["thread_ts"] = message.thread_ts

        self.log.info("Sending to Slack channel=%s", payload.get("channel"))

        # Use SlackClient (your wrapper around BaseClient)
        return await self.client.chat_postMessage(
            channel=payload.get("channel"),
            text=payload.get("text"),
            blocks=payload.get("blocks"),
        )

    # ---------------------------------------------------------
    # Lifecycle
    # ---------------------------------------------------------
    async def install(self, payload: Mapping[str, Any]) -> None:
        self.log.info("Slack install event received (handled upstream)")

    async def uninstall(self, payload: Mapping[str, Any]) -> None:
        self.log.info("Slack uninstall event received (handled upstream)")