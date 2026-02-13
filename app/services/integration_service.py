# app/services/integration_service.py
from __future__ import annotations

from app.core.logging import CorrelationAdapter, get_logger
from app.db.supabase import StorageService
from app.integrations.oauth import OAuthService

logger = get_logger("integration.service")


class IntegrationService:
    """Centralized domain logic for:
    - Slack-first vs HubSpot-first installs
    - Workspace resolution
    - Integration upserts
    - Token refresh persistence
    - Uninstall flows
    """

    def __init__(self, corr_id: str) -> None:
        self.corr_id = corr_id
        self.log = CorrelationAdapter(logger, corr_id)
        self.storage = StorageService(corr_id=corr_id)

    # ---------------------------------------------------------
    # Workspace resolution
    # ---------------------------------------------------------
    def resolve_workspace(self, slack_team_id: str | None) -> str:
        """Resolve workspace ID from Slack team ID.
        Used by SlackConnector and HubSpotConnector.
        """
        if not slack_team_id:
            raise ValueError("Missing Slack team ID")

        slack_integration = self.storage.get_integration_by_slack_team_id(slack_team_id)
        if not slack_integration:
            raise ValueError(f"No Slack integration found for team_id={slack_team_id}")

        return slack_integration.workspace_id

    # ---------------------------------------------------------
    # HubSpot OAuth callback
    # ---------------------------------------------------------
    async def handle_hubspot_oauth_callback(
        self,
        code: str,
        state: str,
    ) -> str:
        """Handles HubSpot OAuth callback.
        state = Slack team ID (Slack-first) OR workspace ID (HubSpot-first).
        Returns workspace_id.
        """
        self.log.info("Exchanging HubSpot OAuth code")

        token_data = await OAuthService.exchange_hubspot_token(
            code,
            corr_id=self.corr_id,
        )

        access_token = token_data["access_token"]
        refresh_token = token_data.get("refresh_token")
        portal_id = str(token_data["portal_id"])

        # Slack-first install
        slack_integration = self.storage.get_integration_by_slack_team_id(state)

        if slack_integration:
            workspace_id = slack_integration.workspace_id
            self.log.info("Resolved workspace via Slack-first install")
        else:
            # HubSpot-first install
            workspace = self.storage.create_workspace(workspace_id=state)
            workspace_id = workspace.id
            self.log.info("Created workspace via HubSpot-first install")

        # Save HubSpot integration
        self.storage.upsert_hubspot_integration(
            workspace_id=workspace_id,
            portal_id=portal_id,
            access_token=access_token,
            refresh_token=refresh_token,
        )

        self.log.info("HubSpot integration saved workspace_id=%s", workspace_id)
        return workspace_id

    # ---------------------------------------------------------
    # Slack OAuth callback (missing in your code)
    # ---------------------------------------------------------
    async def handle_slack_oauth_callback(
        self,
        code: str,
    ) -> str:
        """Handles Slack OAuth callback.
        Returns workspace_id.
        """
        self.log.info("Exchanging Slack OAuth code")

        token_data = await OAuthService.exchange_slack_token(
            code,
            corr_id=self.corr_id,
        )

        team_id = token_data["team"]["id"]
        bot_token = token_data["access_token"]

        # Slack-first install → create workspace
        workspace = self.storage.create_workspace(workspace_id=team_id)
        workspace_id = workspace.id

        # Save Slack integration
        self.storage.upsert_slack_integration(
            workspace_id=workspace_id,
            slack_team_id=team_id,
            slack_bot_token=bot_token,
        )

        self.log.info("Slack integration saved workspace_id=%s", workspace_id)
        return workspace_id

    # ---------------------------------------------------------
    # Uninstall flows
    # ---------------------------------------------------------
    def uninstall_hubspot(self, workspace_id: str) -> None:
        self.storage.delete_integration(workspace_id, provider="hubspot")

    def uninstall_slack(self, workspace_id: str) -> None:
        self.storage.delete_integration(workspace_id, provider="slack")

    # inside IntegrationService


async def handle_slack_oauth_callback(
    self,
    code: str,
    state: str | None,
) -> str:
    """Handles Slack OAuth callback.
    state = workspace_id (HubSpot-first) OR None (Slack-first)
    Returns workspace_id.
    """
    self.log.info("Exchanging Slack OAuth code")

    token_data = await OAuthService.exchange_slack_token(
        code,
        corr_id=self.corr_id,
    )

    access_token = token_data["access_token"]
    team_id = token_data["team"]["id"]

    # HubSpot-first install → state is workspace_id
    if state:
        workspace = self.storage.get_workspace_by_id(state)
        if workspace:
            workspace_id = workspace.id
            self.log.info("Resolved workspace via state=%s", workspace_id)
        else:
            self.log.warning("Invalid state=%s; creating new workspace", state)
            workspace = self.storage.create_workspace(workspace_id=state)
            workspace_id = workspace.id

    else:
        # Slack-first install
        existing = self.storage.get_integration_by_slack_team_id(team_id)
        if existing:
            workspace_id = existing.workspace_id
            self.log.info("Reusing existing workspace=%s", workspace_id)
        else:
            workspace = self.storage.create_workspace(workspace_id=team_id)
            workspace_id = workspace.id
            self.log.info("Created new workspace=%s", workspace_id)

    # Save Slack integration
    self.storage.upsert_slack_integration(
        workspace_id=workspace_id,
        slack_team_id=team_id,
        slack_bot_token=access_token,
    )

    self.log.info("Slack integration saved workspace_id=%s", workspace_id)
    return workspace_id
