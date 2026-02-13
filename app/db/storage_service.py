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
    Synchronous because SupabaseRepository is synchronous.
    """

    def __init__(self, *, corr_id: str | None = None) -> None:
        self.client = SupabaseClient(corr_id=corr_id)
        self.log = CorrelationAdapter(logger, corr_id or "storage")

        self.workspaces = SupabaseRepository[WorkspaceRecord](
            client=self.client,
            table="workspaces",
            model=WorkspaceRecord,
        )
        self.integrations = SupabaseRepository[IntegrationRecord](
            client=self.client,
            table="integrations",
            model=IntegrationRecord,
        )

    # -----------------------------
    # Workspaces
    # -----------------------------
    def get_workspace(self, workspace_id: str) -> WorkspaceRecord | None:
        self.log.info("Fetching workspace workspace_id=%s", workspace_id)
        return self.workspaces.fetch_single({"id": workspace_id})

    def upsert_workspace(
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
        self.workspaces.upsert(payload)
        return WorkspaceRecord(**payload)

    # -----------------------------
    # Integrations
    # -----------------------------
    def get_integration(self, **filters) -> IntegrationRecord | None:
        self.log.info("Fetching integration filters=%s", filters)
        return self.integrations.fetch_single(filters)

    def upsert_integration(self, payload: dict[str, Any]) -> None:
        self.log.info("Upserting integration provider=%s", payload.get("provider"))
        self.integrations.upsert(payload)

    def delete_integration(self, workspace_id: str, provider: str) -> None:
        self.log.info(
            "Deleting integration workspace_id=%s provider=%s", workspace_id, provider
        )
        self.integrations.delete({"workspace_id": workspace_id, "provider": provider})

    # -----------------------------
    # Token updates
    # -----------------------------
    def update_tokens(
        self,
        workspace_id: str,
        provider: str,
        new_at: str,
        new_rt: str | None,
    ) -> None:
        payload = {"access_token": new_at, "refresh_token": new_rt}
        self.integrations.update(
            {"workspace_id": workspace_id, "provider": provider},
            payload,
        )
