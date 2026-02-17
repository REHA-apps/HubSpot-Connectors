from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import httpx

from app.clients.base_client import BaseClient
from app.core.config import settings
from app.core.logging import CorrelationAdapter, get_logger
from fastapi import Depends
from app.utils.constants import ErrorCode   

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
        corr_id: str,
        access_token: str,
        refresh_token: str | None,
    ) -> None:
        self.corr_id = corr_id
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

        self.log = CorrelationAdapter(logger, self.corr_id)

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
            if exc.response.status_code == ErrorCode.UNAUTHORIZED and self.refresh_token:
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

                    return await super().request(
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

        if response.status_code >= ErrorCode.BAD_REQUEST:
            self.log.error("HubSpot error %s: %s", response.status_code, response.text)
            response.raise_for_status()
        if method.upper() == "GET" and response.status_code == ErrorCode.NOT_FOUND:
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

        if resp.status_code != ErrorCode.SUCCESS:
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
    @staticmethod
    def _headers(token: str) -> Mapping[str, str]:
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
    
    async def get_contact(self, object_id: str) -> dict[str, Any]:
        return await self.get_object(
            "contacts",
            object_id,
            properties=["firstname", "lastname", "email", "phone", "lifecyclestage"],
        )

    async def get_deal(self, object_id: str) -> dict[str, Any]:
        return await self.get_object(
            "deals",
            object_id,
            properties=["dealname", "amount", "pipeline", "dealstage"],
        )

    async def get_company(self, object_id: str) -> dict[str, Any]:
        return await self.get_object(
            "companies",
            object_id,
            properties=["name", "domain", "industry"],
        )

    async def create_contact(self, properties: Mapping[str, Any]) -> dict[str, Any]:
        return await self.create_object("contacts", properties)

    async def create_task(self, properties: Mapping[str, Any]) -> dict[str, Any]:
        return await self.create_object("tasks", properties)

    # ---------------------------------------------------------
    # Search: Contacts
    # ---------------------------------------------------------
    async def search_contacts(self, query: str) -> list[dict[str, Any]]:
        q = query.strip().lower()

        # 1. Try CRM search first
        payload = {
            "filterGroups": [
                {"filters": [{"propertyName": "email", "operator": "EQ", "value": q}]},
                {"filters": [{"propertyName": "hs_additional_emails", "operator": "CONTAINS_TOKEN", "value": q}]},
                {"filters": [{"propertyName": "firstname", "operator": "CONTAINS_TOKEN", "value": q}]},
                {"filters": [{"propertyName": "lastname", "operator": "CONTAINS_TOKEN", "value": q}]},
            ],
            "limit": 5,
            "properties": [
                "email",
                "firstname",
                "lastname",
                "company",
                "lifecyclestage",
                "hs_analytics_num_visits",
                "hs_additional_emails",
            ],
        }

        resp = await self.request("POST", "objects/contacts/search", json=payload)
        results = resp.get("results", [])

        if results:
            return results

        # 2. Fallback: identity profile lookup (email → contactId)
        try:
            identity_resp = await self.request(
                "GET",
                f"objects/contacts/{q}",
                params={"idProperty": "email"},
            )
            return [identity_resp]
        except Exception:
            return []
    
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

    async def search_companies(self, query: str) -> list[dict[str, Any]]:
        """Search HubSpot companies using CRM v3 search API.
        Mirrors search_contacts, search_leads, and search_deals.
        """
        payload = {
            "filterGroups": [
                {
                    "filters": [
                        {
                            "propertyName": "name",
                            "operator": "EQ",
                            "value": query,
                        },
                        {
                            "propertyName": "domain",
                            "operator": "CONTAINS_TOKEN",
                            "value": query,
                        },
                    ]
                }
            ],
            "limit": 5,
            "properties": [
                "name",
                "domain",
                "industry",
                "city",
                "state",
                "country",
                "lifecyclestage",
            ],
        }
        self.log.info(f"Search companies: {query}, {payload}")

        resp = await self.request("POST", "objects/companies/search", json=payload)
        return resp.get("results", [])