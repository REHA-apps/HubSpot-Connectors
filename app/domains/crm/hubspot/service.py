from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.core.exceptions import HubSpotAPIError, IntegrationNotFoundError
from app.core.logging import CorrelationAdapter, get_logger
from app.db.records import Provider
from app.db.storage_service import StorageService
from app.domains.crm.base import BaseCRMService
from app.providers.hubspot.client import HubSpotClient
from app.utils.helpers import normalize_object_type

logger = get_logger("hubspot.service")


class HubSpotService(BaseCRMService):
    """Description:
        Domain service coordinating high-level HubSpot business logic.

    Rules Applied:
        - Orchestrates token management, client initialization, and domain operations.
        - Provides a unified search entry point for various HubSpot object types.
        - Ensures refreshed tokens are automatically persisted to the database.
    """

    def __init__(self, corr_id: str, *, storage: StorageService | None = None) -> None:
        self.corr_id = corr_id
        self.log = CorrelationAdapter(logger, corr_id)
        self.storage = storage or StorageService(corr_id=corr_id)

    # Token management
    async def _load_tokens(self, workspace_id: str) -> tuple[str, str | None]:
        integration = await self.storage.get_integration(
            workspace_id=workspace_id,
            provider=Provider.HUBSPOT,
        )

        if not integration:
            raise IntegrationNotFoundError(
                f"No HubSpot integration for workspace {workspace_id}"
            )

        if not integration.access_token:
            raise HubSpotAPIError("HubSpot integration missing access_token")

        access_token = integration.access_token
        refresh_token = integration.refresh_token
        return access_token, refresh_token

    # Client lifecycle
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

    # Persistence logic
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

    # Domain operations
    async def search(
        self,
        *,
        workspace_id: str,
        object_type: str,
        query: str,
    ):
        """Unified HubSpot search entry point.
        Delegates to the correct search_* method based on object_type.
        """
        object_type = object_type.lower()

        match object_type:
            case "contacts" | "contact" | "leads" | "lead":
                results = await self.search_contacts(workspace_id, query)
                url_segment = "contact"
            case "deals" | "deal":
                results = await self.search_deals(workspace_id, query)
                url_segment = "deal"
            case "companies" | "company":
                results = await self.search_companies(workspace_id, query)
                url_segment = "company"
            case "tickets" | "ticket":
                results = await self.search_tickets(workspace_id, query)
                url_segment = "ticket"
            case "tasks" | "task":
                results = await self.search_tasks(workspace_id, query)
                url_segment = "task"
            case _:
                self.log.error("Unknown HubSpot object_type=%s", object_type)
                return []

        # 2. Inject deep links
        integration = await self.storage.get_integration(workspace_id, Provider.HUBSPOT)
        portal_id = integration.portal_id if integration else None

        if results:
            for r in results:
                object_id = r.get("id")
                r["type"] = normalize_object_type(object_type)  # contacts -> contact

                if portal_id:
                    # Tasks and tickets use different URL patterns than
                    # contacts/deals/companies
                    if url_segment == "task":
                        r["hs_url"] = (
                            f"https://app.hubspot.com/tasks/{portal_id}/view/all?taskId={object_id}"
                        )
                    elif url_segment == "ticket":
                        r["hs_url"] = (
                            f"https://app.hubspot.com/contacts/{portal_id}/ticket/{object_id}"
                        )
                    else:
                        r["hs_url"] = (
                            f"https://app.hubspot.com/contacts/{portal_id}/"
                            f"{url_segment}/{object_id}"
                        )

        return results

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

    async def get_contact(
        self, workspace_id: str, object_id: str
    ) -> dict[str, Any] | None:
        client = await self.get_client(workspace_id=workspace_id)
        return await client.get_contact(object_id)

    async def get_deal(
        self, workspace_id: str, object_id: str
    ) -> dict[str, Any] | None:
        client = await self.get_client(workspace_id=workspace_id)
        return await client.get_deal(object_id)

    async def get_company(
        self, workspace_id: str, object_id: str
    ) -> dict[str, Any] | None:
        client = await self.get_client(workspace_id=workspace_id)
        return await client.get_company(object_id)

    async def get_object(
        self,
        *,
        workspace_id: str,
        object_type: str,
        object_id: str,
    ) -> Mapping[str, Any] | None:
        """Unified entry point to fetch any CRM object."""
        object_type = normalize_object_type(object_type)

        result = None
        match object_type:
            case "contact" | "lead":
                result = await self.get_contact(workspace_id, object_id)
            case "deal":
                result = await self.get_deal(workspace_id, object_id)
            case "company":
                result = await self.get_company(workspace_id, object_id)
            case "ticket":
                result = await self.get_ticket(workspace_id, object_id)
            case "task":
                result = await self.get_task(workspace_id, object_id)
            case _:
                self.log.error("Unknown object_type=%s for get_object", object_type)

        if result:
            result["type"] = object_type

        return result

    async def search_tickets(
        self,
        workspace_id: str,
        query: str,
    ) -> list[dict[str, Any]]:
        client = await self.get_client(workspace_id)
        return await client.search_tickets(query)

    async def search_tasks(
        self,
        workspace_id: str,
        query: str,
    ) -> list[dict[str, Any]]:
        client = await self.get_client(workspace_id)
        return await client.search_tasks(query)

    async def get_ticket(
        self, workspace_id: str, object_id: str
    ) -> dict[str, Any] | None:
        client = await self.get_client(workspace_id=workspace_id)
        return await client.get_ticket(object_id)

    async def get_task(
        self, workspace_id: str, object_id: str
    ) -> dict[str, Any] | None:
        client = await self.get_client(workspace_id=workspace_id)
        return await client.get_task(object_id)

    async def create_note(
        self,
        *,
        workspace_id: str,
        content: str,
        associated_id: str,
        associated_type: str,
    ) -> dict[str, Any]:
        """Wrapper to create a CRM note via HubSpotClient."""
        client = await self.get_client(workspace_id)
        return await client.create_note(
            content=content,
            associated_id=associated_id,
            associated_type=associated_type,
        )

    async def get_company_deals(
        self,
        workspace_id: str,
        company_id: str,
    ) -> list[dict[str, Any]]:
        """Fetch all deals associated with a company via batch read."""
        client = await self.get_client(workspace_id)

        # 1. Get associated deal IDs
        deal_ids = await client.get_associations("companies", company_id, "deals")
        if not deal_ids:
            return []

        # 2. Batch read all deals in one API call
        deals = await client.batch_read(
            "deals",
            deal_ids[:100],
            properties=["dealname", "amount", "pipeline", "dealstage"],
        )
        for deal in deals:
            deal["type"] = "deal"

        return deals

    async def get_company_contacts(
        self,
        workspace_id: str,
        company_id: str,
    ) -> list[dict[str, Any]]:
        """Fetch all contacts associated with a company via batch read."""
        client = await self.get_client(workspace_id)

        contact_ids = await client.get_associations("companies", company_id, "contacts")
        if not contact_ids:
            return []

        # Batch read all contacts in one API call
        contacts = await client.batch_read(
            "contacts",
            contact_ids[:100],
            properties=["firstname", "lastname", "email", "phone", "lifecyclestage"],
        )
        for contact in contacts:
            contact["type"] = "contact"

        return contacts
