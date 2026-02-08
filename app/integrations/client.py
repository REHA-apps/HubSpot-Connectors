import httpx
from typing import Optional, Any, Dict
from app.integrations.schemas import HubSpotContactProperties, HubSpotTaskProperties
from app.utils.helpers import HTTPClient, hubspot_retry
from app.services.storage_service import StorageService
from app.core.config import settings

class HubSpotClient:
    def __init__(self, access_token: str, refresh_token: str, slack_team_id: str):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.slack_team_id = slack_team_id # Store the ID here
        self.base_url = "https://api.hubapi.com/crm/v3"

    def _get_headers(self):
        """Always returns fresh headers based on the current access_token."""
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

    async def _request(self, method: str, path: str, **kwargs) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"
        
        # Using a context manager for the client is safer in async loops
        async with httpx.AsyncClient() as client:
            response = await client.request(
                method, 
                url, 
                headers=self._get_headers(), 
                **kwargs
            )

            # --- AUTO-REFRESH LOGIC ---
            if response.status_code == 401 and self.refresh_token:
                print("🔄 Access token expired. Attempting refresh...")
                refreshed = await self.refresh_token_logic()
                
                if refreshed:
                    print("✅ Token refreshed. Retrying original request...")
                    # Retry with the updated self.access_token
                    response = await client.request(
                        method, 
                        url, 
                        headers=self._get_headers(), 
                        **kwargs
                    )

            if method == "GET" and response.status_code == 404:
                return None
                
            response.raise_for_status()
            return response.json()

    async def refresh_token_logic(self) -> bool:
        """Exchanges refresh_token for a new access_token and updates Supabase."""
        url = "https://api.hubapi.com/oauth/v1/token"
        data = {
            "grant_type": "refresh_token",
            "client_id": settings.HUBSPOT_CLIENT_ID, # Pulls from your .env via settings
            "client_secret": settings.HUBSPOT_CLIENT_SECRET,
            "refresh_token": self.refresh_token,
        }
        
        async with httpx.AsyncClient() as client:
            response = await client.post(url, data=data)
            
            if response.status_code == 200:
                data = response.json()
                new_at = data["access_token"]
                new_rt = data.get("refresh_token") # HubSpot might rotate this
                
                self.access_token = new_at
                
                # Now update Supabase using the slack_team_id
                return await StorageService.update_hubspot_tokens(
                    slack_team_id=self.slack_team_id, 
                    new_access_token=new_at,
                    new_refresh_token=new_rt
                )
        return False

    async def create_object(self, object_type: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        """Generic method to create any CRM object."""
        return await self._request("POST", f"objects/{object_type}", json={"properties": properties})

    async def get_object(self, object_type: str, object_id: str, properties: Optional[list[str]] = None) -> Optional[Dict[str, Any]]:
        """Generic method to retrieve any CRM object."""
        path = f"objects/{object_type}/{object_id}"
        if properties:
            path += f"?properties={','.join(properties)}"
        return await self._request("GET", path)

    async def update_object(self, object_type: str, object_id: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        """Generic method to update any CRM object."""
        return await self._request("PATCH", f"objects/{object_type}/{object_id}", json={"properties": properties})

    async def list_objects(self, object_type: str, limit: int = 10, after: Optional[str] = None) -> Dict[str, Any]:
        """Generic method to list CRM objects with pagination."""
        path = f"objects/{object_type}?limit={limit}"
        if after:
            path += f"&after={after}"
        return await self._request("GET", path)

    async def create_contact(self, properties: HubSpotContactProperties) -> Dict[str, Any]:
        """Creates a contact in HubSpot."""
        return await self.create_object("contacts", properties.model_dump(exclude_none=True, by_alias=True))

    async def create_task(self, properties: HubSpotTaskProperties) -> Dict[str, Any]:
        """Creates a CRM Task in HubSpot."""
        return await self.create_object("tasks", properties.model_dump(exclude_none=True))

    async def get_contact_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Searches for a contact by email address."""
        return await self._request("GET", f"objects/contacts/{email}?idProperty=email")
