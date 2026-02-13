# app/connectors/hubspot_connector.py
from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.api.hubspot.schemas import HubSpotContactProperties, HubSpotTaskProperties
from app.clients.hubspot_client import HubSpotClient
from app.connectors.base import Connector
from app.connectors.slack_connector import SlackConnector
from app.core.logging import CorrelationAdapter, get_logger
from app.db.supabase import StorageService
from app.integrations.ai_service import AIService

logger = get_logger("hubspot.connector")


class HubSpotConnector(Connector):
    """HubSpot connector that:
    - resolves workspace via Slack-first or HubSpot-first install
    - initializes HubSpotClient with correlation ID
    - sends Slack notifications via SlackConnector
    """

    def __init__(
        self,
        slack_team_id: str | None,
        slack_connector: SlackConnector | None,
        corr_id: str,
    ) -> None:
        self.slack_team_id = slack_team_id
        self.slack_connector = slack_connector
        self.workspace_id: str | None = None
        self.client: HubSpotClient | None = None
        self.log = CorrelationAdapter(logger, corr_id)
        self.corr_id = corr_id

    async def _init_client(self) -> None:
        self.log.info(
            "Initializing HubSpot client, slack_team_id=%s", self.slack_team_id
        )

        # Slack-first: resolve workspace via Slack integration
        storage = StorageService(corr_id=self.corr_id)

        if self.slack_team_id:
            slack_integration = storage.get_integration_by_slack_team_id(
                self.slack_team_id
            )
            if slack_integration:
                self.workspace_id = slack_integration.workspace_id
                self.log.info(
                    "Resolved workspace_id=%s via Slack integration",
                    self.workspace_id,
                )

        if not self.workspace_id:
            msg = "Cannot resolve workspace for HubSpot event"
            self.log.error(msg)
            raise ValueError(msg)

        integration = storage.get_integration_by_workspace_and_provider(
            workspace_id=self.workspace_id,
            provider="hubspot",
        )

        if integration is None:
            msg = f"No HubSpot integration found for workspace {self.workspace_id}"
            self.log.error(msg)
            raise ValueError(msg)

        if not integration.access_token:
            msg = "HubSpot integration missing access_token"
            self.log.error(msg)
            raise ValueError(msg)

        self.client = HubSpotClient(
            access_token=integration.access_token,
            refresh_token=integration.refresh_token,
            workspace_id=self.workspace_id,
            corr_id=self.corr_id,
        )

        self.log.info(
            "HubSpot client initialized for workspace_id=%s", self.workspace_id
        )

    async def handle_event(
        self,
        event: Mapping[str, Any],
        *,
        channel: str = "#general",
    ) -> Mapping[str, Any]:
        if self.client is None:
            await self._init_client()

        assert self.client is not None  # Pyright: safe now

        contact_data = event.get("contact") or {}
        self.log.info(
            "Handling HubSpot event type=%s object_id=%s",
            event.get("type"),
            event.get("object_id"),
        )

        # AI summary generation
        ai_summary = AIService.generate_contact_insight(contact_data)

        slack_event = {
            "contact_data": contact_data,
            "ai_summary": ai_summary,
            "type": event.get("type"),
            "object_id": event.get("object_id"),
        }

        if self.slack_connector:
            await self.slack_connector.handle_event(slack_event, channel=channel)
        else:
            self.log.warning(
                "No Slack connector available; skipping Slack notification"
            )

        return {"status": "processed", "ai_summary": ai_summary}

    async def send_event(
        self,
        event: Mapping[str, Any],
    ) -> Mapping[str, Any]:
        if self.client is None:
            await self._init_client()

        assert self.client is not None

        task_dict = event.get("task_properties") or {}
        task_properties = HubSpotTaskProperties(**task_dict)

        return await self.client.create_task(
            task_properties.model_dump(exclude_none=True, by_alias=True)
        )

    async def create_contact(
        self,
        contact_properties: HubSpotContactProperties,
    ) -> Mapping[str, Any]:
        if self.client is None:
            await self._init_client()

        assert self.client is not None

        return await self.client.create_contact(
            contact_properties.model_dump(exclude_none=True, by_alias=True)
        )
