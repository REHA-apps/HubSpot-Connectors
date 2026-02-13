# app/services/hubspot_service.py
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.clients.hubspot_client import HubSpotClient
from app.core.logging import CorrelationAdapter, get_logger
from app.db.supabase import StorageService

logger = get_logger("hubspot.service")


class HubSpotService:
    """Domain-level HubSpot service.

    Responsibilities:
    - Load HubSpot tokens from DB
    - Create HubSpotClient
    - Persist refreshed tokens
    - Expose domain operations (search, create contact, create task)
    - Keep connectors and routers clean
    """

    def __init__(self, corr_id: str) -> None:
        self.corr_id = corr_id
        self.log = CorrelationAdapter(logger, corr_id)
        self.storage = StorageService(corr_id=corr_id)

    # ---------------------------------------------------------
    # Client initialization
    # ---------------------------------------------------------
    def _load_tokens(self, workspace_id: str) -> tuple[str, str | None]:
        integration = self.storage.get_integration_by_workspace_and_provider(
            workspace_id=workspace_id,
            provider="hubspot",
        )

        if not integration:
            raise ValueError(f"No HubSpot integration for workspace {workspace_id}")

        if not integration.access_token:
            raise ValueError("HubSpot integration missing access_token")

        return integration.access_token, integration.refresh_token

    def get_client(self, workspace_id: str) -> HubSpotClient:
        access_token, refresh_token = self._load_tokens(workspace_id)

        return HubSpotClient(
            access_token=access_token,
            refresh_token=refresh_token,
            corr_id=self.corr_id,
        )

    # ---------------------------------------------------------
    # Token persistence
    # ---------------------------------------------------------
    def persist_tokens(
        self,
        workspace_id: str,
        new_access: str,
        new_refresh: str | None,
    ) -> None:
        self.storage.update_tokens(
            workspace_id=workspace_id,
            provider="hubspot",
            new_at=new_access,
            new_rt=new_refresh,
        )

    # ---------------------------------------------------------
    # Domain operations
    # ---------------------------------------------------------
    async def search_contacts(
        self, workspace_id: str, query: str
    ) -> list[dict[str, Any]]:
        client = self.get_client(workspace_id)
        return await client.search_contacts(query)

    async def search_deals(self, workspace_id: str, query: str) -> list[dict[str, Any]]:
        client = self.get_client(workspace_id)
        return await client.search_deals(query)

    async def create_contact(
        self,
        workspace_id: str,
        properties: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        client = self.get_client(workspace_id)
        return await client.create_contact(properties)

    async def create_task(
        self,
        workspace_id: str,
        properties: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        client = self.get_client(workspace_id)
        return await client.create_task(properties)
