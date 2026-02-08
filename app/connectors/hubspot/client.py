import httpx
from typing import Optional
from app.connectors.hubspot.models import HubSpotContactProperties, HubSpotTaskProperties
from app.core.config import settings

class HubSpotClient:
    def __init__(self, access_token: str):
        self.access_token = access_token
        self.base_url = "https://api.hubapi.com/crm/v3"
        self.headers = {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json"
        }

    async def create_contact(self, properties: HubSpotContactProperties):
        """Creates a contact in HubSpot using validated Pydantic data."""
        url = f"{self.base_url}/objects/contacts"
        # .dict(by_alias=True) ensures 'lead_score_ai' becomes 'hs_analytics_num_visits'
        payload = {"properties": properties.dict(exclude_none=True, by_alias=True)}

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=self.headers, json=payload)
            response.raise_for_status()
            return response.json()

    async def create_task(self, properties: HubSpotTaskProperties):
        """Creates a CRM Task (useful for AI-generated follow-ups)."""
        url = f"{self.base_url}/objects/tasks"
        payload = {"properties": properties.dict(exclude_none=True)}

        async with httpx.AsyncClient() as client:
            response = await client.post(url, headers=self.headers, json=payload)
            return response.json()

    async def get_contact_by_email(self, email: str):
        """Search for a contact to avoid creating duplicates."""
        url = f"{self.base_url}/objects/contacts/{email}?idProperty=email"

        async with httpx.AsyncClient() as client:
            response = await client.get(url, headers=self.headers)
            if response.status_code == 404:
                return None
            return response.json()
