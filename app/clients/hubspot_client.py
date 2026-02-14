from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import httpx

from app.clients.base_client import BaseClient
from app.core.config import settings
from app.core.logging import CorrelationAdapter, get_logger
from app.utils.constants import (
    BAD_REQUEST_ERROR,
    NOT_FOUND_ERROR,
    SUCCESS,
    UNAUTHORIZED_ERROR,
)

logger = get_logger("hubspot.client")


class HubSpotClient(BaseClient):
    """Pure HubSpot HTTP client.

    Responsibilities:
    - Send HTTP requests to HubSpot
    - Auto-refresh tokens on 401
    - Invoke optional callback on token refresh (no DB writes)
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

        # Optional callback: (new_access_token, new_refresh_token) -> None
        self.on_token_refresh: (
            Callable[[str, str | None], Awaitable[None]]
            | Callable[[str, str | None], None]
            | None
        ) = None

        super().__init__(
            base_url="https://api.hubapi.com/crm/v3",
            headers=self._headers(access_token),
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
            if exc.response.status_code == UNAUTHORIZED_ERROR and self.refresh_token:
                self.log.warning("HubSpot token expired; attempting refresh")

                new_tokens = await self._refresh_token()
                if new_tokens:
                    new_at = new_tokens["access_token"]
                    new_rt = new_tokens.get("refresh_token")

                    # Update in-memory tokens
                    self.access_token = new_at
                    self.refresh_token = new_rt

                    # Update headers
                    self.headers = self._headers(new_at)

                    # Notify service layer
                    if self.on_token_refresh:
                        result = self.on_token_refresh(new_at, new_rt)
                        if isinstance(result, Awaitable):
                            await result

                    return await self._raw_request(
                        method,
                        path,
                        params=params,
                        json=json,
                        data=data,
                    )

            raise

    # ---------------------------------------------------------
    # Raw request (no refresh)
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
            headers=self.headers,
            params=params,
            json=json,
            data=data,
        )

        if response.status_code >= BAD_REQUEST_ERROR:
            self.log.error("HubSpot error %s: %s", response.status_code, response.text)
            response.raise_for_status()
        if method.upper() == "GET" and response.status_code == NOT_FOUND_ERROR:
            self.log.info("HubSpot GET %s returned 404 (None)", url)
            return None

        response.raise_for_status()

        try:
            return response.json()
        except ValueError:
            self.log.error("Invalid JSON response from HubSpot: %s", response.text)
            raise

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

        if resp.status_code != SUCCESS:
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

        return payload

    # ---------------------------------------------------------
    # Headers
    # ---------------------------------------------------------
    def _headers(self, token: str) -> Mapping[str, str]:
        return {
            "Authorization": f"Bearer {token}",
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

    # ---------------------------------------------------------
    # Search: Contacts
    # ---------------------------------------------------------
    async def search_contacts(self, query: str) -> list[dict[str, Any]]:
        payload = {
            "filterGroups": [
                # Exact email match
                {
                    "filters": [
                        {
                            "propertyName": "email",
                            "operator": "EQ",
                            "value": query,
                        }
                    ]
                },
                # First name token match
                {
                    "filters": [
                        {
                            "propertyName": "firstname",
                            "operator": "CONTAINS_TOKEN",
                            "value": query,
                        }
                    ]
                },
                # Last name token match
                {
                    "filters": [
                        {
                            "propertyName": "lastname",
                            "operator": "CONTAINS_TOKEN",
                            "value": query,
                        }
                    ]
                },
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

    # ---------------------------------------------------------
    # Search: Deals
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # Search: Leads (NEW)
    # ---------------------------------------------------------
    async def search_leads(self, query: str) -> list[dict[str, Any]]:
        """Search HubSpot leads using CRM v3 search API.
        Mirrors search_contacts and search_deals.
        """
        payload = {
            "filterGroups": [
                {
                    "filters": [
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
                        {
                            "propertyName": "email",
                            "operator": "CONTAINS_TOKEN",
                            "value": query,
                        },
                    ]
                }
            ],
            "limit": 5,
            "properties": [
                "firstname",
                "lastname",
                "email",
                "company",
                "lifecyclestage",
                "hs_lead_status",
            ],
        }

        resp = await self.request("POST", "objects/leads/search", json=payload)
        return resp.get("results", [])
