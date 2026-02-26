from __future__ import annotations

from collections.abc import Awaitable, Callable, Mapping
from typing import Any

import httpx

from app.core.base_client import BaseClient
from app.core.config import settings
from app.core.logging import CorrelationAdapter, get_logger
from app.utils.constants import ErrorCode

logger = get_logger("hubspot.client")

type TokenRefreshCallback = Callable[[str, str | None], Awaitable[None]]
type TokenRevocationCallback = Callable[[], Awaitable[None]]


class HubSpotClient(BaseClient):
    """Description:
        Asynchronous HTTP client for interacting with the HubSpot CRM v3 API.

    Rules Applied:
        - Automatically handles OAuth token refreshing upon 401 Unauthorized responses.
        - Provides typed convenience methods for common CRM object operations.
        - Incorporates correlation-aware logging for all API interactions.
    """

    # HubSpot Note Association Type IDs (Note → Object)
    _NOTE_ASSOC_TYPE_IDS: dict[str, int] = {
        "contact": 202,
        "deal": 214,
        "company": 190,
        "ticket": 228,
        "task": 204,
    }

    # Centralized search properties registry
    _SEARCH_PROPS: dict[str, list[str]] = {
        "contacts": [
            "email",
            "firstname",
            "lastname",
            "company",
            "lifecyclestage",
            "hs_analytics_num_visits",
            "hs_additional_emails",
            "phone",
            "mobilephone",
        ],
        "deals": ["dealname", "amount", "dealstage", "pipeline"],
        "leads": [
            "firstname",
            "lastname",
            "email",
            "company",
            "lifecyclestage",
            "hs_lead_status",
            "phone",
        ],
        "companies": [
            "name",
            "domain",
            "industry",
            "city",
            "state",
            "country",
            "lifecyclestage",
            "num_associated_contacts",
            "num_associated_deals",
            "hs_analytics_num_page_views",
            "hs_analytics_num_visits",
        ],
        "tickets": [
            "subject",
            "content",
            "hs_pipeline_stage",
            "hs_ticket_priority",
            "createdate",
            "hs_ticket_category",
        ],
        "tasks": [
            "hs_task_subject",
            "hs_task_body",
            "hs_task_status",
            "hs_task_priority",
            "hs_task_type",
            "hs_timestamp",
        ],
        "meetings": [
            "hs_meeting_title",
            "hs_meeting_body",
            "hs_meeting_start_time",
            "hs_meeting_end_time",
            "hs_meeting_outcome",
        ],
    }

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
        self.on_token_refresh: TokenRefreshCallback | None = None

        self.on_token_revoked: TokenRevocationCallback | None = None

        super().__init__(
            base_url="https://api.hubapi.com/crm/v3",
            headers=self._headers(access_token),
            corr_id=corr_id,
        )

        self.log = CorrelationAdapter(logger, self.corr_id)

    # API request orchestration
    async def request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> Any:
        """Makes an HTTP request to the HubSpot API, handling token refresh if needed.

        Args:
            method (str): The HTTP method (e.g., "GET", "POST").
            path (str): The API endpoint path.
            params (Mapping[str, Any] | None): Optional query parameters.
            json (Mapping[str, Any] | None): Optional JSON body for the request.
            data (Mapping[str, Any] | None): Optional form data for the request.

        Returns:
            Any: The JSON response from the API, or None for 404 GET requests.

        Raises:
            httpx.HTTPStatusError: If the request fails with a non-2xx status code
                                   after potential token refresh.

        """
        try:
            return await self._raw_request(
                method,
                path,
                params=params,
                json=json,
                data=data,
            )

        except httpx.HTTPStatusError as exc:
            if (
                exc.response.status_code == ErrorCode.UNAUTHORIZED
                and self.refresh_token
            ):
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

    # Low-level request handling
    async def _raw_request(
        self,
        method: str,
        path: str,
        *,
        params: Mapping[str, Any] | None = None,
        json: Mapping[str, Any] | None = None,
        data: Mapping[str, Any] | None = None,
    ) -> Any:
        """Executes a raw HTTP request to the HubSpot API.

        Args:
            method (str): The HTTP method (e.g., "GET", "POST").
            path (str): The API endpoint path. Can be a full URL or relative path.
            params (Mapping[str, Any] | None): Optional query parameters.
            json (Mapping[str, Any] | None): Optional JSON body for the request.
            data (Mapping[str, Any] | None): Optional form data for the request.

        Returns:
            Any: The JSON response from the API, or None for 404 GET requests.

        Raises:
            httpx.HTTPStatusError: If the request fails with a non-2xx status code.
            ValueError: If the response is not valid JSON.

        """
        if path.startswith("http"):
            url = path
        else:
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

        if method.upper() == "GET" and response.status_code == ErrorCode.NOT_FOUND:
            self.log.info("HubSpot GET %s returned 404 (None)", url)
            return None

        if response.status_code >= ErrorCode.BAD_REQUEST:
            self.log.error("HubSpot error %s: %s", response.status_code, response.text)
            response.raise_for_status()

        response.raise_for_status()

        try:
            return response.json()
        except ValueError:
            self.log.error("Invalid JSON response from HubSpot: %s", response.text)
            raise

    # OAuth token refresh
    async def _refresh_token(self) -> dict[str, str] | None:
        """Attempts to refresh the HubSpot access token using the refresh token.

        Returns:
            dict[str, str] | None: A dictionary containing the new 'access_token'
                and 'refresh_token' if successful, or None otherwise.

        """
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

            # Detect revocation (user uninstalled app from HubSpot portal)
            if resp.status_code == ErrorCode.BAD_REQUEST:
                try:
                    error_data = resp.json()
                    if error_data.get("error") == "invalid_grant":
                        self.log.warning(
                            "HubSpot token revoked (invalid_grant); triggering callback"
                        )
                        if self.on_token_revoked:
                            result = self.on_token_revoked()
                            if isinstance(result, Awaitable):
                                await result
                except Exception as exc:
                    self.log.error("Failed to parse HubSpot refresh error: %s", exc)

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

    # Generic CRM operations
    async def create_object(
        self,
        object_type: str,
        properties: Mapping[str, Any],
        associations: list[dict[str, Any]] | None = None,
    ) -> dict[str, Any]:
        """Generic object creation with optional associations."""
        payload: dict[str, Any] = {"properties": properties}
        if associations:
            payload["associations"] = associations

        return await self.request(
            "POST",
            f"objects/{object_type}",
            json=payload,
        )

    async def create_note(
        self,
        content: str,
        associated_id: str,
        associated_type: str,
    ) -> dict[str, Any]:
        """Creates a CRM note and associates it with a contact, deal, or company."""
        type_id = self._NOTE_ASSOC_TYPE_IDS.get(associated_type.lower(), 202)  # noqa: PLR2004

        from datetime import UTC, datetime

        from app.utils.transformers import to_hubspot_timestamp

        properties = {
            "hs_note_body": content,
            "hs_timestamp": to_hubspot_timestamp(
                datetime.now(UTC), corr_id=self.corr_id
            ),
        }

        associations = [
            {
                "to": {"id": associated_id},
                "types": [
                    {
                        "associationCategory": "HUBSPOT_DEFINED",
                        "associationTypeId": type_id,
                    }
                ],
            }
        ]

        return await self.create_object("notes", properties, associations)

    async def get_object(
        self,
        object_type: str,
        object_id: str,
        properties: list[str] | None = None,
    ) -> dict[str, Any] | None:
        """Generic object retrieval."""
        path = f"objects/{object_type}/{object_id}"
        if properties:
            path += f"?properties={','.join(properties)}"
        return await self.request("GET", path)

    async def search_objects(
        self,
        object_type: str,
        filters: list[dict[str, Any]] | None = None,
        filter_groups: list[dict[str, Any]] | None = None,
        properties: list[str] | None = None,
        limit: int = 5,
        query_string: str | None = None,
    ) -> list[dict[str, Any]]:
        """Generic CRM v3 search."""
        # If query_string is provided, use it for broad "query" search (smart match)
        # Note: If filters/filterGroups are also provided, HubSpot API might
        # ignore query or combine them.
        # But for our use case, we usually want EITHER smart query OR specific filters.

        groups = []
        if filter_groups:
            groups = filter_groups
        elif filters:
            groups = [{"filters": filters}]

        payload: dict[str, Any] = {
            "limit": limit,
            "properties": properties or [],
        }

        if query_string:
            payload["query"] = query_string
        elif groups:
            payload["filterGroups"] = groups

        # If neither query nor filters provided, empty search.
        # Search API requires at least one condition usually.
        # But an empty query string "" might return recent.

        try:
            resp = await self.request(
                "POST", f"objects/{object_type}/search", json=payload
            )
        except Exception as exc:
            # Gracefully handle 403 (missing scopes) and other API errors
            exc_str = str(exc)
            if "403" in exc_str or "MISSING_SCOPES" in exc_str:
                self.log.warning(
                    "Missing HubSpot scopes for %s search — skipping. "
                    "Re-install the app to grant required permissions.",
                    object_type,
                )
                return []
            raise
        return resp.get("results", [])

    # Convenience object helpers
    async def get_contact(self, object_id: str) -> dict[str, Any] | None:
        return await self.get_object(
            "contacts",
            object_id,
            properties=[
                "firstname",
                "lastname",
                "email",
                "phone",
                "mobilephone",
                "lifecyclestage",
                "company",
            ],
        )

    async def get_deal(self, object_id: str) -> dict[str, Any] | None:
        return await self.get_object(
            "deals",
            object_id,
            properties=["dealname", "amount", "pipeline", "dealstage", "hs_next_step"],
        )

    async def get_company(self, object_id: str) -> dict[str, Any] | None:
        return await self.get_object(
            "companies",
            object_id,
            properties=[
                "name",
                "domain",
                "industry",
                "num_associated_contacts",
                "num_associated_deals",
                "hs_analytics_num_page_views",
                "hs_analytics_num_visits",
            ],
        )

    async def create_contact(self, properties: Mapping[str, Any]) -> dict[str, Any]:
        return await self.create_object("contacts", properties)

    async def create_task(self, properties: Mapping[str, Any]) -> dict[str, Any]:
        return await self.create_object("tasks", properties)

    # Contact search logic
    async def search_contacts(self, query: str) -> list[dict[str, Any]]:
        q = query.strip().lower()

        # 1. Try CRM search first
        results = await self.search_objects(
            "contacts", query_string=q, properties=self._SEARCH_PROPS["contacts"]
        )

        if results:
            return results

        # 2. Fallback: identity profile lookup (email → contactId)
        try:
            identity_resp = await self.request(
                "GET",
                f"objects/contacts/{q}",
                params={"idProperty": "email"},
            )
            return [identity_resp] if identity_resp else []
        except Exception:
            return []

    # Deal search logic
    async def search_deals(self, query: str) -> list[dict[str, Any]]:
        return await self.search_objects(
            "deals", query_string=query, properties=self._SEARCH_PROPS["deals"]
        )

    # Lead search logic
    async def search_leads(self, query: str) -> list[dict[str, Any]]:
        return await self.search_objects(
            "leads", query_string=query, properties=self._SEARCH_PROPS["leads"]
        )

    # Company search logic
    async def search_companies(self, query: str) -> list[dict[str, Any]]:
        return await self.search_objects(
            "companies", query_string=query, properties=self._SEARCH_PROPS["companies"]
        )

    async def get_pipelines(self, object_type: str) -> list[dict[str, Any]]:
        """Fetch pipelines for a specific object type (deals, tickets)."""
        data = await self.request("GET", f"pipelines/{object_type}")
        if not data:
            return []
        return data.get("results", [])

    async def get_deal_pipelines(self) -> list[dict[str, Any]]:
        """Fetch all deal pipelines and their stages."""
        return await self.get_pipelines("deals")

    async def update_deal(
        self, object_id: str, properties: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Update properties of a deal."""
        return await self.request(
            "PATCH", f"objects/deals/{object_id}", json={"properties": properties}
        )

    async def update_contact(
        self, object_id: str, properties: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Update properties of a contact."""
        return await self.request(
            "PATCH", f"objects/contacts/{object_id}", json={"properties": properties}
        )

    async def update_company(
        self, object_id: str, properties: Mapping[str, Any]
    ) -> dict[str, Any]:
        """Update properties of a company."""
        return await self.request(
            "PATCH", f"objects/companies/{object_id}", json={"properties": properties}
        )

    # Ticket search logic
    async def search_tickets(self, query: str) -> list[dict[str, Any]]:
        return await self.search_objects(
            "tickets", query_string=query, properties=self._SEARCH_PROPS["tickets"]
        )

    # Task search logic
    async def search_tasks(self, query: str) -> list[dict[str, Any]]:
        return await self.search_objects(
            "tasks", query_string=query, properties=self._SEARCH_PROPS["tasks"]
        )

    # Files/Documents search logic
    async def search_files(self, query: str) -> list[dict[str, Any]]:
        """Search for files/documents."""
        # Files search API is limited. We'll try to find by name if possible,
        # otherwise we might need to rely on list and filter (inefficient).
        # Official endpoint: GET /files/v3/files/search
        # HubSpot Files API search is not well-documented for content search.
        # Raise explicitly until a proper implementation is added.
        raise NotImplementedError(
            "search_files is not yet implemented — "
            "HubSpot Files API search support is limited"
        )

    async def get_ticket(self, object_id: str) -> dict[str, Any] | None:
        return await self.get_object(
            "tickets",
            object_id,
            properties=[
                "subject",
                "content",
                "hs_pipeline_stage",
                "hs_ticket_priority",
                "hs_ticket_category",
            ],
        )

    async def get_owners(self) -> list[dict[str, Any]]:
        """Fetch all owners."""
        data = await self.request("GET", "owners")
        return data.get("results", [])

    async def get_task(self, object_id: str) -> dict[str, Any] | None:
        return await self.get_object(
            "tasks",
            object_id,
            properties=[
                "hs_task_subject",
                "hs_task_body",
                "hs_task_status",
                "hs_task_priority",
                "hs_task_type",
                "hs_timestamp",
                "hubspot_owner_id",
            ],
        )

    async def get_associations(
        self,
        from_object_type: str,
        object_id: str,
        to_object_type: str,
    ) -> list[str]:
        """Fetch associated object IDs via CRM v4 Associations API."""
        resp = await self.request(
            "GET",
            f"objects/{from_object_type}/{object_id}/associations/{to_object_type}",
        )
        results = resp.get("results", [])
        return [str(r.get("toObjectId", r.get("id", ""))) for r in results]

    async def batch_read(
        self,
        object_type: str,
        object_ids: list[str],
        properties: list[str] | None = None,
    ) -> list[dict[str, Any]]:
        """Fetch multiple CRM objects in a single batch read call.

        Uses POST /crm/v3/objects/{objectType}/batch/read to avoid
        N+1 individual GET requests.
        """
        if not object_ids:
            return []

        payload: dict[str, Any] = {
            "inputs": [{"id": oid} for oid in object_ids],
        }
        if properties:
            payload["properties"] = properties

        try:
            resp = await self.request(
                "POST",
                f"objects/{object_type}/batch/read",
                json=payload,
            )
            return resp.get("results", [])
        except Exception as exc:
            self.log.error(
                "Batch read failed for %s (%d ids): %s",
                object_type,
                len(object_ids),
                exc,
            )
            return []

    async def get_account_details(self) -> dict[str, Any]:
        """Fetch account details, including portalId."""
        # Verified endpoint: GET /account-info/v3/details
        return await self.request(
            "GET", "https://api.hubapi.com/account-info/v3/details"
        )

    async def uninstall_app(self) -> None:
        """Description:
        Uninstalls the app from the HubSpot account using the current session.
        Endpoint: DELETE /appinstalls/v3/external-install
        """
        await self.request(
            "DELETE",
            "https://api.hubapi.com/appinstalls/v3/external-install",
        )

    # -----------------------------
    # Conversations Inbox API
    # -----------------------------
    async def get_inbox_thread(self, thread_id: str) -> dict[str, Any]:
        """Fetch a conversation thread by ID."""
        return await self.request(
            "GET", f"conversations/v3/conversations/threads/{thread_id}"
        )

    async def create_inbox_message(
        self,
        thread_id: str,
        text: str,
        sender_actor_id: str | None = None,
        sender_type: str = "Responded by Bot",
        channel_id: str | None = None,
        channel_account_id: str | None = None,
    ) -> dict[str, Any]:
        """Send a message to a conversation thread.

        Args:
            thread_id: The ID of the thread.
            text: The message content.
            sender_actor_id: (Optional) The specific actor ID sending the message.

        Note:
            Creating a message usually requires an Actor.
            If generic, we might need to find a fallback actor.
            The standard endpoint is POST
                /conversations/v3/conversations/threads/{threadId}/messages

        """
        # Construction of the payload is complex for Conversations.
        # Minimal payload:
        # {
        #   "type": "MESSAGE",
        #   "text": "...",
        #   "richText": "...",
        #   "senderActorId": "..."
        # }
        # senderActorId is usually required if type is MESSAGE.

        payload: dict[str, Any] = {
            "type": "MESSAGE",
            "text": text,
            "richText": f"<p>{text}</p>",  # Basic HTML support
        }

        if sender_actor_id:
            payload["senderActorId"] = sender_actor_id

        # If no senderActorId, HubSpot API might reject or assign to default?
        # We'll see. If it fails, we might need to fetch actors first.

        return await self.request(
            "POST",
            f"conversations/v3/conversations/threads/{thread_id}/messages",
            json=payload,
        )

    async def get_meetings(
        self,
        object_id: str,
        properties: list[str] | None = None,
    ) -> dict[str, Any] | None:
        return await self.get_object(
            "meetings",
            object_id,
            properties=properties
            or [
                "hs_meeting_title",
                "hs_meeting_body",
                "hs_meeting_start_time",
                "hs_meeting_end_time",
                "hs_meeting_outcome",
            ],
        )

    async def search_meetings(self, query: str) -> list[dict[str, Any]]:
        return await self.search_objects(
            "meetings", query_string=query, properties=self._SEARCH_PROPS["meetings"]
        )
