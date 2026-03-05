from __future__ import annotations

from typing import Any, cast

from app.core.logging import get_logger
from app.db.records import PlanTier, Provider
from app.db.storage_service import StorageService
from app.domains.ai.service import AIService
from app.domains.crm.hubspot.service import HubSpotService
from app.domains.crm.integration_service import IntegrationService
from app.domains.messaging.base import MessagingService

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
        self.storage = storage or StorageService(corr_id=corr_id)
        self.hubspot = HubSpotService(corr_id, storage=self.storage)
        self.integration_service = integration_service or IntegrationService(
            corr_id, storage=self.storage
        )

        self.ai = ai or AIService(corr_id)

    async def handle_event(self, event: dict[str, Any]) -> None:  # noqa: PLR0911, PLR0912, PLR0915
        """Process a single HubSpot webhook event."""
        portal_id = str(event.get("portalId"))
        object_id = str(event.get("objectId"))
        sub_type = event.get("subscriptionType", "")

        # 1. Resolve Workspace
        integration = await self.storage.get_integration_by_portal_id(portal_id)
        if not integration:
            logger.warning("No integration found for portalId=%s", portal_id)
            return

        workspace_id = integration.workspace_id

        # Handle HubSpot uninstallation event
        if sub_type == "app.deleted":
            logger.info("Processing HubSpot uninstall for portalId=%s", portal_id)
            await self.integration_service.uninstall_hubspot(workspace_id)
            logger.info("HubSpot integration removed for workspace_id=%s", workspace_id)
            return

        # 1b. Check notifications_enabled flag (set via SettingsPage)
        slack_integ_check = await self.storage.get_integration(
            workspace_id, Provider.SLACK
        )
        if slack_integ_check:
            notifs_enabled = slack_integ_check.metadata.get(
                "notifications_enabled", True
            )
            if not notifs_enabled:
                logger.info(
                    "Notifications disabled for workspace %s — skipping event %s",
                    workspace_id,
                    sub_type,
                )
                return

        # 2. Determine Object Type
        obj_type = self._map_subscription_to_type(sub_type, event)
        if not obj_type:
            logger.info("Skipping unhandled subscription type: %s", sub_type)
            return

        # 3. Fetch Object from HubSpot
        logger.info("Fetching %s %s for analysis", obj_type, object_id)
        obj = await self.hubspot.get_object(
            workspace_id=workspace_id, object_type=obj_type, object_id=object_id
        )
        if not obj:
            logger.warning("Could not fetch %s %s", obj_type, object_id)
            return

        # Inject portalId for deep linking
        if isinstance(obj, dict):
            obj["portalId"] = portal_id

        # 4. Perform AI Analysis
        analysis = await self.ai.analyze_polymorphic(obj, obj_type)

        # 5. Check Notification Threshold
        # Always notify on creation events so new tickets/contacts/deals
        # are never silently dropped, regardless of priority.
        is_creation = "creation" in sub_type
        if not is_creation and not self._should_notify(analysis, event):
            logger.info(
                "Skipping notification for %s %s (below threshold)", obj_type, object_id
            )
            return

        # 6. Resolve Target Slack Integration (Advanced Routing)
        is_enterprise = await self.integration_service.is_at_least_tier(
            workspace_id, PlanTier.PRO
        )

        slack_integ = None
        if is_enterprise:
            # Advanced Routing: Match integration by territory or fallback
            all_integrations = await self.storage.list_integrations(
                workspace_id, Provider.SLACK
            )

            # Heuristic: Match 'hs_territory' against 'routing_key' in metadata
            territory = obj.get("properties", {}).get("hs_territory")
            if territory:
                for integ in all_integrations:
                    if integ.metadata.get("routing_key") == territory:
                        slack_integ = integ
                        logger.info(
                            "Routed notification to Slack team_id=%s for territory=%s",
                            integ.metadata.get("slack_team_id"),
                            territory,
                        )
                        break

            if not slack_integ and all_integrations:
                # Default to primary or first available
                slack_integ = all_integrations[0]
                logger.info(
                    "No territory match; defaulted to primary Slack team_id=%s",
                    slack_integ.metadata.get("slack_team_id"),
                )
        else:
            # Starter/Professional: Single workspace logic
            slack_integ = await self.storage.get_integration(
                workspace_id, Provider.SLACK
            )

        if not slack_integ:
            logger.warning(
                "No target Slack integration found for workspace %s, cannot notify",
                workspace_id,
            )
            return

        # Dynamically resolve MessagingService via registry
        from app.connectors.registry import registry

        manifest = registry.get_connector(
            "slack"
        )  # This logic could be further abstracted to handle multiple providers
        if not manifest or not manifest.channel_service:
            logger.error("MessagingService for slack not found in registry")
            return

        messaging_service_cls = manifest.channel_service
        messaging_service: MessagingService = cast(Any, messaging_service_cls)(
            corr_id=self.corr_id,
            integration_service=self.integration_service,
            slack_integration=slack_integ,
        )

        logger.info("Sending proactive notification for %s %s", obj_type, object_id)
        is_pro = await self.integration_service.is_pro_workspace(workspace_id)

        thread_ts = None
        mapping = None

        if is_pro and obj_type == "ticket":
            # 1. Resolve target channel
            channel = await messaging_service._resolve_channel(workspace_id, None)  # type: ignore
            if channel:
                # 2. Look up existing thread mapping
                mapping = await self.storage.get_thread_mapping(
                    workspace_id=workspace_id,
                    object_type="ticket",
                    object_id=object_id,
                    channel_id=channel,
                )
                if mapping:
                    thread_ts = mapping.thread_ts
                    logger.info("Found existing thread mapping thread_ts=%s", thread_ts)

        # 6. Send Slack Notification
        sent_ts = await messaging_service.send_card(
            workspace_id=workspace_id,
            obj=obj,
            analysis=analysis,
            is_pro=is_pro,
            thread_ts=thread_ts,
        )

        # 7. Persist new thread mapping if this was the first message
        if is_pro and obj_type == "ticket" and sent_ts and not thread_ts:
            channel = await messaging_service._resolve_channel(workspace_id, None)  # type: ignore
            if channel:
                await self.storage.upsert_thread_mapping(
                    {
                        "workspace_id": workspace_id,
                        "object_type": "ticket",
                        "object_id": object_id,
                        "channel_id": channel,
                        "thread_ts": sent_ts,
                    }
                )
                logger.info("Stored new thread mapping thread_ts=%s", sent_ts)

    def _map_subscription_to_type(
        self, sub_type: str, event: dict[str, Any] | None = None
    ) -> str | None:
        # Standard subscription type format:
        # 'ticket.creation', 'deal.propertyChange', etc.
        type_map = {
            "contact": "contact",
            "deal": "deal",
            "company": "company",
            "ticket": "ticket",
            "task": "task",
            "meeting": "meeting",
            "conversation": "conversation",
            "lead": "lead",
        }
        for key, val in type_map.items():
            if key in sub_type:
                return val

        # HubSpot CRM Events format: 'object.creation', 'object.propertyChange'
        # Object type is identified via objectTypeId in the event payload.
        if sub_type.startswith("object.") and event:
            object_type_id_map = {
                "0-1": "contact",
                "0-2": "company",  # HubSpot: 0-2 = companies
                "0-3": "deal",  # HubSpot: 0-3 = deals
                "0-4": "task",
                "0-5": "ticket",
                "0-47": "meeting",
                "0-136": "lead",
            }
            object_type_id = str(event.get("objectTypeId", ""))
            obj_type = object_type_id_map.get(object_type_id)
            if obj_type:
                logger.info(
                    "Mapped object.* event objectTypeId=%s → %s",
                    object_type_id,
                    obj_type,
                )
                return obj_type

        return None

    def _should_notify(  # noqa: PLR0911
        self, analysis: Any, event: dict[str, Any]
    ) -> bool:
        """Determine if a notification should be sent.

        Uses event fields or AI analysis to decide.
        """
        # 1. Ticket priority changed to HIGH or URGENT — always notify.
        if event.get("propertyName") == "hs_ticket_priority" and str(
            event.get("propertyValue", "")
        ).upper() in ("HIGH", "URGENT"):
            return True

        # 2. Ticket pipeline stage changed — always notify.
        if event.get("propertyName") == "hs_pipeline_stage":
            return True

        # 3. Deal stage changed to closed-won or closed-lost — always notify.
        if event.get("propertyName") == "dealstage" and str(
            event.get("propertyValue", "")
        ).lower() in ("closedwon", "closedlost"):
            return True

        # 4. Task status changed — always notify.
        if event.get("propertyName") == "hs_task_status":
            return True

        # 3. AI-driven: Deals with High/Critical risk
        if hasattr(analysis, "risk"):
            if analysis.risk in ["High", "Critical"]:
                return True

        # 4. AI-driven: Tickets with High/Critical urgency
        if hasattr(analysis, "urgency"):
            if analysis.urgency in ["High", "Critical"]:
                return True

        # 5. AI-driven: Contacts with score >= threshold
        if hasattr(analysis, "score"):
            try:
                if int(analysis.score) >= self.AI_SCORE_THRESHOLD:
                    return True
            except (ValueError, TypeError):
                pass

        # 6. Conversations: always notify
        if hasattr(analysis, "status") and "Conversation" in str(
            getattr(analysis, "summary", "")
        ):
            return True

        # Default: suppress to keep signal-to-noise ratio high
        return False
