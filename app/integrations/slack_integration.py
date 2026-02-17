# app/integrations/slack_integration.py
from __future__ import annotations

from slack_sdk.web.async_client import AsyncWebClient
from pydantic import SecretStr


class SlackIntegration:
    """
    Lightweight wrapper around Slack's AsyncWebClient.

    Responsibilities:
    - Hold Slack bot token + default channel
    - Build typed Slack client instances
    - Produce SlackConnector instances with correlation IDs
    """

    def __init__(
        self,
        *,
        slack_bot_token: SecretStr,
        default_channel: str,
    ) -> None:
        self.slack_bot_token = slack_bot_token
        self.default_channel = default_channel

    # -----------------------------------------------------
    # Slack client
    # -----------------------------------------------------
    def build_client(self) -> AsyncWebClient:
        """Return a fresh AsyncWebClient instance."""
        return AsyncWebClient(token=self.slack_bot_token.get_secret_value())

    # -----------------------------------------------------
    # Connector factory
    # -----------------------------------------------------
    def get_connector(self, corr_id: str):
        """
        Build a SlackConnector bound to this integration's token.
        Lazy import avoids circular dependencies.
        """
        from app.connectors.slack_connector import SlackConnector

        return SlackConnector(
            slack_client=self.build_client(),
            corr_id=corr_id,
            default_channel=self.default_channel,
        )