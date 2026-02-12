from app.core.config import settings
from app.utils.helpers import HTTPClient
from typing import Any

class OAuthService:

    @staticmethod
    async def exchange_hubspot_token(code: str) -> dict[str, Any]:
        """Exchanges a temporary code for permanent tokens."""
        url = "https://api.hubapi.com/oauth/v1/token"
        data = {
            "grant_type": "authorization_code",
            "client_id": settings.HUBSPOT_CLIENT_ID,
            "client_secret": settings.HUBSPOT_CLIENT_SECRET,
            "redirect_uri": settings.HUBSPOT_REDIRECT_URI,
            "code": code,
        }

        client = HTTPClient.get_client()
        response = await client.post(url, data=data)
        response.raise_for_status()
        
        payload = response.json()

        if "access_token" not in payload:
            raise ValueError(f"Invalid HubSpot OAuth response: {payload}")

        return payload

    @staticmethod
    async def exchange_slack_token(code: str) -> dict[str, Any]:
        url = "https://slack.com/api/oauth.v2.access"

        data = {
            "client_id": settings.SLACK_CLIENT_ID,
            "client_secret": settings.SLACK_CLIENT_SECRET,
            "code": code,
            "redirect_uri": settings.SLACK_REDIRECT_URI,
        }

        client = HTTPClient.get_client()
        response = await client.post(url, data=data)
        response.raise_for_status()

        payload = response.json()

        if not payload.get("ok"):
            raise ValueError(f"Slack OAuth failed: {payload.get('error')}")

        return payload
