from __future__ import annotations

import time
from datetime import UTC, datetime, timedelta
from functools import cached_property
from typing import Any

from app.connectors.hubspot.channel import HubSpotChannel
from app.connectors.slack.channel import SlackChannel
from app.core.exceptions import IntegrationNotFoundError
from app.core.logging import CorrelationAdapter, get_logger
from app.db.records import IntegrationRecord, PlanTier, Provider
from app.db.storage_service import StorageService
from app.providers.slack.client import SlackClient

logger = get_logger("integration.service")

# Global tier cache — caches derived PlanTier values (not raw records).
# Integration record caching is handled by StorageService's AsyncTTL caches.
_GLOBAL_TIER_CACHE: dict[str, tuple[float, PlanTier]] = {}
_TIER_CACHE_TTL = 300.0  # 5 minutes


class IntegrationService:
    """Domain service for managing workspace-provider integrations and OAuth
    lifecycles.

    Integration record caching is handled by StorageService's AsyncTTL caches.
    This service maintains only a tier cache for derived PlanTier lookups.
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

    @cached_property
    def hubspot_service(self):
        """Lazy-loaded to avoid circular imports and unnecessary initialization."""
        from app.domains.crm.hubspot.service import HubSpotService

        return HubSpotService(self.corr_id, storage=self.storage)

    async def get_integration(
        self,
        workspace_id: str,
        provider: Provider,
    ) -> IntegrationRecord | None:
        """Fetches an integration record.

        Delegates to StorageService which maintains its own AsyncTTL cache
        with proper invalidation on upserts, deletes, and token updates.

        Args:
            workspace_id: The workspace to fetch for.
            provider: The specific provider (Slack/HubSpot).

        Returns:
            The integration record if found, else None.

        """
        return await self.storage.get_integration(workspace_id, provider)

    async def get_integration_by_slack_team_id(
        self,
        team_id: str,
    ) -> IntegrationRecord | None:
        """Retrieves an integration record by Slack team ID.

        Delegates to StorageService which maintains its own AsyncTTL cache
        for slack_team_id → workspace_id mapping.

        Args:
            team_id: The team ID from Slack.

        Returns:
            The integration record if found, else None.

        """
        return await self.storage.get_integration_by_slack_team_id(team_id)

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
            Retrieves the plan tier for a workspace, accounting for the 7-day trial.

        Args:
            workspace_id (str): The workspace to check.

        Returns:
            PlanTier: The assigned tier (FREE or PRO).

        """
        now = time.time()
        if workspace_id in _GLOBAL_TIER_CACHE:
            ts, tier = _GLOBAL_TIER_CACHE[workspace_id]
            if now - ts < _TIER_CACHE_TTL:
                return tier
            del _GLOBAL_TIER_CACHE[workspace_id]

        workspace = await self.storage.get_workspace(workspace_id)
        if not workspace:
            _GLOBAL_TIER_CACHE[workspace_id] = (now, PlanTier.FREE)
            return PlanTier.FREE

        # 1. Active subscription check
        if workspace.subscription_status == "active" or workspace.plan == PlanTier.PRO:
            _GLOBAL_TIER_CACHE[workspace_id] = (now, PlanTier.PRO)
            return PlanTier.PRO

        # 2. 7-day Trial check
        install_date = workspace.install_date or workspace.created_at
        if install_date:
            # Ensure we're comparing offset-aware datetimes
            target_now = datetime.now(UTC)
            if install_date.tzinfo is None:
                install_date = install_date.replace(tzinfo=UTC)

            if target_now <= install_date + timedelta(days=7):
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
    async def handle_hubspot_oauth_callback(self, code: str, state: str | None) -> str:
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

        # Fetch token info to capture the installing user's email
        primary_email: str | None = None
        try:
            from app.utils.helpers import HTTPClient

            http = HTTPClient.get_client(corr_id=self.corr_id)
            info_resp = await http.get(
                f"https://api.hubapi.com/oauth/v1/access-tokens/{token.access_token}"
            )
            if info_resp.is_success:
                info = info_resp.json()
                primary_email = info.get(
                    "user"
                )  # 'user' field is the installer's email
                self.log.info(
                    "Captured primary_email=%s from HubSpot token info", primary_email
                )
        except Exception as e:
            self.log.warning("Could not fetch HubSpot token info: %s", e)

        # Slack-first install (only if state was not dropped)
        slack_integration = None
        if state:
            slack_integration = await self.get_integration_by_slack_team_id(state)

        if slack_integration:
            workspace_id = slack_integration.workspace_id
            self.log.info("Resolved workspace via Slack-first install")
            # Update primary_email on existing workspace if we have it
            if primary_email:
                await self.storage.upsert_workspace(
                    workspace_id=workspace_id, primary_email=primary_email
                )
        else:
            # HubSpot-first install or state was dropped
            import uuid

            workspace_id = state or str(uuid.uuid4())
            workspace = await self.storage.upsert_workspace(
                workspace_id=workspace_id,
                primary_email=primary_email,
                install_date=datetime.now(UTC),
            )
            # Re-read to guarantee we have the assigned ID
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

        # Workflow seeding is disabled: referencing the custom
        # "Send Slack Message" action
        # programmatically requires a numeric definition ID only available via hapikey.
        # Users can manually create workflows via HubSpot → Automations → Workflows,
        # selecting "Send Slack Message" from the action library.
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
        team_name = token.raw.get("team", {}).get("name", "")
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
                "slack_team_name": team_name,
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
            import asyncio

            async def _persist_tokens():
                try:
                    await self.update_slack_tokens(
                        workspace_id=integration.workspace_id,
                        access_token=t,
                        refresh_token=r,
                        expires_at=e,
                    )
                except Exception as exc:
                    self.log.error(
                        "Failed to persist rotated Slack tokens for workspace=%s: %s",
                        integration.workspace_id,
                        exc,
                    )

            try:
                loop = asyncio.get_running_loop()
                loop.create_task(_persist_tokens())
            except RuntimeError:
                self.log.error(
                    "No running event loop — cannot persist "
                    "rotated tokens for workspace=%s",
                    integration.workspace_id,
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
