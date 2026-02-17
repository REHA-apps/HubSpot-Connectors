# app/services/integration_service.py
from __future__ import annotations

from app.core.logging import CorrelationAdapter, get_logger
from app.db.records import IntegrationRecord, Provider
from app.db.storage_service import StorageService
from app.integrations.oauth import OAuthService

logger = get_logger("integration.service")


class IntegrationService:
    """
    Centralized domain logic for:
    - Slack-first vs HubSpot-first installs
    - Workspace resolution
    - Integration upserts
    - Token refresh persistence
    - Uninstall flows

    Improvements:
    - Request-scoped caching (no aiocache)
    - Zero duplicate lookups
    - Clean alignment with IntegrationRecord + WorkspaceRecord
    """

    def __init__(self, corr_id: str):
        self.corr_id = corr_id
        self.log = CorrelationAdapter(logger, corr_id)

        self.storage = StorageService(corr_id=corr_id)
        self.oauth = OAuthService(corr_id=corr_id)

        # Typed caches
        self._integration_cache: dict[tuple[str, Provider], IntegrationRecord | None] = {}
        self._slack_team_cache: dict[str, IntegrationRecord | None] = {}

    # ---------------------------------------------------------
    # Cached fetch helpers
    # ---------------------------------------------------------
    async def get_integration(
        self,
        workspace_id: str,
        provider: Provider,
    ) -> IntegrationRecord | None:
        key = (workspace_id, provider)
        if key in self._integration_cache:
            return self._integration_cache[key]

        row = await self.storage.get_integration(workspace_id, provider)
        self._integration_cache[key] = row
        return row

    async def get_integration_by_slack_team_id(
        self,
        team_id: str,
    ) -> IntegrationRecord | None:
        if team_id in self._slack_team_cache:
            return self._slack_team_cache[team_id]

        row = await self.storage.get_integration_by_slack_team_id(team_id)
        self._slack_team_cache[team_id] = row
        return row

    # ---------------------------------------------------------
    # Workspace resolution
    # ---------------------------------------------------------
    async def resolve_workspace(self, slack_team_id: str | None) -> str:
        if not slack_team_id:
            raise ValueError("Missing Slack team ID")

        integration = await self.get_integration_by_slack_team_id(slack_team_id)
        if not integration:
            raise ValueError(f"No Slack integration found for team_id={slack_team_id}")

        return integration.workspace_id

    async def resolve_default_channel(self, workspace_id: str) -> str:
        """
        Determine the default Slack channel for this workspace.

        Priority:
        1. integration.default_channel (if stored)
        2. integration.slack_team_id (fallback)
        """
        integration = await self.get_integration(workspace_id, provider=Provider.SLACK)
        if not integration:
            raise ValueError(f"No Slack integration found for workspace {workspace_id}")

        # 1. Explicit default channel
        default_channel = getattr(integration, "channel_id", None)
        if default_channel:
            return default_channel

        # 2. Fallback: Slack team ID
        slack_team_id = getattr(integration, "slack_team_id", None)
        if slack_team_id:
            return slack_team_id

        raise ValueError(
            f"No default Slack channel configured for workspace {workspace_id}"
        )

    # ---------------------------------------------------------
    # HubSpot OAuth callback
    # ---------------------------------------------------------
    async def handle_hubspot_oauth_callback(self, code: str, state: str) -> str:
        """
        Handles HubSpot OAuth callback.
        state = Slack team ID (Slack-first) OR workspace ID (HubSpot-first).
        Returns workspace_id.
        """
        self.log.info("Exchanging HubSpot OAuth code")
        token = await self.oauth.exchange_hubspot_token(code)

        # Slack-first install
        slack_integration = await self.get_integration_by_slack_team_id(state)
        if slack_integration:
            workspace_id = slack_integration.workspace_id
            self.log.info("Resolved workspace via Slack-first install")
        else:
            # HubSpot-first install
            workspace = await self.storage.upsert_workspace(workspace_id=state)
            workspace_id = workspace.id
            self.log.info("Created workspace via HubSpot-first install")

        # Save HubSpot integration
        await self.storage.upsert_integration(
            {
                "workspace_id": workspace_id,
                "provider": Provider.HUBSPOT,
                "portal_id": token.portal_id,
                "access_token": token.access_token,
                "refresh_token": token.refresh_token,
            }
        )

        self.log.info("HubSpot integration saved workspace_id=%s", workspace_id)
        return workspace_id

    # ---------------------------------------------------------
    # Slack OAuth callback
    # ---------------------------------------------------------
    async def handle_slack_oauth_callback(self, code: str, state: str | None) -> str:
        """
        Handles Slack OAuth callback.
        state = workspace_id (HubSpot-first) OR None (Slack-first)
        Returns workspace_id.
        """
        self.log.info("Exchanging Slack OAuth code")

        token = await self.oauth.exchange_slack_token(code)
        team_id = token.team_id
        bot_token = token.access_token

        # HubSpot-first install → state is workspace_id
        if state:
            workspace = await self.storage.get_workspace(state)
            if workspace:
                workspace_id = workspace.id
                self.log.info("Resolved workspace via state=%s", workspace_id)
            else:
                workspace = await self.storage.upsert_workspace(workspace_id=state)
                workspace_id = workspace.id
                self.log.warning("Invalid state=%s; created new workspace", state)

        else:
            # Slack-first install
            existing = await self.get_integration_by_slack_team_id(team_id)
            if existing:
                workspace_id = existing.workspace_id
                self.log.info("Reusing existing workspace=%s", workspace_id)
            else:
                workspace = await self.storage.upsert_workspace(workspace_id=team_id)
                workspace_id = workspace.id
                self.log.info("Created new workspace=%s", workspace_id)

        # Save Slack integration
        await self.storage.upsert_integration(
            {
                "workspace_id": workspace_id,
                "provider": Provider.SLACK,
                "slack_team_id": team_id,
                "slack_bot_token": bot_token,
            }
        )

        self.log.info("Slack integration saved workspace_id=%s", workspace_id)
        return workspace_id

    # ---------------------------------------------------------
    # Uninstall flows
    # ---------------------------------------------------------
    async def uninstall_hubspot(self, workspace_id: str) -> None:
        await self.storage.delete_integration(workspace_id, provider=Provider.HUBSPOT)

    async def uninstall_slack(self, workspace_id: str) -> None:
        await self.storage.delete_integration(workspace_id, provider=Provider.SLACK)