from __future__ import annotations

from collections.abc import Mapping
from typing import Any, cast

from app.core.exceptions import IntegrationNotFoundError
from app.core.logging import get_logger
from app.db.records import Provider
from app.db.storage_service import StorageService
from app.domains.crm.base import BaseCRMService
from app.providers.hubspot.client import HubSpotClient
from app.utils.cache import AsyncTTL
from app.utils.helpers import normalize_object_type, pluralize_hs_type

logger = get_logger("hubspot.service")


class HubSpotService(BaseCRMService):
    """Domain service coordinating high-level HubSpot business logic.

    Attributes:
        _PIPELINES_CACHE (AsyncTTL): Class-level cache for deal pipelines.
        _OWNERS_CACHE (AsyncTTL): Class-level cache for HubSpot owners.

    """

    _PIPELINES_CACHE = AsyncTTL(ttl=3600)  # Cache for 1 hour
    _OWNERS_CACHE = AsyncTTL(ttl=3600)  # Cache for 1 hour
    _ENGAGEMENTS_CACHE = AsyncTTL(ttl=300)  # Cache engagements for 5 mins
    _ASSOCIATIONS_CACHE = AsyncTTL(ttl=300)  # Cache associations for 5 mins

    def __init__(self, corr_id: str, *, storage: StorageService | None = None) -> None:
        self.corr_id = corr_id
        self.storage = storage or StorageService(corr_id=corr_id)
        # Per-instance client cache: avoids re-fetching tokens from
        # Supabase on every method call within the same request.
        self._client_cache: dict[str, HubSpotClient] = {}

    # Client lifecycle
    async def get_client(self, workspace_id: str) -> HubSpotClient:
        """Builds or returns a cached HubSpotClient for this workspace."""
        if workspace_id in self._client_cache:
            return self._client_cache[workspace_id]

        integration = await self.storage.get_integration(
            workspace_id=workspace_id,
            provider=Provider.HUBSPOT,
        )

        if not integration:
            raise IntegrationNotFoundError(
                f"No HubSpot integration for workspace {workspace_id}"
            )

        client = HubSpotClient(
            access_token=integration.access_token or "",
            refresh_token=integration.refresh_token,
            corr_id=self.corr_id,
        )

        async def _handle_refresh(new_at: str, new_rt: str | None) -> None:
            await self.persist_tokens(
                workspace_id=integration.workspace_id,
                new_access=new_at,
                new_refresh=new_rt,
            )

        client.on_token_refresh = _handle_refresh

        async def _handle_revocation() -> None:
            from app.domains.crm.integration_service import IntegrationService

            service = IntegrationService(self.corr_id, storage=self.storage)
            await service.uninstall_workspace(
                integration.workspace_id, trigger_hubspot_uninstall=False
            )

        client.on_token_revoked = _handle_revocation

        self._client_cache[workspace_id] = client
        return client

    # Persistence logic
    async def persist_tokens(
        self,
        workspace_id: str,
        new_access: str,
        new_refresh: str | None,
    ) -> None:
        """Persists rotated tokens to storage."""
        integration = await self.storage.get_integration(workspace_id, Provider.HUBSPOT)
        if not integration:
            logger.error(
                "No integration found to persist tokens for workspace %s", workspace_id
            )
            return

        credentials = dict(integration.credentials or {})
        credentials["access_token"] = new_access
        if new_refresh:
            credentials["refresh_token"] = new_refresh

        await self.storage.upsert_integration(
            {
                "id": integration.id,
                "workspace_id": workspace_id,
                "provider": Provider.HUBSPOT,
                "credentials": credentials,
                "metadata": integration.metadata,
            }
        )

    # Domain operations
    async def search(
        self,
        *,
        workspace_id: str,
        object_type: str,
        query: str,
    ) -> list[dict[str, Any]]:
        """Unified HubSpot search entry point."""
        object_type = object_type.lower()
        match object_type:
            case "contacts" | "contact" | "leads" | "lead":
                results = await self.search_contacts(workspace_id, query)
                url_segment = "contact"
            case "deals" | "deal":
                results = await self._search_by_type(workspace_id, "deals", query)
                url_segment = "deal"
            case "companies" | "company":
                results = await self._search_by_type(workspace_id, "companies", query)
                url_segment = "company"
            case "tickets" | "ticket":
                results = await self._search_by_type(workspace_id, "tickets", query)
                url_segment = "ticket"
            case "tasks" | "task":
                results = await self._search_by_type(workspace_id, "tasks", query)
                url_segment = "task"
            case _:
                logger.error("Unknown HubSpot object_type=%s", object_type)
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
        self, workspace_id: str, query: str
    ) -> list[dict[str, Any]]:
        client = await self.get_client(workspace_id)
        return await client.search_contacts(query)

    async def _search_by_type(
        self, workspace_id: str, object_type: str, query: str
    ) -> list[dict[str, Any]]:
        client = await self.get_client(workspace_id)
        return await client.search_objects(
            object_type,
            query_string=query,
            properties=client._SEARCH_PROPS.get(object_type, []),
        )

    async def create_contact(
        self, workspace_id: str, properties: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        client = await self.get_client(workspace_id)
        return await client.create_contact(properties)

    async def create_task(
        self, workspace_id: str, properties: Mapping[str, Any]
    ) -> Mapping[str, Any]:
        client = await self.get_client(workspace_id)
        return await client.create_task(properties)

    async def associate_object(
        self,
        workspace_id: str,
        from_type: str,
        from_id: str,
        to_type: str,
        to_id: str,
    ) -> None:
        """Associate two CRM objects using HubSpot defined types."""
        client = await self.get_client(workspace_id)

        # In HubSpot v3, the type string "{fromObjectType}_to_{toObjectType}"
        # is the most reliable way to create standard associations
        type_val = f"{from_type}_to_{to_type}"

        await client.request(
            "POST",
            f"associations/{from_type}/{to_type}/batch/create",
            json={
                "inputs": [
                    {
                        "from": {"id": from_id},
                        "to": {"id": to_id},
                        "type": type_val,
                    }
                ]
            },
        )

    async def get_contact(
        self,
        workspace_id: str,
        object_id: str,
        associations: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """Retrieves a single contact from HubSpot."""
        client = await self.get_client(workspace_id=workspace_id)
        result = await client.get_object(
            "contacts",
            object_id,
            properties=[
                "firstname",
                "lastname",
                "email",
                "phone",
                "lifecyclestage",
                "company",
                "hubspot_owner_id",
            ],
            associations=associations,
        )
        if result:
            results = await self.inject_urls(workspace_id, [result], "contact")
            res = results[0]
            res["workspace_id"] = workspace_id
            return res
        return None

    async def get_object_engagements(
        self,
        workspace_id: str,
        object_type: str,
        object_id: str,
    ) -> list[dict[str, Any]]:
        """Fetches all engagements associated with a CRM object."""
        key = f"engagements:{workspace_id}:{object_type}:{object_id}"

        async def _fetch():
            client = await self.get_client(workspace_id=workspace_id)
            hs_type = pluralize_hs_type(object_type)
            engagements = []
            entities = {
                "notes": ["hs_note_body", "hs_timestamp"],
                "emails": ["hs_email_subject", "hs_email_text", "hs_timestamp"],
                "meetings": [
                    "hs_meeting_title",
                    "hs_meeting_body",
                    "hs_meeting_start_time",
                    "hs_meeting_end_time",
                    "hs_meeting_outcome",
                ],
                "calls": [
                    "hs_call_title",
                    "hs_call_body",
                    "hs_call_status",
                    "hs_timestamp",
                ],
                "tasks": [
                    "hs_task_subject",
                    "hs_task_body",
                    "hs_task_status",
                    "hs_task_priority",
                    "hs_timestamp",
                ],
            }
            for entity_type, props in entities.items():
                try:
                    assoc_ids = await client.get_associations(
                        hs_type, object_id, entity_type
                    )
                    if assoc_ids:
                        details = await client.batch_read(
                            entity_type, assoc_ids, properties=props
                        )
                        for d in details:
                            d["_engagement_type"] = entity_type
                            engagements.append(d)
                except Exception as e:
                    logger.error(
                        "Failed to fetch %s engagements for %s %s: %s",
                        entity_type,
                        object_type,
                        object_id,
                        e,
                    )
            return engagements

        return await self._ENGAGEMENTS_CACHE.get_or_fetch(key, _fetch)

    async def get_deal(
        self,
        workspace_id: str,
        object_id: str,
        associations: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """Retrieves a single deal from HubSpot."""
        client = await self.get_client(workspace_id=workspace_id)
        result = await client.get_object(
            "deals",
            object_id,
            properties=[
                "dealname",
                "amount",
                "pipeline",
                "dealstage",
                "hs_next_step",
                "hubspot_owner_id",
            ],
            associations=associations,
        )
        if result:
            results = await self.inject_urls(workspace_id, [result], "deal")
            res = results[0]
            res["workspace_id"] = workspace_id
            return res
        return None

    async def get_company(
        self, workspace_id: str, object_id: str
    ) -> dict[str, Any] | None:
        client = await self.get_client(workspace_id=workspace_id)
        result = await client.get_company(object_id)
        if result:
            results = await self.inject_urls(workspace_id, [result], "company")
            res = results[0]
            res["workspace_id"] = workspace_id
            return res
        return None

    async def get_object(
        self,
        *,
        workspace_id: str,
        object_type: str,
        object_id: str,
        associations: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """Unified entry point to fetch any CRM object."""
        object_type = normalize_object_type(object_type)
        result = None
        match object_type:
            case "contact":
                result = await self.get_contact(workspace_id, object_id, associations)
            case "company":
                result = await self.get_company(workspace_id, object_id)
            case "deal":
                result = await self.get_deal(workspace_id, object_id, associations)
            case "ticket":
                result = await self.get_ticket(workspace_id, object_id)
            case "task":
                result = await self.get_task(workspace_id, object_id)
            case "meeting":
                result = await self.get_meeting(workspace_id, object_id)
            case "note":
                result = await self.get_note(workspace_id, object_id)
            case "call":
                result = await self.get_call(workspace_id, object_id)
            case "email":
                result = await self.get_email(workspace_id, object_id)
            case "lead":
                result = await self.get_lead(workspace_id, object_id)
            case "conversation" | "thread":
                client = await self.get_client(workspace_id)
                result = await client.get_inbox_thread(object_id)
            case _:
                logger.error("Unknown object_type=%s for get_object", object_type)

        if result:
            result["type"] = object_type
        return result

    async def get_ticket(
        self, workspace_id: str, object_id: str
    ) -> dict[str, Any] | None:
        client = await self.get_client(workspace_id=workspace_id)
        result = await client.get_ticket(object_id)
        if result:
            result["workspace_id"] = workspace_id
        return result

    async def get_task(
        self, workspace_id: str, object_id: str
    ) -> dict[str, Any] | None:
        client = await self.get_client(workspace_id=workspace_id)
        result = await client.get_task(object_id)
        if result:
            result["workspace_id"] = workspace_id
        return result

    async def get_meeting(
        self, workspace_id: str, object_id: str
    ) -> dict[str, Any] | None:
        client = await self.get_client(workspace_id=workspace_id)
        result = await client.get_meeting(object_id)
        if result:
            result["workspace_id"] = workspace_id
        return result

    async def get_note(
        self, workspace_id: str, object_id: str
    ) -> dict[str, Any] | None:
        client = await self.get_client(workspace_id=workspace_id)
        result = await client.get_note(object_id)
        if result:
            result["workspace_id"] = workspace_id
        return result

    async def get_call(
        self, workspace_id: str, object_id: str
    ) -> dict[str, Any] | None:
        client = await self.get_client(workspace_id=workspace_id)
        result = await client.get_call(object_id)
        if result:
            result["workspace_id"] = workspace_id
        return result

    async def get_email(
        self, workspace_id: str, object_id: str
    ) -> dict[str, Any] | None:
        client = await self.get_client(workspace_id=workspace_id)
        result = await client.get_email(object_id)
        if result:
            result["workspace_id"] = workspace_id
        return result

    async def get_lead(
        self, workspace_id: str, object_id: str
    ) -> dict[str, Any] | None:
        client = await self.get_client(workspace_id=workspace_id)
        result = await client.get_lead(object_id)
        if result:
            result["workspace_id"] = workspace_id
        return result

    async def create_note(
        self,
        *,
        workspace_id: str,
        content: str,
        associated_id: str,
        associated_type: str,
    ) -> dict[str, Any]:
        """Creates a note in HubSpot and associates it with a CRM object."""
        client = await self.get_client(workspace_id)
        return await client.create_note(
            content=content,
            associated_id=associated_id,
            associated_type=associated_type,
        )

    async def publish_app_event(
        self,
        workspace_id: str,
        event_template_id: str,
        object_type: str,
        object_id: str,
        properties: dict[str, str],
    ) -> None:
        """Logs a custom app event to a record's timeline."""
        try:
            client = await self.get_client(workspace_id)
            await client.create_app_event(
                event_template_id=event_template_id,
                object_id=object_id,
                tokens=properties,
            )
        except Exception as e:
            logger.warning("Failed to publish app event: %s", e)

    async def send_thread_reply(
        self, workspace_id: str, thread_id: str, text: str
    ) -> dict[str, Any]:
        client = await self.get_client(workspace_id)
        return await client.create_inbox_message(thread_id=thread_id, text=text)

    async def get_associated_objects(
        self,
        workspace_id: str,
        from_object_type: str,
        object_id: str,
        to_object_type: str,
    ) -> list[dict[str, Any]]:
        """Generic method to fetch and batch read any associated object type."""
        key = f"assoc:{workspace_id}:{from_object_type}:{object_id}:{to_object_type}"

        async def _fetch():
            client = await self.get_client(workspace_id)
            props = []
            target_name = "name"
            if to_object_type == "contacts":
                props = ["firstname", "lastname", "email", "phone", "lifecyclestage"]
                target_name = "contact"
            elif to_object_type == "deals":
                props = ["dealname", "amount", "pipeline", "dealstage"]
                target_name = "deal"
            elif to_object_type == "companies":
                props = ["name", "domain", "industry"]
                target_name = "company"
            elif to_object_type == "tickets":
                props = ["subject", "hs_ticket_priority", "hs_ticket_category"]
                target_name = "ticket"

            assoc_ids = await client.get_associations(
                from_object_type, object_id, to_object_type
            )
            if not assoc_ids:
                return []
            objects = await client.batch_read(
                to_object_type, assoc_ids[:100], properties=props
            )
            for obj in objects:
                obj["type"] = target_name
            return await self.inject_urls(workspace_id, objects, target_name)

        return await self._ASSOCIATIONS_CACHE.get_or_fetch(key, _fetch)

    async def get_all_associations(
        self, workspace_id: str, object_type: str, object_id: str
    ) -> dict[str, list[dict[str, Any]]]:
        """Fetch all primary associations for an object.
        Consolidates multiple association ID lookups into a single
        object fetch to improve performance.
        """
        targets = ["contacts", "companies", "deals", "tickets"]
        hs_type = normalize_object_type(object_type)
        if hs_type in targets:
            targets.remove(hs_type)
        if hs_type == "contact" and "contacts" in targets:
            targets.remove("contacts")

        target_map = {t: t for t in targets}
        obj = await self.get_object(
            workspace_id=workspace_id,
            object_type=hs_type,
            object_id=object_id,
            associations=targets,
        )

        if not obj or "associations" not in obj:
            return {t: [] for t in targets}

        import asyncio

        async def _fetch_details(plural_type: str, assoc_data: dict[str, Any]):
            client = await self.get_client(workspace_id)
            results = assoc_data.get("results", [])
            ids = [r["id"] for r in results]
            if not ids:
                return []

            props = []
            target_name = "contact"
            if plural_type == "contacts":
                props = ["firstname", "lastname", "email", "phone", "lifecyclestage"]
                target_name = "contact"
            elif plural_type == "deals":
                props = ["dealname", "amount", "pipeline", "dealstage"]
                target_name = "deal"
            elif plural_type == "companies":
                props = ["name", "domain", "industry"]
                target_name = "company"
            elif plural_type == "tickets":
                props = ["subject", "hs_ticket_priority", "hs_ticket_category"]
                target_name = "ticket"

            objects = await client.batch_read(plural_type, ids[:100], properties=props)
            for o in objects:
                o["type"] = target_name
            return await self.inject_urls(workspace_id, objects, target_name)

        tasks = {}
        for target, plural in target_map.items():
            if target in obj["associations"]:
                tasks[target] = _fetch_details(plural, obj["associations"][target])

        results = await asyncio.gather(*tasks.values(), return_exceptions=True)
        final_associations = {t: [] for t in targets}
        for target, res in zip(tasks.keys(), results, strict=False):
            if isinstance(res, Exception):
                logger.error(f"Failed to fetch {target} details: {res}")
            else:
                final_associations[target] = cast(list[dict[str, Any]], res)

        return final_associations

    async def get_deal_pipelines(self, workspace_id: str) -> list[dict[str, Any]]:
        key = f"pipelines:{workspace_id}"

        async def _fetch():
            client = await self.get_client(workspace_id)
            return await client.get_deal_pipelines()

        return await self._PIPELINES_CACHE.get_or_fetch(key, _fetch)

    async def update_deal(
        self, workspace_id: str, deal_id: str, properties: Mapping[str, Any]
    ) -> dict[str, Any]:
        client = await self.get_client(workspace_id)
        return await client.update_deal(deal_id, properties)

    async def update_contact(
        self, workspace_id: str, contact_id: str, properties: Mapping[str, Any]
    ) -> dict[str, Any]:
        client = await self.get_client(workspace_id)
        return await client.update_contact(contact_id, properties)

    async def update_company(
        self, workspace_id: str, company_id: str, properties: Mapping[str, Any]
    ) -> dict[str, Any]:
        client = await self.get_client(workspace_id)
        return await client.update_company(company_id, properties)

    async def get_owners(self, workspace_id: str) -> list[dict[str, Any]]:
        key = f"owners:{workspace_id}"

        async def _fetch():
            client = await self.get_client(workspace_id)
            return await client.get_owners()

        return await self._OWNERS_CACHE.get_or_fetch(key, _fetch)

    async def enrich_task(
        self, workspace_id: str, task: dict[str, Any]
    ) -> dict[str, Any]:
        props = task.get("properties", {})
        context = {"owner_name": "Unassigned", "contacts": [], "companies": []}
        owner_id = props.get("hubspot_owner_id")
        if owner_id:
            owners = await self.get_owners(workspace_id)
            owner = next((o for o in owners if o["id"] == owner_id), None)
            if owner:
                context["owner_name"] = (
                    f"{owner.get('firstName', '')} {owner.get('lastName', '')}".strip()
                    or owner.get("email", "Unknown")
                )

        assoc_contacts = await self.get_associated_objects(
            workspace_id, "tasks", task["id"], "contacts"
        )
        for c in assoc_contacts:
            c_props = c.get("properties", {})
            name = (
                f"{c_props.get('firstname', '')} {c_props.get('lastname', '')}".strip()
            )
            context["contacts"].append(
                name or c_props.get("email") or "Unknown Contact"
            )

        assoc_companies = await self.get_associated_objects(
            workspace_id, "tasks", task["id"], "companies"
        )
        for c in assoc_companies:
            c_props = c.get("properties", {})
            context["companies"].append(
                c_props.get("name") or c_props.get("domain") or "Unknown Company"
            )
        return context

    async def get_contact_meetings(
        self, workspace_id: str, contact_id: str
    ) -> list[dict[str, Any]]:
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

    async def update_meeting(
        self, workspace_id: str, meeting_id: str, properties: Mapping[str, Any]
    ) -> dict[str, Any]:
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
        client = await self.get_client(workspace_id)
        associations = None
        if contact_id:
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
        client = await self.get_client(workspace_id)
        await client.uninstall_app()
