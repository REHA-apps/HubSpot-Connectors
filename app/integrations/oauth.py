# app/integrations/oauth.py
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.core.config import settings
from app.core.logging import CorrelationAdapter, get_logger
from app.utils.helpers import HTTPClient

logger = get_logger("oauth")


HubSpotOAuthResponse = Mapping[str, Any]
SlackOAuthResponse = Mapping[str, Any]


class OAuthService:
    """Handles OAuth token exchanges for HubSpot and Slack.
    - correlation ID support
    - structured logging
    - Python 3.12 typing
    - consistent error handling
    """

    # ------------------------------------------------------------------
    # HubSpot OAuth
    # ------------------------------------------------------------------
    @staticmethod
    async def exchange_hubspot_token(
        code: str,
        *,
        corr_id: str | None = None,
    ) -> HubSpotOAuthResponse:
        log = CorrelationAdapter(logger, corr_id or "oauth_hubspot")
        log.info("Exchanging HubSpot OAuth code")

        url = "https://api.hubapi.com/oauth/v1/token"
        data = {
            "grant_type": "authorization_code",
            "client_id": settings.HUBSPOT_CLIENT_ID,
            "client_secret": settings.HUBSPOT_CLIENT_SECRET.get_secret_value(),
            "redirect_uri": settings.HUBSPOT_REDIRECT_URI.unicode_string(),
            "code": code,
        }

        client = HTTPClient.get_client()

        try:
            resp = await client.post(url, data=data)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            log.error("HubSpot OAuth request failed: %s", exc)
            raise

        if "access_token" not in payload:
            log.error("Invalid HubSpot OAuth response: %s", payload)
            raise ValueError("HubSpot OAuth response missing access_token")

        log.info("HubSpot OAuth token exchange successful")
        return payload

    # ------------------------------------------------------------------
    # Slack OAuth
    # ------------------------------------------------------------------
    @staticmethod
    async def exchange_slack_token(
        code: str,
        *,
        corr_id: str | None = None,
    ) -> SlackOAuthResponse:
        log = CorrelationAdapter(logger, corr_id or "oauth_slack")
        log.info("Exchanging Slack OAuth code")

        url = "https://slack.com/api/oauth.v2.access"
        data = {
            "client_id": settings.SLACK_CLIENT_ID,
            "client_secret": settings.SLACK_CLIENT_SECRET.get_secret_value(),
            "code": code,
            "redirect_uri": settings.SLACK_REDIRECT_URI.unicode_string(),
        }

        client = HTTPClient.get_client()

        try:
            resp = await client.post(url, data=data)
            resp.raise_for_status()
            payload = resp.json()
        except Exception as exc:
            log.error("Slack OAuth request failed: %s", exc)
            raise

        if not payload.get("ok"):
            error = payload.get("error", "unknown_error")
            log.error("Slack OAuth failed: %s", error)
            raise ValueError(f"Slack OAuth failed: {error}")

        log.info("Slack OAuth token exchange successful")
        return payload
