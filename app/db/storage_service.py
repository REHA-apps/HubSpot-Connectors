from __future__ import annotations

from typing import Any

from app.core.logging import CorrelationAdapter, get_logger
from app.db.records import IntegrationRecord, Provider, WorkspaceRecord
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
        self.log = CorrelationAdapter(logger, corr_id)

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

    # Workspace operations
    async def get_workspace(self, workspace_id: str) -> WorkspaceRecord | None:
        self.log.info("Fetching workspace workspace_id=%s", workspace_id)
        return await self.workspaces.fetch_single({"id": workspace_id})

    async def upsert_workspace(
        self,
        workspace_id: str,
        primary_email: str | None = None,
        subscription_id: str | None = None,
    ) -> WorkspaceRecord:
        payload = {
            "id": workspace_id,
            "primary_email": primary_email,
            "subscription_id": subscription_id,
        }

        self.log.info("Upserting workspace id=%s", workspace_id)
        return await self.workspaces.upsert(payload)

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
        self.log.info("Deleting workspace workspace_id=%s", workspace_id)
        return await self.workspaces.delete({"id": workspace_id})

    # Integration operations
    async def get_integration(
        self, workspace_id: str, provider: Provider
    ) -> IntegrationRecord | None:
        self.log.info(
            "Fetching integration workspace_id=%s provider=%s",
            workspace_id,
            provider,
        )

        cache_key = f"integ:{workspace_id}:{provider}"

        async def fetch():
            return await self.integrations.fetch_single(
                {"workspace_id": workspace_id, "provider": provider}
            )

        return await _record_cache.get_or_fetch(cache_key, fetch)

    async def get_integration_by_slack_team_id(
        self,
        slack_team_id: str,
    ) -> IntegrationRecord | None:
        self.log.info("Fetching Slack integration slack_team_id=%s", slack_team_id)

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
        self.log.info("Fetching HubSpot integration portal_id=%s", portal_id)

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
                portal_id, lambda: _wrap_result(record.workspace_id)
            )

        return record

    async def get_integrations_for_workspace(
        self,
        workspace_id: str,
    ) -> list[IntegrationRecord]:
        self.log.info("Fetching all integrations for workspace_id=%s", workspace_id)
        # We don't cache list queries comfortably yet due to invalidation complexity
        return await self.integrations.fetch_many({"workspace_id": workspace_id})

    async def list_integrations(self) -> list[IntegrationRecord]:
        self.log.info("Listing all integrations")
        return await self.integrations.fetch_many({})

    async def upsert_integration(self, payload: dict[str, Any]) -> IntegrationRecord:
        self.log.info("Upserting integration provider=%s", payload.get("provider"))

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
        self.log.info(
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
        self.log.info(
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
        new_at: str,
        new_rt: str | None,
    ) -> IntegrationRecord | None:
        # Note: In a real app with JSONB updates, you might want a specialized
        # RPC or to fetch-then-save to avoid overwriting other credential keys.
        # For simplicity here, we assume 'credentials' is being updated.

        existing = await self.get_integration(workspace_id, provider)
        if not existing:
            return None

        new_credentials = {
            **existing.credentials,
            "access_token": new_at,
            "refresh_token": new_rt,
        }
        payload = {"credentials": new_credentials}

        self.log.info(
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
