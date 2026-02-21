from __future__ import annotations

from typing import Any

from app.core.logging import CorrelationAdapter, get_logger
from app.db.records import Provider
from app.db.storage_service import StorageService
from app.domains.ai.service import AIService
from app.domains.crm.channel_service import ChannelService
from app.domains.crm.hubspot.service import HubSpotService
from app.domains.crm.integration_service import IntegrationService

logger = get_logger("notification.service")


class NotificationService:
    """Description:
        Service for processing HubSpot webhook events and sending proactive AI
        notifications to Slack.

    Rules Applied:
        - Maps HubSpot portalId to internal workspace.
        - Fetches changed objects and performs AI analysis.
        - Applies heuristics (thresholds) to decide whether to notify.
    """

    AI_SCORE_THRESHOLD = 80

    def __init__(
        self,
        corr_id: str,
        *,
        storage: StorageService | None = None,
        integration_service: IntegrationService | None = None,
        ai: AIService | None = None,
    ):
        self.corr_id = corr_id
        self.log = CorrelationAdapter(logger, corr_id)

        self.storage = storage or StorageService(corr_id=corr_id)
        self.hubspot = HubSpotService(corr_id, storage=self.storage)
        self.integration_service = integration_service or IntegrationService(
            corr_id, storage=self.storage
        )

        self.ai = ai or AIService(corr_id)

    async def handle_event(self, event: dict[str, Any]) -> None:
        """Process a single HubSpot webhook event."""
        portal_id = str(event.get("portalId"))
        object_id = str(event.get("objectId"))
        sub_type = event.get("subscriptionType", "")

        # 1. Resolve Workspace
        integration = await self.storage.get_integration_by_portal_id(portal_id)
        if not integration:
            self.log.warning("No integration found for portalId=%s", portal_id)
            return

        workspace_id = integration.workspace_id

        # Handle HubSpot uninstallation event
        if sub_type == "app.deleted":
            self.log.info("Processing HubSpot uninstall for portalId=%s", portal_id)
            await self.integration_service.uninstall_hubspot(workspace_id)
            self.log.info(
                "HubSpot integration removed for workspace_id=%s", workspace_id
            )
            return

        # 2. Determine Object Type
        obj_type = self._map_subscription_to_type(sub_type)
        if not obj_type:
            self.log.info("Skipping unhandled subscription type: %s", sub_type)
            return

        # 3. Fetch Object from HubSpot
        self.log.info("Fetching %s %s for analysis", obj_type, object_id)
        obj = await self.hubspot.get_object(
            workspace_id=workspace_id, object_type=obj_type, object_id=object_id
        )
        if not obj:
            self.log.warning("Could not fetch %s %s", obj_type, object_id)
            return

        # Inject portalId for deep linking
        if isinstance(obj, dict):
            obj["portalId"] = portal_id

        # 4. Perform AI Analysis
        analysis = await self.ai.analyze_polymorphic(obj, obj_type)

        # 5. Check Notification Threshold
        if not self._should_notify(analysis, event):
            self.log.info(
                "Skipping notification for %s %s (below threshold)", obj_type, object_id
            )
            return

        # 6. Send Slack Notification
        slack_integ = await self.storage.get_integration(workspace_id, Provider.SLACK)
        if not slack_integ:
            self.log.warning(
                "No Slack integration for workspace %s, cannot notify", workspace_id
            )
            return

        channel_service = ChannelService(
            corr_id=self.corr_id,
            integration_service=self.integration_service,
            slack_integration=slack_integ,
        )

        self.log.info("Sending proactive notification for %s %s", obj_type, object_id)
        await channel_service.send_card(
            workspace_id=workspace_id,
            obj=obj,
            analysis=analysis,
        )

    def _map_subscription_to_type(self, sub_type: str) -> str | None:
        type_map = {
            "contact": "contact",
            "deal": "deal",
            "company": "company",
            "ticket": "ticket",
            "task": "task",
            "conversation": "conversation",
        }
        for key, val in type_map.items():
            if key in sub_type:
                return val
        return None

    def _should_notify(self, analysis: Any, event: dict[str, Any]) -> bool:
        """Description:
        Determines if a notification should be sent based on AI analysis or event type.
        Refined to avoid noise.
        """
        # 1. Deals: Notify on High Risk or Closed Won (if we get that info)
        if hasattr(analysis, "risk"):
            if analysis.risk in ["High", "Critical"]:
                return True

        # 2. Tickets: Notify on High/Critical Urgency
        if hasattr(analysis, "urgency"):
            if analysis.urgency in ["High", "Critical"]:
                return True

        # 3. Contacts: Notify on High Score (e.g. > 80)
        if hasattr(analysis, "score"):
            try:
                if int(analysis.score) >= self.AI_SCORE_THRESHOLD:
                    return True
            except (ValueError, TypeError):
                pass

        # 4. Tasks: Notify if "Not Started" but Priority is High?
        # Or maybe just don't notify for tasks automatically yet to avoid spam.
        if hasattr(analysis, "status_label"):
            # For now, maybe only high priority tasks?
            pass

        # 5. Conversations: Always notify
        if hasattr(analysis, "status") and "Conversation" in str(
            getattr(analysis, "summary", "")
        ):
            return True

        # Default: Don't notify to keep signal-to-noise ratio high
        return False
