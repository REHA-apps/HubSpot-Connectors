from typing import Optional, Tuple
import httpx

from app.core.config import settings
from app.db.supabase import StorageService


class TokenManager:
    """Centralized token retrieval and refresh for integrations."""

    @staticmethod
    async def get_hubspot_tokens(slack_team_id: str) -> Tuple[str, Optional[str], Optional[str]]:
        integration = await StorageService.get_by_slack_id(slack_team_id, provider="hubspot")
        if not integration:
            raise ValueError(f"No HubSpot integration found for Slack team {slack_team_id}")

        return integration.access_token, integration.refresh_token, getattr(integration, "portal_id", None)

    @staticmethod
    async def refresh_hubspot_tokens(slack_team_id: str) -> Tuple[str, Optional[str]]:
        integration = await StorageService.get_by_slack_id(slack_team_id, provider="hubspot")
        if not integration or not integration.refresh_token:
            raise ValueError("Cannot refresh HubSpot tokens: missing integration or refresh token")

        url = "https://api.hubapi.com/oauth/v1/token"
        data = {
            "grant_type": "refresh_token",
            "client_id": settings.HUBSPOT_CLIENT_ID,
            "client_secret": settings.HUBSPOT_CLIENT_SECRET,
            "refresh_token": integration.refresh_token,
        }

        async with httpx.AsyncClient() as client:
            resp = await client.post(url, data=data)
            resp.raise_for_status()
            payload = resp.json()

        new_at = payload["access_token"]
        new_rt = payload.get("refresh_token") or integration.refresh_token

        await StorageService.update_tokens(
            slack_team_id=slack_team_id,
            provider="hubspot",
            new_at=new_at,
            new_rt=new_rt,
        )

        return new_at, new_rt