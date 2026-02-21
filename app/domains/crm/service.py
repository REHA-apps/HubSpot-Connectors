from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.core.logging import CorrelationAdapter, get_logger
from app.db.records import Provider
from app.domains.crm.base import BaseCRMService
from app.domains.crm.hubspot.service import HubSpotService

logger = get_logger("crm.service")


class CRMService(BaseCRMService):
    """Orchestration layer for CRM providers.
    Routes generic CRM requests to the appropriate provider-specific service.
    """

    def __init__(self, corr_id: str) -> None:
        self.corr_id = corr_id
        self.log = CorrelationAdapter(logger, corr_id)

        # Initialize provider-specific services
        self.hubspot = HubSpotService(corr_id=corr_id)
        # self.salesforce = SalesforceService(corr_id=corr_id)
        # Placeholder for future expansion

    def _resolve_provider_service(self, provider: Provider) -> BaseCRMService:
        """Resolve the concrete service for a given provider."""
        if provider == Provider.HUBSPOT:
            return self.hubspot

        # Add future providers here
        raise ValueError(f"Unsupported CRM provider: {provider}")

    async def get_object(
        self,
        *,
        workspace_id: str,
        object_type: str,
        object_id: str,
        provider: Provider = Provider.HUBSPOT,  # Default for now
    ) -> Mapping[str, Any] | None:
        service = self._resolve_provider_service(provider)
        return await service.get_object(
            workspace_id=workspace_id,
            object_type=object_type,
            object_id=object_id,
        )

    async def search(
        self,
        *,
        workspace_id: str,
        object_type: str,
        query: str,
        provider: Provider = Provider.HUBSPOT,
    ) -> list[dict[str, Any]]:
        service = self._resolve_provider_service(provider)
        return await service.search(
            workspace_id=workspace_id,
            object_type=object_type,
            query=query,
        )

    async def create_contact(
        self,
        workspace_id: str,
        properties: Mapping[str, Any],
        provider: Provider = Provider.HUBSPOT,
    ) -> Mapping[str, Any]:
        service = self._resolve_provider_service(provider)
        return await service.create_contact(workspace_id, properties)

    async def create_task(
        self,
        workspace_id: str,
        properties: Mapping[str, Any],
        provider: Provider = Provider.HUBSPOT,
    ) -> Mapping[str, Any]:
        service = self._resolve_provider_service(provider)
        return await service.create_task(workspace_id, properties)

    async def create_note(
        self,
        *,
        workspace_id: str,
        content: str,
        associated_id: str,
        associated_type: str,
        provider: Provider = Provider.HUBSPOT,
    ) -> dict[str, Any]:
        service = self._resolve_provider_service(provider)
        return await service.create_note(
            workspace_id=workspace_id,
            content=content,
            associated_id=associated_id,
            associated_type=associated_type,
        )

    async def create_meeting(
        self,
        workspace_id: str,
        properties: Mapping[str, Any],
        contact_id: str | None = None,
        provider: Provider = Provider.HUBSPOT,
    ) -> dict[str, Any]:
        service = self._resolve_provider_service(provider)
        return await service.create_meeting(
            workspace_id=workspace_id,
            properties=properties,
            contact_id=contact_id,
        )
