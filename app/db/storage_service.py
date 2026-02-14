# app/db/storage_service.py
from __future__ import annotations

from typing import Any

from app.core.logging import CorrelationAdapter, get_logger
from app.db.records import IntegrationRecord, WorkspaceRecord
from app.db.repository import SupabaseRepository
from app.db.supabase_client import SupabaseClient

logger = get_logger("storage")


class StorageService:
    """Pure persistence layer.
    Thin async wrapper around typed Supabase repositories.
    """

    def __init__(self, *, corr_id: str | None = None) -> None:
        self.client = SupabaseClient(corr_id=corr_id)
        self.log = CorrelationAdapter(logger, corr_id or "storage")

        self.workspaces = SupabaseRepository[WorkspaceRecord](
            client=self.client,
            table="workspaces",
            model=WorkspaceRecord,
            corr_id=corr_id or "storage",
        )

        self.integrations = SupabaseRepository[IntegrationRecord](
            client=self.client,
            table="integrations",
            model=IntegrationRecord,
            corr_id=corr_id or "storage",
        )

    # ---------------------------------------------------------
    # Workspaces
    # ---------------------------------------------------------
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

    # ---------------------------------------------------------
    # Integrations
    # ---------------------------------------------------------
    async def get_integration(
        self, workspace_id: str, provider: str
    ) -> IntegrationRecord | None:
        self.log.info(
            "Fetching integration workspace_id=%s provider=%s", workspace_id, provider
        )
        return await self.integrations.fetch_single(
            {"workspace_id": workspace_id, "provider": provider}
        )

    async def get_integration_by_slack_team_id(
        self,
        slack_team_id: str,
    ) -> IntegrationRecord | None:
        """Fetch Slack integration by Slack team ID."""
        self.log.info("Fetching Slack integration slack_team_id=%s", slack_team_id)
        return await self.integrations.fetch_single(
            {"provider": "slack", "slack_team_id": slack_team_id}
        )

    async def get_integration_by_portal_id(
        self,
        portal_id: str,
    ) -> IntegrationRecord | None:
        """Fetch HubSpot integration by portal_id."""
        self.log.info("Fetching HubSpot integration portal_id=%s", portal_id)
        return await self.integrations.fetch_single(
            {"provider": "hubspot", "portal_id": portal_id}
        )

    async def get_integrations_for_workspace(
        self,
        workspace_id: str,
    ) -> list[IntegrationRecord]:
        """Return all integrations for a workspace."""
        self.log.info("Fetching all integrations for workspace_id=%s", workspace_id)
        return await self.integrations.fetch_many({"workspace_id": workspace_id})

    async def delete_workspace(
        self,
        workspace_id: str,
    ) -> int:
        """Delete a workspace by ID.
        Returns number of rows deleted.
        """
        self.log.info("Deleting workspace workspace_id=%s", workspace_id)
        return await self.workspaces.delete({"id": workspace_id})

    async def list_integrations(self) -> list[IntegrationRecord]:
        """Return all integrations across all workspaces."""
        self.log.info("Listing all integrations")
        return await self.integrations.fetch_many({})

    async def upsert_integration(self, payload: dict[str, Any]) -> IntegrationRecord:
        self.log.info("Upserting integration provider=%s", payload.get("provider"))
        return await self.integrations.upsert(payload)

    async def delete_integration(self, workspace_id: str, provider: str) -> int:
        self.log.info(
            "Deleting integration workspace_id=%s provider=%s",
            workspace_id,
            provider,
        )
        return await self.integrations.delete(
            {"workspace_id": workspace_id, "provider": provider}
        )

    # ---------------------------------------------------------
    # Token updates
    # ---------------------------------------------------------
    async def update_tokens(
        self,
        workspace_id: str,
        provider: str,
        new_at: str,
        new_rt: str | None,
    ) -> IntegrationRecord | None:
        payload = {"access_token": new_at, "refresh_token": new_rt}

        self.log.info(
            "Updating tokens workspace_id=%s provider=%s",
            workspace_id,
            provider,
        )

        return await self.integrations.update(
            {"workspace_id": workspace_id, "provider": provider},
            payload,
        )
