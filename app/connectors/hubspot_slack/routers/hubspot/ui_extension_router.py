from __future__ import annotations

import asyncio
from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException, Query

from app.connectors.hubspot_slack.hubspot_renderer import HubSpotRenderer
from app.core.dependencies import (
    get_ai_service,
    get_hubspot_service,
    get_integration_service,
    get_workspace_id,
)
from app.core.logging import get_logger
from app.domains.ai.service import AIService
from app.domains.crm.hubspot.service import HubSpotService
from app.domains.crm.integration_service import IntegrationService
from app.domains.crm.ui import CardBuilder

router = APIRouter(prefix="/hubspot/ui-extension", tags=["hubspot-ui-extension"])
logger = get_logger("hubspot.ui_extension")


@router.get("/insight")
async def get_insight(
    object_id: str = Query(..., alias="objectId"),
    hs_object_type: str = Query(..., alias="hs_object_type"),
    workspace_id: str = Depends(get_workspace_id),
    integration_service: IntegrationService = Depends(get_integration_service),
    hubspot: HubSpotService = Depends(get_hubspot_service),
    ai: AIService = Depends(get_ai_service),
) -> dict[str, Any]:
    """Return the UnifiedCard IR for rendering inside the HubSpot React sidebar.

    Fetches the CRM object, recent engagements, and Pro plan status in parallel,
    then runs AI analysis and renders the result to the HubSpot UI Extensions
    JSON format consumed by MirrorCard.tsx.

    Args:
        object_id: The HubSpot CRM object ID.
        hs_object_type: The HubSpot object type (e.g. ``0-1`` for contacts).
        workspace_id: Internal workspace ID resolved from ``portalId``.
        integration_service: Integration service (injected).
        hubspot: HubSpot service (injected).
        ai: AI analysis service (injected).

    """
    logger.info("Fetching UI extension insight for %s %s", hs_object_type, object_id)

    # Fetch object, engagements, and Pro status in parallel
    (obj, engagements), is_pro = await asyncio.gather(
        asyncio.gather(
            hubspot.get_object(
                workspace_id=workspace_id,
                object_type=hs_object_type,
                object_id=object_id,
            ),
            hubspot.get_object_engagements(workspace_id, hs_object_type, object_id),
        ),
        integration_service.is_pro_workspace(workspace_id),
    )
    if not obj:
        raise HTTPException(status_code=404, detail="Object not found")

    analysis = await ai.analyze_polymorphic(
        obj,
        hs_object_type,
        # Shown as structured tile — excluded from AI text
        engagements=None,
        # Shown via CrmAssociationTable — excluded from AI text
        associated_objects=None,
    )

    unified_card = CardBuilder().build(obj, cast(Any, analysis), is_pro=is_pro)
    return HubSpotRenderer().render(
        object_id, unified_card, object_type=hs_object_type, engagements=engagements
    )
