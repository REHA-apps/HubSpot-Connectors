from __future__ import annotations

from typing import Any

from app.connectors.hubspot.channel import HubSpotChannel
from app.connectors.slack.channel import SlackChannel
from app.core.exceptions import IntegrationNotFoundError
from app.core.logging import CorrelationAdapter, get_logger
from app.db.records import IntegrationRecord, Provider
from app.db.storage_service import StorageService

logger = get_logger("integration.service")


class IntegrationService:
    """Description:
        Domain service for managing workspace-provider integrations and OAuth
        lifecycles.

    Rules Applied:
        - Implements request-scoped caching for integration records.
        - Orchestrates multi-provider installation flows (Slack-first vs HubSpot-first).
    """

    def __init__(
        self,
        corr_id: str,
        *,
        storage: StorageService | None = None,
    ) -> None:
        self.corr_id = corr_id
        self.log = CorrelationAdapter(logger, corr_id)

        self.storage = storage or StorageService(corr_id)
        self.slack_channel = SlackChannel(corr_id)
        self.hubspot_channel = HubSpotChannel(corr_id)

        # Typed caches
        self._integration_cache: dict[
            tuple[str, Provider], IntegrationRecord | None
        ] = {}
        self._slack_team_cache: dict[str, IntegrationRecord | None] = {}

    # Caching helpers
    async def get_integration(
        self,
        workspace_id: str,
        provider: Provider,
    ) -> IntegrationRecord | None:
        """Description:
            Fetches an integration record, utilizing local caching to minimize DB load.

        Args:
            workspace_id (str): The workspace to fetch for.
            provider (Provider): The specific provider (Slack/HubSpot).

        Returns:
            IntegrationRecord | None: The record if found, else None.

        Rules Applied:
            - Checks the _integration_cache before querying the storage service.

        """
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
        """Description:
            Retrieves an integration record by its Slack team ID with local caching.

        Args:
            team_id (str): The team ID from Slack.

        Returns:
            IntegrationRecord | None: The found record or None.

        Rules Applied:
            - Maintains a local Slack team cache to prevent redundant lookups.

        """
        if team_id in self._slack_team_cache:
            return self._slack_team_cache[team_id]

        row = await self.storage.get_integration_by_slack_team_id(team_id)
        self._slack_team_cache[team_id] = row
        return row

    # ---------------------------------------------------------
    # Workspace resolution
    # ---------------------------------------------------------
    async def resolve_workspace(self, slack_team_id: str | None) -> str:
        """Description:
            Maps a Slack team ID to an internal workspace ID.

        Args:
            slack_team_id (str | None): The team ID from Slack.

        Returns:
            str: Resolving workspace ID.

        Rules Applied:
            - Raises ValueError if team ID is missing or integration is not found.

        """
        if not slack_team_id:
            raise ValueError("Missing Slack team ID")

        integration = await self.get_integration_by_slack_team_id(slack_team_id)
        if not integration:
            raise IntegrationNotFoundError(
                f"No Slack integration found for team_id={slack_team_id}"
            )

        return integration.workspace_id

    async def resolve_default_channel(self, workspace_id: str) -> str:
        """Determine the default Slack channel for this workspace.

        Priority:
        1. integration.default_channel (if stored)
        2. integration.slack_team_id (fallback)
        """
        integration = await self.get_integration(workspace_id, provider=Provider.SLACK)
        if not integration:
            raise IntegrationNotFoundError(
                f"No Slack integration found for workspace {workspace_id}"
            )

        # 1. Explicit default channel
        default_channel = getattr(integration, "channel_id", None)
        if default_channel:
            return default_channel

        # 2. Fallback: Slack team ID
        slack_team_id = getattr(integration, "slack_team_id", None)
        if slack_team_id:
            return slack_team_id

        raise IntegrationNotFoundError(
            f"No default Slack channel configured for workspace {workspace_id}"
        )

    # OAuth lifecycle
    async def handle_hubspot_oauth_callback(self, code: str, state: str) -> str:
        """Description:
            Processes the HubSpot OAuth callback for both Slack-first and
            HubSpot-first flows.

        Args:
            code (str): Authorization code from HubSpot.
            state (str): Context identifier (Slack team ID or Workspace ID).

        Returns:
            str: The resolved or created workspace ID.

        Rules Applied:
            - Exchanges tokens via HubSpotPlatform.
            - Upserts both Workspace and Integration records.

        """
        self.log.info("Exchanging HubSpot OAuth code")
        token = await self.hubspot_channel.exchange_token(code)

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
        hs_payload: dict[str, Any] = {
            "workspace_id": workspace_id,
            "provider": Provider.HUBSPOT,
            "credentials": {
                "access_token": token.access_token,
                "refresh_token": token.refresh_token,
            },
            "metadata": {
                "portal_id": token.portal_id,
            },
        }

        # On re-install, include existing row ID so upsert merges instead of duplicating
        existing_hs = await self.storage.get_integration(workspace_id, Provider.HUBSPOT)
        if existing_hs:
            hs_payload["id"] = existing_hs.id

        await self.storage.upsert_integration(hs_payload)

        self.log.info("HubSpot integration saved workspace_id=%s", workspace_id)
        return workspace_id

    # Slack OAuth callback
    async def handle_slack_oauth_callback(self, code: str, state: str | None) -> str:
        """Description:
            Processes the Slack OAuth callback following a successful authentication.

        Args:
            code (str): Authorization code from Slack.
            state (str | None): Optional workspace ID context for HubSpot-first
                                installs.

        Returns:
            str: Finalized workspace ID.

        Rules Applied:
            - Exchanges tokens via SlackPlatform.
            - Reuses existing workspaces if Slack-first install corresponds to an
              existing team.

        """
        self.log.info("Exchanging Slack OAuth code")

        token = await self.slack_channel.exchange_token(code)
        team_id = token.team_id
        bot_token = token.access_token

        # HubSpot-first install → state is workspace_id
        existing = None
        if state:
            workspace = await self.storage.get_workspace(state)
            if workspace:
                workspace_id = workspace.id
                self.log.info("Resolved workspace via state=%s", workspace_id)
            else:
                workspace = await self.storage.upsert_workspace(workspace_id=state)
                workspace_id = workspace.id
                self.log.warning("Invalid state=%s; created new workspace", state)

            # Check for existing Slack integration to prevent duplicate on re-install
            existing = await self.get_integration_by_slack_team_id(team_id)

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
        slack_payload: dict[str, Any] = {
            "workspace_id": workspace_id,
            "provider": Provider.SLACK,
            "credentials": {
                "slack_bot_token": bot_token,
                "refresh_token": token.refresh_token,
                "expires_at": token.expires_at,
            },
            "metadata": {
                "slack_team_id": team_id,
            },
        }

        # On re-install, include existing row ID so upsert merges instead of duplicating
        if existing:
            slack_payload["id"] = existing.id

        await self.storage.upsert_integration(slack_payload)

        self.log.info("Slack integration saved workspace_id=%s", workspace_id)
        return workspace_id

    # Uninstallation
    async def uninstall_hubspot(self, workspace_id: str) -> None:
        await self.storage.delete_integration(workspace_id, provider=Provider.HUBSPOT)

    async def update_slack_tokens(
        self,
        workspace_id: str,
        access_token: str,
        refresh_token: str | None,
        expires_at: int | None,
    ) -> None:
        """Description:
        Callback to persist rotated Slack tokens.
        """
        integration = await self.get_integration(workspace_id, provider=Provider.SLACK)
        if not integration:
            return

        await self.storage.upsert_integration(
            {
                "id": integration.id,
                "workspace_id": workspace_id,
                "provider": Provider.SLACK,
                "credentials": {
                    **integration.credentials,
                    "slack_bot_token": access_token,
                    "refresh_token": refresh_token,
                    "expires_at": expires_at,
                },
                "metadata": integration.metadata,
            }
        )
        self.log.info(
            "Slack tokens rotated and persisted for workspace=%s", workspace_id
        )

    async def uninstall_slack(self, workspace_id: str) -> None:
        await self.storage.delete_integration(workspace_id, provider=Provider.SLACK)
