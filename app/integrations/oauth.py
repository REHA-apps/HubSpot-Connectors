# app/integrations/oauth.py
from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass
from typing import Any

from app.core.config import settings
from app.core.logging import CorrelationAdapter, get_logger
from app.utils.helpers import HTTPClient

logger = get_logger("oauth")


# ---------------------------------------------------------
# Typed OAuth responses
# ---------------------------------------------------------
@dataclass(frozen=True)
class HubSpotOAuthResult:
    access_token: str
    refresh_token: str | None
    expires_in: int
    portal_id: str
    raw: Mapping[str, Any]


@dataclass(frozen=True)
class SlackOAuthResult:
    access_token: str
    bot_user_id: str
    team_id: str
    raw: Mapping[str, Any]


# ---------------------------------------------------------
# Custom exceptions
# ---------------------------------------------------------
class OAuthExchangeError(Exception):
    pass


class OAuthService:
    """Handles OAuth token exchanges for HubSpot and Slack.

    Features:
    - correlation ID support
    - structured logging
    - typed return values
    - consistent error handling
    """

    def __init__(self, corr_id: str | None = None) -> None:
        self.log = CorrelationAdapter(logger, corr_id or "oauth")
        self.client = HTTPClient.get_client()

    # ---------------------------------------------------------
    # Helpers
    # ---------------------------------------------------------
    async def _post_form(self, url: str, data: Mapping[str, Any]) -> Mapping[str, Any]:
        try:
            resp = await self.client.post(url, data=data)
            resp.raise_for_status()
            return resp.json()
        except Exception as exc:
            self.log.error("OAuth request failed: %s", exc)
            raise OAuthExchangeError(str(exc)) from exc

    # ---------------------------------------------------------
    # HubSpot OAuth
    # ---------------------------------------------------------
    async def exchange_hubspot_token(self, code: str) -> HubSpotOAuthResult:
        self.log.info("Exchanging HubSpot OAuth code")

        payload = await self._post_form(
            "https://api.hubapi.com/oauth/v1/token",
            {
                "grant_type": "authorization_code",
                "client_id": settings.HUBSPOT_CLIENT_ID,
                "client_secret": settings.HUBSPOT_CLIENT_SECRET.get_secret_value(),
                "redirect_uri": settings.HUBSPOT_REDIRECT_URI.unicode_string(),
                "code": code,
            },
        )

        if "access_token" not in payload:
            self.log.error("Invalid HubSpot OAuth response: %s", payload)
            raise OAuthExchangeError("HubSpot OAuth response missing access_token")

        self.log.info("HubSpot OAuth token exchange successful")

        return HubSpotOAuthResult(
            access_token=payload["access_token"],
            refresh_token=payload.get("refresh_token"),
            expires_in=payload.get("expires_in", 0),
            portal_id=str(payload.get("hub_id", "")),
            raw=payload,
        )

    # ---------------------------------------------------------
    # Slack OAuth
    # ---------------------------------------------------------
    async def exchange_slack_token(self, code: str) -> SlackOAuthResult:
        self.log.info("Exchanging Slack OAuth code")

        payload = await self._post_form(
            "https://slack.com/api/oauth.v2.access",
            {
                "client_id": settings.SLACK_CLIENT_ID,
                "client_secret": settings.SLACK_CLIENT_SECRET.get_secret_value(),
                "code": code,
                "redirect_uri": settings.SLACK_REDIRECT_URI.unicode_string(),
            },
        )

        if not payload.get("ok"):
            error = payload.get("error", "unknown_error")
            self.log.error("Slack OAuth failed: %s", error)
            raise OAuthExchangeError(f"Slack OAuth failed: {error}")

        self.log.info("Slack OAuth token exchange successful")

        return SlackOAuthResult(
            access_token=payload["access_token"],
            bot_user_id=payload["bot_user_id"],
            team_id=payload["team"]["id"],
            raw=payload,
        )
