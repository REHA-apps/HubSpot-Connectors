from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from typing import Any

from app.connectors.hubspot.channel import HubSpotChannel
from app.connectors.slack.channel import SlackChannel  # noqa: PLC0415
from app.core.exceptions import IntegrationNotFoundError
from app.core.logging import CorrelationAdapter, get_logger
from app.db.records import IntegrationRecord, PlanTier, Provider
from app.db.storage_service import StorageService
from app.domains.crm.hubspot.workflow_service import WorkflowService
from app.providers.slack.client import SlackClient

logger = get_logger("integration.service")

# Global, cross-request caches. Evicted dynamically on reads based on TTL.
_GLOBAL_INTEGRATION_CACHE: dict[
    tuple[str, Provider], tuple[float, IntegrationRecord | None]
] = {}
_GLOBAL_SLACK_TEAM_CACHE: dict[str, tuple[float, IntegrationRecord | None]] = {}
_GLOBAL_TIER_CACHE: dict[str, tuple[float, PlanTier]] = {}
CACHE_TTL = 300.0  # 5 minutes


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

        # Avoid circular import
        from app.domains.crm.hubspot.service import HubSpotService  # noqa: PLC0415

        self.hubspot_service = HubSpotService(self.corr_id, storage=self.storage)
        self.workflow_service = WorkflowService(corr_id, self.storage)

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
        now = time.time()
        key = (workspace_id, provider)

        # 1. Instance (request-scoped) cache
        if key in self._integration_cache:
            return self._integration_cache[key]

        # 2. Global (application-scoped) TTL cache
        if key in _GLOBAL_INTEGRATION_CACHE:
            ts, record = _GLOBAL_INTEGRATION_CACHE[key]
            if now - ts < CACHE_TTL:
                self._integration_cache[key] = record
                return record
            del _GLOBAL_INTEGRATION_CACHE[key]  # Evict expired

        row = await self.storage.get_integration(workspace_id, provider)
        self._integration_cache[key] = row
        _GLOBAL_INTEGRATION_CACHE[key] = (now, row)
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
        now = time.time()

        # 1. Instance cache
        if team_id in self._slack_team_cache:
            return self._slack_team_cache[team_id]

        # 2. Global cache
        if team_id in _GLOBAL_SLACK_TEAM_CACHE:
            ts, record = _GLOBAL_SLACK_TEAM_CACHE[team_id]
            if now - ts < CACHE_TTL:
                self._slack_team_cache[team_id] = record
                return record
            del _GLOBAL_SLACK_TEAM_CACHE[team_id]

        row = await self.storage.get_integration_by_slack_team_id(team_id)
        self._slack_team_cache[team_id] = row
        _GLOBAL_SLACK_TEAM_CACHE[team_id] = (now, row)

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

        # 2. Check metadata
        if integration.metadata and "channel_id" in integration.metadata:
            return integration.metadata["channel_id"]

        # 3. Fallback: No channel found
        raise IntegrationNotFoundError(
            f"No default Slack channel configured for workspace {workspace_id}"
        )

    async def get_tier(self, workspace_id: str) -> PlanTier:
        """Description:
            Retrieves the plan tier for a workspace, accounting for the 14-day trial.

        Args:
            workspace_id (str): The workspace to check.

        Returns:
            PlanTier: The assigned tier (FREE or PRO).

        """
        now = time.time()
        if workspace_id in _GLOBAL_TIER_CACHE:
            ts, tier = _GLOBAL_TIER_CACHE[workspace_id]
            if now - ts < CACHE_TTL:
                return tier
            del _GLOBAL_TIER_CACHE[workspace_id]

        workspace = await self.storage.get_workspace(workspace_id)
        if not workspace:
            _GLOBAL_TIER_CACHE[workspace_id] = (now, PlanTier.FREE)
            return PlanTier.FREE

        # 1. Active subscription check
        if workspace.subscription_status == "active" or workspace.tier == PlanTier.PRO:
            _GLOBAL_TIER_CACHE[workspace_id] = (now, PlanTier.PRO)
            return PlanTier.PRO

        # 2. 14-day Trial check
        install_date = workspace.install_date or workspace.created_at
        if install_date:
            # Ensure we're comparing offset-aware datetimes
            target_now = datetime.now(UTC)
            if install_date.tzinfo is None:
                install_date = install_date.replace(tzinfo=UTC)

            if target_now <= install_date + timedelta(days=14):
                _GLOBAL_TIER_CACHE[workspace_id] = (now, PlanTier.PRO)
                return PlanTier.PRO

        _GLOBAL_TIER_CACHE[workspace_id] = (now, PlanTier.FREE)
        return PlanTier.FREE

    async def is_pro_workspace(self, workspace_id: str) -> bool:
        """Checks if a workspace is in the PRO tier (active or trialing)."""
        tier = await self.get_tier(workspace_id)
        return tier == PlanTier.PRO

    async def is_at_least_tier(
        self, workspace_id: str, required_tier: PlanTier
    ) -> bool:
        """DEPRECATED: Use is_pro_workspace(workspace_id)."""
        if required_tier == PlanTier.FREE:
            return True
        return await self.is_pro_workspace(workspace_id)

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
            workspace = await self.storage.upsert_workspace(
                workspace_id=state, install_date=datetime.now(UTC)
            )
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

        # Seed initial workflows for user
        await self.workflow_service.seed_all_workflows(workspace_id)

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
                workspace = await self.storage.upsert_workspace(
                    workspace_id=team_id, install_date=datetime.now(UTC)
                )
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
    async def uninstall_workspace(
        self,
        workspace_id: str,
        trigger_hubspot_uninstall: bool = True,
        trigger_slack_uninstall: bool = True,
    ) -> None:
        """Description:
        Fully uninstalls all integrations for a workspace and resets the workflow state.
        Triggers proactive uninstallation on both Slack and HubSpot if applicable.
        """
        # 1. Re-entry Guard: Check if the workspace record exists before proceeding.
        # This prevents infinite loops if revocation is detected multiple times.
        workspace = await self.storage.get_workspace(workspace_id)
        if not workspace:
            self.log.info("Workspace %s already uninstalled; skipping.", workspace_id)
            return

        self.log.info("Resetting all integrations for workspace_id=%s", workspace_id)

        # 2. Proactively uninstall from HubSpot if present and requested
        if trigger_hubspot_uninstall:
            try:
                hs_integration = await self.get_integration(
                    workspace_id, Provider.HUBSPOT
                )
                if hs_integration:
                    self.log.info("Triggering outbound HubSpot uninstallation")
                    await self.hubspot_service.uninstall_app(workspace_id)
            except Exception as exc:
                self.log.warning(
                    "Outbound HubSpot uninstallation failed: %s",
                    exc,
                )

        # 3. Proactively uninstall from Slack if present and requested
        if trigger_slack_uninstall:
            try:
                slack_integration = await self.get_integration(
                    workspace_id, Provider.SLACK
                )
                if slack_integration:
                    self.log.info("Triggering outbound Slack uninstallation")
                    # Attach token to channel
                    bot_token = slack_integration.slack_bot_token
                    self.slack_channel.bot_token = bot_token
                    await self.slack_channel.apps_uninstall()
            except Exception as exc:
                self.log.warning("Outbound Slack uninstallation failed: %s", exc)

        # Clear integrations first (tokens, metadata)
        await self.storage.delete_all_integrations_for_workspace(workspace_id)

        # Finally remove the workspace record itself for a full reset
        await self.storage.delete_workspace(workspace_id)

    async def uninstall_hubspot(self, workspace_id: str) -> None:
        """Description:
        Handles HubSpot uninstallation by resetting the workspace integrations.
        """
        await self.uninstall_workspace(workspace_id, trigger_hubspot_uninstall=False)

    async def get_slack_client(self, integration: IntegrationRecord) -> SlackClient:
        """Description:
        Returns a rotation-aware SlackClient for the given integration.
        """
        credentials = integration.credentials
        bot_token = credentials.get("slack_bot_token")
        refresh_token = credentials.get("refresh_token")
        expires_at = credentials.get("expires_at")

        client = SlackClient(
            corr_id=self.corr_id,
            bot_token=str(bot_token),
            refresh_token=refresh_token,
            expires_at=expires_at,
        )

        # Set callback for token rotation
        def on_refresh(t, r, e):
            import asyncio  # noqa: PLC0415

            asyncio.create_task(
                self.update_slack_tokens(
                    workspace_id=integration.workspace_id,
                    access_token=t,
                    refresh_token=r,
                    expires_at=e,
                )
            )

        client.on_token_refresh = on_refresh
        return client

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
        """Description:
        Handles Slack uninstallation by resetting the workspace integrations.
        """
        await self.uninstall_workspace(workspace_id, trigger_slack_uninstall=False)
