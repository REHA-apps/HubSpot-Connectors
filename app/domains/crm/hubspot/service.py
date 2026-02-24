from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.core.exceptions import HubSpotAPIError, IntegrationNotFoundError
from app.core.logging import CorrelationAdapter, get_logger
from app.db.records import Provider
from app.db.storage_service import StorageService
from app.domains.crm.base import BaseCRMService
from app.providers.hubspot.client import HubSpotClient
from app.utils.cache import AsyncTTL
from app.utils.helpers import normalize_object_type

logger = get_logger("hubspot.service")


class HubSpotService(BaseCRMService):
    """Domain service coordinating high-level HubSpot business logic.

    Attributes:
        _PIPELINES_CACHE (AsyncTTL): Class-level cache for deal pipelines.
        _OWNERS_CACHE (AsyncTTL): Class-level cache for HubSpot owners.

    """

    _PIPELINES_CACHE = AsyncTTL(ttl=3600)  # Cache for 1 hour
    _OWNERS_CACHE = AsyncTTL(ttl=3600)  # Cache for 1 hour

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

        async def _handle_revocation() -> None:
            self.log.warning(
                "Reactive uninstallation triggered for workspace_id=%s", workspace_id
            )
            # Avoid circular import
            from app.domains.crm.integration_service import (  # noqa: PLC0415
                IntegrationService,
            )

            service = IntegrationService(self.corr_id, storage=self.storage)
            await service.uninstall_workspace(
                workspace_id, trigger_hubspot_uninstall=False
            )

        client.on_token_revoked = _handle_revocation

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
    ) -> list[dict[str, Any]]:
        """Unified HubSpot search entry point.

        Delegates to the correct search_* method based on object_type.

        Args:
            workspace_id: The workspace identifier.
            object_type: The CRM object type (e.g., 'contact', 'deal').
            query: The search query string.

        Returns:
            A list of matching HubSpot objects.

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

        return await self.inject_urls(workspace_id, results, url_segment)

    async def inject_urls(
        self,
        workspace_id: str,
        results: list[dict[str, Any]],
        object_type: str | None = None,
    ) -> list[dict[str, Any]]:
        """Injects `hs_url` deep links and standardizes `type` on a list of results."""
        if not results:
            return results

        integration = await self.storage.get_integration(workspace_id, Provider.HUBSPOT)
        portal_id = integration.portal_id if integration else None

        for r in results:
            obj_type = normalize_object_type(
                object_type.lower() if object_type else (r.get("type", "contact"))
            )
            r["type"] = obj_type
            object_id = r.get("id")

            if portal_id and object_id and not r.get("hs_url"):
                if obj_type == "task":
                    r["hs_url"] = (
                        f"https://app.hubspot.com/tasks/{portal_id}/view/all?taskId={object_id}"
                    )
                elif obj_type == "ticket":
                    r["hs_url"] = (
                        f"https://app.hubspot.com/contacts/{portal_id}/ticket/{object_id}"
                    )
                else:
                    r["hs_url"] = (
                        f"https://app.hubspot.com/contacts/{portal_id}/{obj_type}/{object_id}"
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
        result = await client.get_contact(object_id)
        if result:
            results = await self.inject_urls(workspace_id, [result], "contact")
            return results[0]
        return None

    async def get_deal(
        self, workspace_id: str, object_id: str
    ) -> dict[str, Any] | None:
        client = await self.get_client(workspace_id=workspace_id)
        result = await client.get_deal(object_id)
        if result:
            results = await self.inject_urls(workspace_id, [result], "deal")
            return results[0]
        return None

    async def get_company(
        self, workspace_id: str, object_id: str
    ) -> dict[str, Any] | None:
        client = await self.get_client(workspace_id=workspace_id)
        result = await client.get_company(object_id)
        if result:
            results = await self.inject_urls(workspace_id, [result], "company")
            return results[0]
        return None

    async def get_object(
        self,
        *,
        workspace_id: str,
        object_type: str,
        object_id: str,
    ) -> dict[str, Any] | None:
        """Unified entry point to fetch any CRM object.

        Args:
            workspace_id: The workspace identifier.
            object_type: The HubSpot object type.
            object_id: The specific record ID.

        Returns:
            The object data or None if not found.

        """
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
            case "conversation" | "thread":
                client = await self.get_client(workspace_id)
                result = await client.get_inbox_thread(object_id)
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

    async def send_thread_reply(
        self,
        workspace_id: str,
        thread_id: str,
        text: str,
    ) -> dict[str, Any]:
        """Sends a reply to a conversation thread.

        Args:
            workspace_id (str): The workspace identifier.
            thread_id (str): The conversation thread ID.
            text (str): The reply text.

        Returns:
            dict[str, Any]: The created message object.

        """
        client = await self.get_client(workspace_id)
        return await client.create_inbox_message(
            thread_id=thread_id,
            text=text,
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

        return await self.inject_urls(workspace_id, deals, "deal")

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

        return await self.inject_urls(workspace_id, contacts, "contact")

    async def get_contact_deals(
        self,
        workspace_id: str,
        contact_id: str,
    ) -> list[dict[str, Any]]:
        """Fetch all deals associated with a contact via batch read."""
        client = await self.get_client(workspace_id)

        deal_ids = await client.get_associations("contacts", contact_id, "deals")
        if not deal_ids:
            return []

        deals = await client.batch_read(
            "deals",
            deal_ids[:100],
            properties=["dealname", "amount", "pipeline", "dealstage"],
        )
        for deal in deals:
            deal["type"] = "deal"

        return await self.inject_urls(workspace_id, deals, "deal")

    async def get_contact_companies(
        self,
        workspace_id: str,
        contact_id: str,
    ) -> list[dict[str, Any]]:
        """Fetch all companies associated with a contact via batch read."""
        client = await self.get_client(workspace_id)

        company_ids = await client.get_associations("contacts", contact_id, "companies")
        if not company_ids:
            return []

        companies = await client.batch_read(
            "companies",
            company_ids[:100],
            properties=[
                "name",
                "domain",
                "industry",
                "num_associated_contacts",
                "num_associated_deals",
            ],
        )
        for co in companies:
            co["type"] = "company"

        return await self.inject_urls(workspace_id, companies, "company")

    async def get_deal_pipelines(self, workspace_id: str) -> list[dict[str, Any]]:
        """Fetch deal pipelines with global TTL caching.

        Args:
            workspace_id (str): The workspace identifier.

        Returns:
            list[dict[str, Any]]: A list of deal pipelines.

        """
        key = f"pipelines:{workspace_id}"

        async def _fetch():
            client = await self.get_client(workspace_id)
            return await client.get_deal_pipelines()

        return await self._PIPELINES_CACHE.get_or_fetch(key, _fetch)

    async def update_deal(
        self,
        workspace_id: str,
        deal_id: str,
        properties: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Update a deal's properties."""
        client = await self.get_client(workspace_id)
        return await client.update_deal(deal_id, properties)

    async def update_contact(
        self,
        workspace_id: str,
        contact_id: str,
        properties: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Update a contact's properties."""
        client = await self.get_client(workspace_id)
        return await client.update_contact(contact_id, properties)

    async def update_company(
        self,
        workspace_id: str,
        company_id: str,
        properties: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Update a company's properties."""
        client = await self.get_client(workspace_id)
        return await client.update_company(company_id, properties)

    async def get_owners(self, workspace_id: str) -> list[dict[str, Any]]:
        """Fetch owners with global TTL caching.

        Args:
            workspace_id (str): The workspace identifier.

        Returns:
            list[dict[str, Any]]: A list of HubSpot owners.

        """
        key = f"owners:{workspace_id}"

        async def _fetch():
            client = await self.get_client(workspace_id)
            return await client.get_owners()

        return await self._OWNERS_CACHE.get_or_fetch(key, _fetch)

    async def enrich_task(
        self,
        workspace_id: str,
        task: dict[str, Any],
    ) -> dict[str, Any]:
        """Fetch additional context for a task (owner name, associations)."""
        client = await self.get_client(workspace_id)
        props = task.get("properties", {})
        context = {
            "owner_name": "Unassigned",
            "contacts": [],
            "companies": [],
        }

        # 1. Resolve Owner Name
        owner_id = props.get("hubspot_owner_id")
        if owner_id:
            owners = await self.get_owners(workspace_id)
            owner = next((o for o in owners if o["id"] == owner_id), None)
            if owner:
                first = owner.get("firstName", "")
                last = owner.get("lastName", "")
                context["owner_name"] = f"{first} {last}".strip() or owner.get(
                    "email", "Unknown"
                )

        # 2. Fetch Associated Contacts
        contact_ids = await client.get_associations("tasks", task["id"], "contacts")
        if contact_ids:
            contacts = await client.batch_read(
                "contacts", contact_ids, properties=["firstname", "lastname", "email"]
            )
            for c in contacts:
                c_props = c.get("properties", {})
                name = (
                    f"{c_props.get('firstname', '')} {c_props.get('lastname', '')}"
                ).strip()
                email = c_props.get("email")
                context["contacts"].append(name or email or "Unknown Contact")

        # 3. Fetch Associated Companies
        company_ids = await client.get_associations("tasks", task["id"], "companies")
        if company_ids:
            companies = await client.batch_read(
                "companies", company_ids, properties=["name", "domain"]
            )
            for c in companies:
                c_props = c.get("properties", {})
                name = c_props.get("name") or c_props.get("domain") or "Unknown Company"
                context["companies"].append(name)

        return context

    async def get_contact_meetings(
        self,
        workspace_id: str,
        contact_id: str,
    ) -> list[dict[str, Any]]:
        """Fetch all meetings associated with a contact via batch read."""
        client = await self.get_client(workspace_id)

        meeting_ids = await client.get_associations("contacts", contact_id, "meetings")
        if not meeting_ids:
            return []

        meetings = await client.batch_read(
            "meetings",
            meeting_ids[:100],
            properties=[
                "hs_meeting_title",
                "hs_meeting_start_time",
                "hs_meeting_end_time",
                "hs_meeting_outcome",
            ],
        )
        for meeting in meetings:
            meeting["type"] = "meeting"

        return meetings

    async def get_meeting(
        self, workspace_id: str, object_id: str
    ) -> dict[str, Any] | None:
        client = await self.get_client(workspace_id=workspace_id)
        return await client.get_meetings(object_id)

    async def update_meeting(
        self,
        workspace_id: str,
        meeting_id: str,
        properties: Mapping[str, Any],
    ) -> dict[str, Any]:
        """Update a meeting's properties."""
        client = await self.get_client(workspace_id)
        return await client.request(
            "PATCH", f"objects/meetings/{meeting_id}", json={"properties": properties}
        )

    async def create_meeting(
        self,
        workspace_id: str,
        properties: Mapping[str, Any],
        contact_id: str | None = None,
    ) -> dict[str, Any]:
        """Create a meeting and optionally associate it with a contact."""
        client = await self.get_client(workspace_id)

        associations = None
        if contact_id:
            # Association Type ID for Meeting -> Contact is 200
            # (Note -> Contact is 202)
            associations = [
                {
                    "to": {"id": contact_id},
                    "types": [
                        {
                            "associationCategory": "HUBSPOT_DEFINED",
                            "associationTypeId": 200,
                        }
                    ],
                }
            ]

        return await client.create_object("meetings", properties, associations)

    async def uninstall_app(self, workspace_id: str) -> None:
        """Description:
        Uninstalls the app from the HubSpot account.
        """
        client = await self.get_client(workspace_id)
        await client.uninstall_app()
