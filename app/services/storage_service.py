from typing import Dict, Any, Optional
from supabase import create_client, Client
from app.core.config import settings

class StorageService:
    """Service for handling data storage using Supabase."""
    
    _client: Optional[Client] = None

    @classmethod
    def get_client(cls) -> Client:
        """Initializes and returns the Supabase client."""
        if cls._client is None:
            if not settings.SUPABASE_URL or not settings.SUPABASE_KEY:
                # In a real app, we might want to raise an error here
                # For now, we'll try to initialize and let it fail if credentials are missing
                pass
            cls._client = create_client(settings.SUPABASE_URL, settings.SUPABASE_KEY)
        return cls._client

    @classmethod
    async def save_integration(cls, data: Dict[str, Any]) -> Dict[str, Any]:
        """
        Saves or updates HubSpot integration data.
        Upserts based on the slack_team_id.
        """
        client = cls.get_client()
        # Ensure we have a slack_team_id to upsert on
        slack_team_id = data.get("slack_team_id")
        if not slack_team_id:
            raise ValueError("slack_team_id is required for saving integration")

        response = client.table("integrations").upsert(data, on_conflict="slack_team_id").execute()
        item = response.data[0] if response.data else {}
        if not isinstance(item, dict):
            return {}
        return item

    @classmethod
    async def get_by_slack_id(cls, slack_team_id: str) -> Optional[Dict[str, Any]]:
        """
        Retrieves integration data by Slack team ID.
        """
        client = cls.get_client()
        response = client.table("integrations").select("*").eq("slack_team_id", slack_team_id).execute()
        item = response.data[0] if response.data else None
        if item is not None and not isinstance(item, dict):
            return None
        return item

    @classmethod
    async def update_hubspot_tokens(cls, slack_team_id: str, new_access_token: str, new_refresh_token: str = None) -> bool:
        """
        Updates HubSpot tokens using slack_team_id as the unique identifier.
        This is safer than filtering by the token itself.
        """
        try:
            client = cls.get_client()
            
            # Prepare the update payload
            update_payload = {
                "hubspot_access_token": new_access_token,
                "updated_at": "now()" # Tracks when the refresh happened
            }
            
            # If HubSpot provided a new refresh token (rotation), include it
            if new_refresh_token:
                update_payload["hubspot_refresh_token"] = new_refresh_token
            
            # Execute the update
            response = client.table("integrations")\
                .update(update_payload)\
                .eq("slack_team_id", slack_team_id)\
                .execute()
            
            if response.data:
                print(f"✅ Supabase sync complete for team: {slack_team_id}")
                return True
            else:
                print(f"⚠️ No record found for team_id: {slack_team_id}. Update failed.")
                return False
                
        except Exception as e:
            print(f"❌ StorageService Error: {str(e)}")
            return False