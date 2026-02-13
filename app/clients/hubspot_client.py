# app/clients/hubspot_client.py
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

import httpx

from app.clients.base_client import BaseClient
from app.core.config import settings
from app.core.logging import CorrelationAdapter, get_logger

logger = get_logger("hubspot.client")


class HubSpotClient(BaseClient):
    """Pure HubSpot HTTP client.

    Responsibilities:
    - Send HTTP requests to HubSpot
    - Refresh tokens when expired
    - Return refreshed tokens to the caller
    - No database access
    - No workspace logic
    """

    def __init__(
        self,
        access_token: str,
        refresh_token: str | None,
        *,
        corr_id: str | None = None,
    ) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token

        super().__init__(
            base_url="https://api.hubapi.com/crm/v3",
            headers={
                "Authorization": f"Bearer {access_token}",
                "Content-Type": "application/json",
            },
            corr_id=corr_id,
        )

        self.log = CorrelationAdapter(logger, corr_id or "hubspot")

    # ---------------------------------------------------------
    # Public request wrapper with auto-refresh
    # ---------------------------------------------------------
    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> Any:
        try:
            return await self._raw_request(
                method,
                path,
                params=params,
                json=json,
                data=data,
            )

        except httpx.HTTPStatusError as exc:
            if exc.response.status_code == 401 and self.refresh_token:
                self.log.warning("HubSpot token expired; attempting refresh")

                new_tokens = await self._refresh_token()
                if new_tokens:
                    # Update in-memory tokens
                    self.access_token = new_tokens["access_token"]
                    self.refresh_token = new_tokens.get("refresh_token")

                    return await self._raw_request(
                        method,
                        path,
                        params=params,
                        json=json,
                        data=data,
                    )

            raise

    # ---------------------------------------------------------
    # Raw request
    # ---------------------------------------------------------
    async def _raw_request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> Any:
        url = f"{self.base_url}/{path.lstrip('/')}"

        self.log.info("HubSpot %s %s", method, url)

        client = self.get_client()

        response = await client.request(
            method=method,
            url=url,
            headers=self._headers(),
            params=params,
            json=json,
            data=data,
        )

        if method.upper() == "GET" and response.status_code == 404:
            self.log.info("HubSpot GET %s returned 404 (None)", url)
            return None

        response.raise_for_status()
        return response.json()

    # ---------------------------------------------------------
    # Token refresh (returns new tokens, does NOT persist)
    # ---------------------------------------------------------
    async def _refresh_token(self) -> dict[str, str] | None:
        url = "https://api.hubapi.com/oauth/v1/token"
        data = {
            "grant_type": "refresh_token",
            "client_id": settings.HUBSPOT_CLIENT_ID,
            "client_secret": settings.HUBSPOT_CLIENT_SECRET.get_secret_value(),
            "refresh_token": self.refresh_token,
        }

        client = self.get_client()

        try:
            resp = await client.post(url, data=data)
        except Exception as exc:
            self.log.error("HubSpot refresh request failed: %s", exc)
            return None

        if resp.status_code != 200:
            self.log.error(
                "HubSpot token refresh failed: status=%s body=%s",
                resp.status_code,
                resp.text,
            )
            return None

        payload = resp.json()
        if "access_token" not in payload:
            self.log.error("HubSpot refresh response missing access_token")
            return None

        return payload  # caller persists tokens

    # ---------------------------------------------------------
    # Headers
    # ---------------------------------------------------------
    def _headers(self) -> Mapping[str, str]:
        return {
            "Authorization": f"Bearer {self.access_token}",
            "Content-Type": "application/json",
        }

    # ---------------------------------------------------------
    # Convenience methods
    # ---------------------------------------------------------
    async def create_object(
        self,
        object_type: str,
        properties: Mapping[str, Any],
    ) -> dict[str, Any]:
        return await self.request(
            "POST",
            f"objects/{object_type}",
            json={"properties": properties},
        )

    async def get_object(
        self,
        object_type: str,
        object_id: str,
        properties: list[str] | None = None,
    ) -> Any:
        path = f"objects/{object_type}/{object_id}"
        if properties:
            path += f"?properties={','.join(properties)}"
        return await self.request("GET", path)

    async def create_contact(self, properties: Mapping[str, Any]) -> dict[str, Any]:
        return await self.create_object("contacts", properties)

    async def create_task(self, properties: Mapping[str, Any]) -> dict[str, Any]:
        return await self.create_object("tasks", properties)

    async def search_contacts(self, query: str) -> list[dict[str, Any]]:
        payload = {
            "filterGroups": [
                {
                    "filters": [
                        {
                            "propertyName": "email",
                            "operator": "CONTAINS_TOKEN",
                            "value": query,
                        },
                        {
                            "propertyName": "firstname",
                            "operator": "CONTAINS_TOKEN",
                            "value": query,
                        },
                        {
                            "propertyName": "lastname",
                            "operator": "CONTAINS_TOKEN",
                            "value": query,
                        },
                    ]
                }
            ],
            "limit": 5,
            "properties": [
                "email",
                "firstname",
                "lastname",
                "company",
                "lifecyclestage",
                "hs_analytics_num_visits",
            ],
        }
        resp = await self.request("POST", "objects/contacts/search", json=payload)
        return resp.get("results", [])

    async def search_deals(self, query: str) -> list[dict[str, Any]]:
        payload = {
            "filterGroups": [
                {
                    "filters": [
                        {
                            "propertyName": "dealname",
                            "operator": "CONTAINS_TOKEN",
                            "value": query,
                        }
                    ]
                }
            ],
            "limit": 5,
            "properties": ["dealname", "amount", "dealstage", "pipeline"],
        }

        resp = await self.request("POST", "objects/deals/search", json=payload)
        return resp.get("results", [])
