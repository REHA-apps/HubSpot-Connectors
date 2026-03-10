from __future__ import annotations

from collections.abc import Mapping
from typing import Any

from app.connectors.hubspot_slack.services.handlers.action_handlers import (
    ActionButtonHandler,
)
from app.connectors.hubspot_slack.services.handlers.base import InteractionHandler
from app.connectors.hubspot_slack.services.handlers.modal_handlers import ModalHandler
from app.connectors.hubspot_slack.services.handlers.object_handlers import (
    ObjectViewHandler,
)
from app.domains.ai.service import AIService
from app.domains.crm.hubspot.service import HubSpotService
from app.domains.crm.integration_service import IntegrationService


class InteractionRegistry:
    """Central registry to route Slack interactions to their specific handlers."""

    def __init__(
        self,
        corr_id: str,
        hubspot: HubSpotService,
        ai: AIService,
        integration_service: IntegrationService,
    ):
        self.corr_id = corr_id

        # Initialize handlers
        self.object_view = ObjectViewHandler(corr_id, hubspot, ai, integration_service)
        self.action_button = ActionButtonHandler(
            corr_id, hubspot, ai, integration_service
        )
        self.modal = ModalHandler(corr_id, hubspot, ai, integration_service)

    def get_handler(
        self, payload: Mapping[str, Any], action_id: str | None = None
    ) -> InteractionHandler | None:
        """Determines the appropriate handler for a given payload."""
        interaction_type = payload.get("type", "")

        if interaction_type == "view_submission":
            return self.modal

        if interaction_type == "block_actions":
            if action_id:
                parts = action_id.split(":")
                prefix = parts[0]

                # Exact prefix routing for object viewing
                if prefix in {
                    "view_object",
                    "select_object",
                    "view_contact_company",
                    "view_contact_deals",
                    "view_company_deals",
                    "view_deals",
                    "view_contacts",
                    "view_contact_meetings",
                }:
                    return self.object_view

                # Exact prefix routing for modals
                if prefix in {
                    "open_add_note_modal",
                    "open_update_lead_type_modal",
                    "open_ai_recap_modal",
                    "reassign_owner",
                    "open_calculator",
                    "schedule_meeting",
                }:
                    return self.modal

                # Exact prefix routing
                if prefix in {
                    "update_deal_stage",
                    "ticket_claim",
                    "ticket_close",
                    "ticket_delete",
                    "ticket_transcript",
                    "gated_feature_click",
                }:
                    return self.action_button

        return None
