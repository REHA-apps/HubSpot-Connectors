# app/services/hubspot_service.py
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.clients.hubspot_client import HubSpotClient
from app.core.logging import CorrelationAdapter, get_logger
from app.db.storage_service import StorageService
from app.db.records import Provider

logger = get_logger("hubspot.service")


class HubSpotService:
    """Domain-level HubSpot service.

    Responsibilities:
    - Load HubSpot tokens from DB (async)
    - Create HubSpotClient (async)
    - Persist refreshed tokens (async)
    - Expose domain operations (search, create contact, create task)
    - Keep connectors and routers clean
    """

    def __init__(self, corr_id: str) -> None:
        self.corr_id = corr_id
        self.log = CorrelationAdapter(logger, corr_id)
        self.storage = StorageService(corr_id=corr_id)

    # ---------------------------------------------------------
    # Token loading
    # ---------------------------------------------------------
    async def _load_tokens(self, workspace_id: str) -> tuple[str, str | None]:
        integration = await self.storage.get_integration(
            workspace_id=workspace_id,
            provider=Provider.HUBSPOT,
        )

        if not integration:
            raise ValueError(f"No HubSpot integration for workspace {workspace_id}")

        if not integration.access_token:
            raise ValueError("HubSpot integration missing access_token")
        
        access_token = integration.access_token.get_secret_value()
        refresh_token = integration.refresh_token.get_secret_value() if integration.refresh_token else None
        return access_token, refresh_token

    # ---------------------------------------------------------
    # Client initialization
    # ---------------------------------------------------------
    async def get_client(self, workspace_id: str) -> HubSpotClient:
        access_token, refresh_token = await self._load_tokens(workspace_id)

        client = HubSpotClient(
            access_token=access_token,
            refresh_token=refresh_token,
            corr_id=self.corr_id,
        )

        async def _handle_refresh(new_at: str, new_rt: str | None) -> None:
            await self.persist_tokens(
                workspace_id=workspace_id,
                new_access=new_at,
                new_refresh=new_rt,
            )
        # Attach callback so HubSpotClient can persist refreshed tokens
        client.on_token_refresh = _handle_refresh

        return client   

    # ---------------------------------------------------------
    # Token persistence
    # ---------------------------------------------------------
    async def persist_tokens(
        self,
        workspace_id: str,
        new_access: str,
        new_refresh: str | None,
    ) -> None:
        await self.storage.update_tokens(
            workspace_id=workspace_id,
            provider=Provider.HUBSPOT,
            new_at=new_access,
            new_rt=new_refresh,
        )

    # ---------------------------------------------------------
    # Domain operations
    # ---------------------------------------------------------
    async def search(
        self,
        *,
        workspace_id: str,
        object_type: str,
        query: str,
    ):
        """
        Unified HubSpot search entry point.
        Delegates to the correct search_* method based on object_type.
        """
        object_type = object_type.lower()

        match object_type:
            case "contacts" | "contact":
                return await self.search_contacts(workspace_id, query)

            case "leads" | "lead":
                return await self.search_leads(workspace_id, query)

            case "deals" | "deal":
                return await self.search_deals(workspace_id, query)

            case "companies" | "company":
                return await self.search_companies(workspace_id, query)

            case _: 
                self.log.error("Unknown HubSpot object_type=%s", object_type)
                return []

    async def search_contacts(
        self,
        workspace_id: str,
        query: str,
    ) -> list[dict[str, Any]]:
        client = await self.get_client(workspace_id)
        return await client.search_contacts(query)

    async def search_deals(
        self,
        workspace_id: str,
        query: str,
    ) -> list[dict[str, Any]]:
        client = await self.get_client(workspace_id)
        return await client.search_deals(query)

    async def search_leads(
        self,
        workspace_id: str,
        query: str,
    ) -> list[dict[str, Any]]:
        client = await self.get_client(workspace_id)
        return await client.search_leads(query)

    async def search_companies(
        self,
        workspace_id: str,
        query: str,
    ) -> list[dict[str, Any]]:
        client = await self.get_client(workspace_id)
        return await client.search_companies(query)
    
    async def create_contact(
        self,
        workspace_id: str,
        properties: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        client = await self.get_client(workspace_id)
        return await client.create_contact(properties)

    async def create_task(
        self,
        workspace_id: str,
        properties: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        client = await self.get_client(workspace_id)
        return await client.create_task(properties)

    async def get_contact(self, object_id: str, portal_id: str) -> dict[str, Any]:
        client = await self.get_client(workspace_id=portal_id)
        return await client.get_contact(object_id)

    async def get_deal(self, object_id: str, portal_id: str) -> dict[str, Any]:
        client = await self.get_client(workspace_id=portal_id)
        return await client.get_deal(object_id)

    async def get_company(self, object_id: str, portal_id: str) -> dict[str, Any]:
        client = await self.get_client(workspace_id=portal_id)
        return await client.get_company(object_id)
