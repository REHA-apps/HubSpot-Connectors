from typing import Any, Dict, List, Optional
import httpx

from app.core.config import settings
from app.db.supabase import StorageService
from app.integrations.base_client import BaseClient
from app.api.hubspot.schemas import HubSpotContactProperties, HubSpotTaskProperties

UNAUTHORIZED_ERROR = 401
NOT_FOUND_ERROR = 404
SUCCESS = 200


class HubSpotClient(BaseClient):
    """
    HubSpot HTTP client using BaseClient with token refresh and CRUD methods.
    """

    def __init__(self, access_token: str, refresh_token: str, slack_team_id: str):
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.slack_team_id = slack_team_id
        super().__init__(
            base_url="https://api.hubapi.com/crm/v3",
            headers={"Authorization": f"Bearer {access_token}", "Content-Type": "application/json"},
        )

    def _get_headers(self) -> Dict[str, str]:
        """Always return fresh headers based on the current access_token."""
        return {"Authorization": f"Bearer {self.access_token}", "Content-Type": "application/json"}

    async def request(self, method: str, path: str, **kwargs) -> Any:
        """Override BaseClient request to add token refresh logic."""
        url = f"{self.base_url}/{path.lstrip('/')}"
        async with httpx.AsyncClient() as client:
            response = await client.request(method, url, headers=self._get_headers(), **kwargs)

            # Handle expired access token
            if response.status_code == UNAUTHORIZED_ERROR and self.refresh_token:
                refreshed = await self.refresh_token_logic()
                if refreshed:
                    # Retry request with new access token
                    response = await client.request(method, url, headers=self._get_headers(), **kwargs)

            if method.upper() == "GET" and response.status_code == NOT_FOUND_ERROR:
                return None

            response.raise_for_status()
            return response.json()

    async def refresh_token_logic(self) -> bool:
        """Refresh HubSpot access token using refresh_token and update Supabase."""
        url = "https://api.hubapi.com/oauth/v1/token"
        data = {
            "grant_type": "refresh_token",
            "client_id": settings.HUBSPOT_CLIENT_ID,
            "client_secret": settings.HUBSPOT_CLIENT_SECRET,
            "refresh_token": self.refresh_token,
        }

        async with httpx.AsyncClient() as client:
            response = await client.post(url, data=data)
            if response.status_code == SUCCESS:
                resp_data = response.json()
                self.access_token = resp_data["access_token"]
                new_rt = resp_data.get("refresh_token")
                if new_rt:
                    self.refresh_token = new_rt

                # Update Supabase tokens
                return await StorageService.update_tokens(
                    slack_team_id=self.slack_team_id,
                    provider="hubspot",
                    new_at=self.access_token,
                    new_rt=new_rt,
                )

        print(f"❌ HubSpot Token Refresh Failed: {response.status_code} - {response.text}")
        return False

    # ---------------------------
    # Generic CRUD Methods
    # ---------------------------
    async def create_object(self, object_type: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        return await self.request("POST", f"objects/{object_type}", json={"properties": properties})

    async def get_object(
        self,
        object_type: str,
        object_id: str,
        properties: Optional[List[str]] = None
    ) -> Optional[Dict[str, Any]]:
        path = f"objects/{object_type}/{object_id}"
        if properties:
            path += f"?properties={','.join(properties)}"
        return await self.request("GET", path)

    async def update_object(self, object_type: str, object_id: str, properties: Dict[str, Any]) -> Dict[str, Any]:
        return await self.request("PATCH", f"objects/{object_type}/{object_id}", json={"properties": properties})

    async def list_objects(self, object_type: str, limit: int = 10, after: Optional[str] = None) -> Dict[str, Any]:
        path = f"objects/{object_type}?limit={limit}"
        if after:
            path += f"&after={after}"
        return await self.request("GET", path)

    # ---------------------------
    # HubSpot-specific Methods
    # ---------------------------
    async def create_contact(self, properties: HubSpotContactProperties) -> Dict[str, Any]:
        return await self.create_object(
            "contacts", properties.model_dump(exclude_none=True, by_alias=True)
        )

    async def create_task(self, properties: HubSpotTaskProperties) -> Dict[str, Any]:
        return await self.create_object("tasks", properties.model_dump(exclude_none=True))

    async def get_contact_by_email(self, email: str) -> Optional[Dict[str, Any]]:
        """Search HubSpot contact by email with selected properties."""
        properties = ["firstname", "lastname", "email", "company", "jobtitle", "lifecyclestage"]
        path = f"objects/contacts/{email}?idProperty=email&properties={','.join(properties)}"
        return await self.request("GET", path)
