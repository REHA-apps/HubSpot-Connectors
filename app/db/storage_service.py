from __future__ import annotations

from datetime import UTC, datetime
from typing import Any

from app.core.logging import get_logger
from app.db.records import (
    AIScoreRecord,
    IntegrationRecord,
    Provider,
    ScoringConfigRecord,
    ThreadMappingRecord,
    WorkspaceRecord,
)
from app.db.repository import SupabaseRepository
from app.db.supabase_client import SupabaseClient
from app.utils.cache import AsyncTTL

logger = get_logger("storage")


class StorageService:
    """Description:
        Core persistence service providing a typed, high-level interface to Supabase.

    Rules Applied:
        - Acts as a thin wrapper around specific SupabaseRepository instances.
        - Orchestrates multi-step database operations like ensured workspace creation.
    """

    def __init__(self, corr_id: str) -> None:
        self.client = SupabaseClient(corr_id=corr_id)
        self.workspaces = SupabaseRepository[WorkspaceRecord](
            client=self.client,
            table="workspaces",
            model=WorkspaceRecord,
            corr_id=corr_id,
        )

        self.integrations = SupabaseRepository[IntegrationRecord](
            client=self.client,
            table="integrations",
            model=IntegrationRecord,
            corr_id=corr_id,
        )

        self.thread_mappings = SupabaseRepository[ThreadMappingRecord](
            client=self.client,
            table="thread_mappings",
            model=ThreadMappingRecord,
            corr_id=corr_id,
        )

        self.scoring_configs = SupabaseRepository[ScoringConfigRecord](
            client=self.client,
            table="scoring_configs",
            model=ScoringConfigRecord,
            corr_id=corr_id,
        )

        self.ai_scores = SupabaseRepository[AIScoreRecord](
            client=self.client,
            table="ai_scores",
            model=AIScoreRecord,
            corr_id=corr_id,
        )

    async def _resolve_internal_workspace_id(self, workspace_id: str) -> str:
        """Helper to resolve an internal workspace UUID from a numeric portal ID.

        If workspace_id is numeric, it performs a lookup to find the actual
        workspace_id from the HubSpot integration record.
        """
        if not workspace_id.isdigit():
            return workspace_id

        # Numeric ID detected; resolve to internal UUID
        integration = await self.get_integration_by_portal_id(portal_id=workspace_id)
        if not integration:
            logger.warning(
                "Could not resolve internal workspace_id for portal %s", workspace_id
            )
            return (
                workspace_id  # Fallback to original, error will likely occur downstream
            )

        return integration.workspace_id

    # Workspace operations
    async def get_workspace(self, workspace_id: str) -> WorkspaceRecord | None:
        logger.info("Fetching workspace workspace_id=%s", workspace_id)
        return await self.workspaces.fetch_single({"id": workspace_id})

    async def upsert_workspace(  # noqa: PLR0913
        self,
        workspace_id: str,
        primary_email: str | None = None,
        portal_id: str | None = None,
        subscription_id: str | None = None,
        subscription_status: str | None = None,
        stripe_customer_id: str | None = None,
        plan: str | None = None,
        trial_ends_at: datetime | None = None,
        install_date: Any | None = None,
    ) -> WorkspaceRecord:
        payload = {
            "id": workspace_id,
            "primary_email": primary_email,
            "portal_id": portal_id,
            "subscription_id": subscription_id,
            "subscription_status": subscription_status,
            "stripe_customer_id": stripe_customer_id,
            "plan": plan,
            "trial_ends_at": trial_ends_at,
        }
        # Filter out None values to avoid overwriting existing data with nulls
        payload = {k: v for k, v in payload.items() if v is not None}

        if install_date:
            payload["install_date"] = install_date

        logger.info("Upserting workspace id=%s", workspace_id)
        return await self.workspaces.upsert(payload)

    async def get_workspace_by_stripe_customer_id(
        self, customer_id: str
    ) -> WorkspaceRecord | None:
        logger.info("Fetching workspace by stripe_customer_id=%s", customer_id)
        return await self.workspaces.fetch_single({"stripe_customer_id": customer_id})

    async def ensure_workspace(self, workspace_id: str) -> WorkspaceRecord:
        """Description:
            Fetches a workspace by ID, creating it if it does not already exist.

        Args:
            workspace_id (str): The workspace identifier.

        Returns:
            WorkspaceRecord: The retrieved or newly created workspace record.

        """
        ws = await self.get_workspace(workspace_id)
        return ws or await self.upsert_workspace(workspace_id)

    async def delete_workspace(self, workspace_id: str) -> int:
        logger.info("Deleting workspace workspace_id=%s", workspace_id)
        return await self.workspaces.delete({"id": workspace_id})

    async def list_all_workspaces(self) -> list[WorkspaceRecord]:
        logger.info("Listing all workspaces")
        return await self.workspaces.fetch_many({})

    # Integration operations
    async def get_integration(
        self, workspace_id: str, provider: Provider
    ) -> IntegrationRecord | None:
        logger.info(
            "Fetching integration workspace_id=%s provider=%s",
            workspace_id,
            provider,
        )

        # Preemptive check for HubSpot: If the provided
        # workspace_id is strictly numeric,
        # it is a HubSpot portal_id instead of our internal workspace_id.
        if provider == Provider.HUBSPOT and workspace_id.isdigit():
            logger.info(
                "Numeric ID detected, using portal_id lookup for %s", workspace_id
            )
            return await self.get_integration_by_portal_id(portal_id=workspace_id)

        cache_key = f"integ:{workspace_id}:{provider}"

        async def fetch():
            return await self.integrations.fetch_single(
                {"workspace_id": workspace_id, "provider": provider}
            )

        row = await _record_cache.get_or_fetch(cache_key, fetch)

        return row

    async def list_integrations(
        self,
        workspace_id: str,
        provider: Provider | None = None,
    ) -> list[IntegrationRecord]:
        """Fetches all integrations for a workspace, optionally filtered by provider."""
        filters: dict[str, Any] = {"workspace_id": workspace_id}
        if provider:
            filters["provider"] = provider

        return await self.integrations.fetch_many(filters)

    async def get_integration_by_slack_team_id(
        self,
        slack_team_id: str,
    ) -> IntegrationRecord | None:
        logger.info("Fetching Slack integration slack_team_id=%s", slack_team_id)

        # 1. Resolve Workspace ID from mapping cache
        async def fetch_record_directly():
            # Fallback lookup if mapping fails or for initial populate
            return await self.integrations.fetch_single(
                {"provider": Provider.SLACK, "metadata->>slack_team_id": slack_team_id}
            )

        workspace_id = await _slack_mapping_cache.get(slack_team_id)

        if workspace_id:
            # Hit mapping, try fetching record via primary cache
            record = await self.get_integration(workspace_id, Provider.SLACK)
            if record:
                return record
            # If record missing (deleted?), remove mapping and retry direct
            await _slack_mapping_cache.invalidate(slack_team_id)

        # Miss mapping or stale mapping: Fetch direct
        record = await fetch_record_directly()
        if record:
            # Populate both caches to avoid redundant DB calls
            await _slack_mapping_cache.set(slack_team_id, record.workspace_id)
            cache_key = f"integ:{record.workspace_id}:{Provider.SLACK}"
            await _record_cache.set(cache_key, record)

        return record

    async def get_integration_by_portal_id(
        self,
        portal_id: str,
    ) -> IntegrationRecord | None:
        logger.info("Fetching HubSpot integration portal_id=%s", portal_id)

        async def fetch_record_directly():
            return await self.integrations.fetch_single(
                {"provider": Provider.HUBSPOT, "metadata->>portal_id": portal_id}
            )

        workspace_id = await _hubspot_mapping_cache.get(portal_id)

        if workspace_id:
            record = await self.get_integration(workspace_id, Provider.HUBSPOT)
            if record:
                return record
            await _hubspot_mapping_cache.invalidate(portal_id)

        record = await fetch_record_directly()
        if record:
            await _hubspot_mapping_cache.get_or_fetch(
                portal_id,
                lambda: _wrap_result(record.workspace_id),  # noqa: PLW0108
            )

        return record

    async def get_integrations_for_workspace(
        self,
        workspace_id: str,
    ) -> list[IntegrationRecord]:
        logger.info("Fetching all integrations for workspace_id=%s", workspace_id)
        # We don't cache list queries comfortably yet due to invalidation complexity
        return await self.integrations.fetch_many({"workspace_id": workspace_id})

    async def list_all_integrations(self) -> list[IntegrationRecord]:
        logger.info("Listing all integrations")
        return await self.integrations.fetch_many({})

    async def upsert_integration(self, payload: dict[str, Any]) -> IntegrationRecord:
        logger.info("Upserting integration provider=%s", payload.get("provider"))

        res = await self.integrations.upsert(payload)

        # Invalidate record cache
        if res:
            cache_key = f"integ:{res.workspace_id}:{res.provider}"
            await _record_cache.invalidate(cache_key)

            # Opportunistically update mappings?
            # If metadata has IDs, we could update/invalidate mapping caches too.
            if res.provider == Provider.SLACK:
                tid = res.metadata.get("slack_team_id")
                if tid:
                    await _slack_mapping_cache.invalidate(tid)
            if res.provider == Provider.HUBSPOT:
                pid = res.metadata.get("portal_id")
                if pid:
                    await _hubspot_mapping_cache.invalidate(str(pid))

        return res

    async def ensure_integration(
        self,
        workspace_id: str,
        provider: Provider,
    ) -> IntegrationRecord:
        integ = await self.get_integration(workspace_id, provider)
        if integ:
            return integ
        return await self.upsert_integration(
            {"workspace_id": workspace_id, "provider": provider}
        )

    async def delete_integration(self, workspace_id: str, provider: Provider) -> int:
        logger.info(
            "Deleting integration workspace_id=%s provider=%s",
            workspace_id,
            provider,
        )
        count = await self.integrations.delete(
            {"workspace_id": workspace_id, "provider": provider}
        )
        if count > 0:
            await _record_cache.invalidate(f"integ:{workspace_id}:{provider}")
            # We should theoretically invalidate mappings too but lack IDs.
            # Stale mapping -> lookup miss -> re-fetch -> null -> removed
            # (Self-healing).
        return count

    async def delete_all_integrations_for_workspace(self, workspace_id: str) -> int:
        logger.info(
            "Deleting all integrations for workspace_id=%s",
            workspace_id,
        )
        # Hard to invalidate specific keys without iteration.
        # Ideally clear all caches or accept temporary staleness.
        # For now, we assume simple invalidation or rely on TTL.
        # But we could iterate providers and invalidate _record_cache.
        await _record_cache.invalidate(f"integ:{workspace_id}:{Provider.SLACK}")
        await _record_cache.invalidate(f"integ:{workspace_id}:{Provider.HUBSPOT}")

        return await self.integrations.delete({"workspace_id": workspace_id})

    # Token operations
    async def update_tokens(
        self,
        workspace_id: str,
        provider: Provider,
        access_token: str,
        refresh_token: str | None,
    ) -> IntegrationRecord | None:
        # Note: In a real app with JSONB updates, you might want a specialized
        # RPC or to fetch-then-save to avoid overwriting other credential keys.
        # For simplicity here, we assume 'credentials' is being updated.

        existing = await self.get_integration(workspace_id, provider)
        if not existing:
            return None

        new_credentials = {
            **existing.credentials,
            "access_token": access_token,
            "refresh_token": refresh_token,
        }
        payload = {"credentials": new_credentials}

        logger.info(
            "Updating tokens workspace_id=%s provider=%s",
            workspace_id,
            provider,
        )

        updated = await self.integrations.update(
            {"workspace_id": workspace_id, "provider": provider},
            payload,
        )

        if updated:
            await _record_cache.invalidate(f"integ:{workspace_id}:{provider}")

        return updated

    # Thread mapping operations
    async def get_thread_mapping(
        self,
        workspace_id: str,
        object_type: str,
        object_id: str,
        channel_id: str | None = None,
    ) -> ThreadMappingRecord | None:
        workspace_id = await self._resolve_internal_workspace_id(workspace_id)
        logger.info(
            "Fetching thread mapping workspace_id=%s object_type=%s object_id=%s",
            workspace_id,
            object_type,
            object_id,
        )
        filters = {
            "workspace_id": workspace_id,
            "object_type": object_type,
            "object_id": object_id,
        }
        if channel_id:
            filters["channel_id"] = channel_id
        return await self.thread_mappings.fetch_single(filters)

    async def upsert_thread_mapping(
        self, payload: dict[str, Any]
    ) -> ThreadMappingRecord:
        if "workspace_id" in payload:
            payload["workspace_id"] = await self._resolve_internal_workspace_id(
                payload["workspace_id"]
            )
        logger.info(
            "Upserting thread mapping object_id=%s thread_ts=%s",
            payload.get("object_id"),
            payload.get("thread_ts"),
        )
        return await self.thread_mappings.upsert(payload)

    async def get_thread_mapping_by_ts(
        self,
        workspace_id: str,
        channel_id: str,
        thread_ts: str,
    ) -> ThreadMappingRecord | None:
        workspace_id = await self._resolve_internal_workspace_id(workspace_id)
        logger.info(
            "Fetching thread mapping workspace_id=%s channel_id=%s thread_ts=%s",
            workspace_id,
            channel_id,
            thread_ts,
        )
        return await self.thread_mappings.fetch_single(
            {
                "workspace_id": workspace_id,
                "channel_id": channel_id,
                "thread_ts": thread_ts,
            }
        )

    async def store_stripe_event(self, event_id: str) -> bool:
        """Returns True if event is new.
        Returns False if event was already processed.
        """
        try:
            response = await self.client.upsert(
                "stripe_events",
                {"id": event_id},
                on_conflict="id",
                ignore_duplicates=True,
            )

            data = getattr(response, "data", [])
            return len(data) > 0
        except Exception as e:
            # Duplicate primary key = already processed
            logger.error("Stripe event already processed: %s %s", event_id, e)
            return False

    # Scoring config operations
    async def get_scoring_config(
        self,
        workspace_id: str,
    ) -> ScoringConfigRecord | None:
        internal_id = await self._resolve_internal_workspace_id(workspace_id)
        return await self.scoring_configs.fetch_single({"workspace_id": internal_id})

    async def ensure_scoring_config(
        self,
        workspace_id: str,
    ) -> ScoringConfigRecord:
        internal_id = await self._resolve_internal_workspace_id(workspace_id)
        config = await self.get_scoring_config(internal_id)
        if config:
            return config

        return await self.scoring_configs.insert({"workspace_id": internal_id})

    async def upsert_ai_score(
        self,
        workspace_id: str,
        object_type: str,
        object_id: str,
        score: int,
        score_reason: str,
        next_action: str,
    ) -> AIScoreRecord:
        internal_id = await self._resolve_internal_workspace_id(workspace_id)
        payload = {
            "workspace_id": internal_id,
            "object_type": object_type,
            "object_id": object_id,
            "score": score,
            "score_reason": score_reason,
            "next_action": next_action,
            "updated_at": datetime.now(UTC).isoformat(),
        }

        return await self.ai_scores.upsert(payload)

    async def get_ai_scores(
        self,
        workspace_id: str,
        object_type: str,
        object_id: str,
    ) -> list[AIScoreRecord]:
        internal_id = await self._resolve_internal_workspace_id(workspace_id)
        return await self.ai_scores.fetch_many(
            {
                "workspace_id": internal_id,
                "object_type": object_type,
                "object_id": object_id,
            }
        )

    async def get_top_scored_objects(
        self,
        workspace_id: str,
        object_type: str,
        limit: int = 10,
    ) -> list[AIScoreRecord]:
        internal_id = await self._resolve_internal_workspace_id(workspace_id)
        return await self.ai_scores.fetch_many(
            {"workspace_id": internal_id, "object_type": object_type},
            order_by=("score", "desc"),
            limit=limit,
        )


# Global module-level caches
# Caches IntegrationRecord by {workspace_id}:{provider}
_record_cache = AsyncTTL[IntegrationRecord | None](ttl=300)

# Caches workspace_id by slack_team_id
_slack_mapping_cache = AsyncTTL[str](ttl=300)

# Caches workspace_id by portal_id
_hubspot_mapping_cache = AsyncTTL[str](ttl=300)


async def _wrap_result(val: str):
    """Helper to wrap a value in a coroutine for get_or_fetch"""
    return val
