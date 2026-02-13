# app/db/supabase.py
from __future__ import annotations

from typing import Any

from app.core.logging import CorrelationAdapter, get_logger
from app.db.records import IntegrationRecord, WorkspaceRecord
from app.db.repository import SupabaseRepository
from app.db.supabase_client import SupabaseClient

logger = get_logger("storage")


class StorageService:
    """Domain-level storage API:
    - workspaces
    - integrations
    - token updates
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

    # -------- Workspaces --------
    def get_workspace_by_id(self, workspace_id: str) -> WorkspaceRecord | None:
        self.log.info("Fetching workspace workspace_id=%s", workspace_id)
        return self.workspaces.fetch_single({"id": workspace_id})

    def create_workspace(
        self,
        workspace_id: str,
        primary_email: str | None = None,
        subscription_id: str | None = None,
    ) -> WorkspaceRecord:
        self.log.info(
            "Creating workspace workspace_id=%s primary_email=%s",
            workspace_id,
            primary_email,
        )
        payload = {
            "id": workspace_id,
            "primary_email": primary_email,
            "subscription_id": subscription_id,
        }

        self.workspaces.upsert(payload)

        return WorkspaceRecord(
            id=workspace_id,
            primary_email=primary_email,
            subscription_id=subscription_id,
        )

    # -------- Integrations --------
    def get_integration_by_slack_team_id(
        self,
        slack_team_id: str,
    ) -> IntegrationRecord | None:
        self.log.info("Fetching integration by slack_team_id=%s", slack_team_id)
        return self.integrations.fetch_single({"slack_team_id": slack_team_id})

    def get_integration_by_workspace_and_provider(
        self,
        workspace_id: str,
        provider: str,
    ) -> IntegrationRecord | None:
        self.log.info(
            "Fetching integration workspace_id=%s provider=%s",
            workspace_id,
            provider,
        )
        return self.integrations.fetch_single(
            {"workspace_id": workspace_id, "provider": provider}
        )

    def upsert_slack_integration(
        self,
        workspace_id: str,
        slack_team_id: str,
        slack_bot_token: str,
    ) -> None:
        self.log.info(
            "Upserting Slack integration workspace_id=%s slack_team_id=%s",
            workspace_id,
            slack_team_id,
        )
        payload = {
            "workspace_id": workspace_id,
            "provider": "slack",
            "slack_team_id": slack_team_id,
            "slack_bot_token": slack_bot_token,
        }
        self.integrations.upsert(payload)

    def upsert_hubspot_integration(
        self,
        workspace_id: str,
        portal_id: str,
        access_token: str,
        refresh_token: str | None,
    ) -> None:
        self.log.info(
            "Upserting HubSpot integration workspace_id=%s portal_id=%s",
            workspace_id,
            portal_id,
        )
        payload: dict[str, Any] = {
            "workspace_id": workspace_id,
            "provider": "hubspot",
            "portal_id": portal_id,
            "access_token": access_token,
            "refresh_token": refresh_token,
        }
        self.integrations.upsert(payload)

    def delete_integration(
        self,
        workspace_id: str,
        provider: str,
    ) -> None:
        self.log.info(
            "Deleting integration workspace_id=%s provider=%s",
            workspace_id,
            provider,
        )
        self.integrations.delete({"workspace_id": workspace_id, "provider": provider})

    # -------- Token updates --------
    def update_tokens(
        self,
        workspace_id: str,
        provider: str,
        new_at: str,
        new_rt: str | None,
    ) -> None:
        self.log.info(
            "Updating tokens workspace_id=%s provider=%s",
            workspace_id,
            provider,
        )
        payload: dict[str, Any] = {
            "access_token": new_at,
            "refresh_token": new_rt,
        }
        self.integrations.update(
            {"workspace_id": workspace_id, "provider": provider},
            payload,
        )
