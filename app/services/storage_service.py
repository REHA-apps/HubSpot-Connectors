import os
from supabase import create_client, Client
from datetime import datetime, timedelta
from typing import Any

supabase: Client = create_client(
    os.getenv("SUPABASE_URL") or "",
    os.getenv("SUPABASE_KEY") or ""
)

class StorageService:
    @staticmethod
    async def save_integration(data: dict):
        """Saves or updates tokens after a successful OAuth install."""
        # Calculate expiration (HubSpot tokens usually last 30 minutes)
        expires_at = datetime.utcnow() + timedelta(seconds=data['expires_in'])

        row = {
            "hubspot_portal_id": str(data['portal_id']),
            "slack_team_id": data['slack_team_id'],
            "hubspot_access_token": data['access_token'],
            "hubspot_refresh_token": data['refresh_token'],
            "hubspot_expires_at": expires_at.isoformat(),
            "slack_bot_token": data['slack_bot_token']
        }

        # Upsert: update if portal_id exists, otherwise insert
        return supabase.table("integrations").upsert(row, on_conflict="hubspot_portal_id").execute()

    @staticmethod
    async def get_by_slack_id(slack_team_id: str) -> dict[str, Any] | None:
        """Finds the HubSpot credentials for a specific Slack workspace."""
        response = supabase.table("integrations") \
            .select("*") \
            .eq("slack_team_id", slack_team_id) \
            .single() \
            .execute()
        # response.data can be a dict or None if no record found
        return response.data if isinstance(response.data, dict) else None
