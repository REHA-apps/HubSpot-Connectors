from __future__ import annotations

from typing import Any, cast

from fastapi import APIRouter, Depends, HTTPException

from app.connectors.hubspot.ui import CardBuilder
from app.core.dependencies import (
    get_ai_service,
    get_corr_id,
    get_hubspot_service,
    get_integration_service,
)
from app.core.logging import CorrelationAdapter, get_logger
from app.domains.ai.service import AIService
from app.domains.crm.hubspot.service import HubSpotService
from app.domains.crm.integration_service import IntegrationService

router = APIRouter(prefix="/hubspot/ui-extension", tags=["hubspot-ui-extension"])
logger = get_logger("hubspot.ui_extension")


@router.get("/insight")
async def get_insight(
    objectId: str,
    portalId: str,
    hs_object_type: str,
    corr_id: str = Depends(get_corr_id),
    integration_service: IntegrationService = Depends(get_integration_service),
    hubspot: HubSpotService = Depends(get_hubspot_service),
    ai: AIService = Depends(get_ai_service),
) -> dict[str, Any]:
    """Description:
    Endpoint for HubSpot Modern UI Extensions (React).
    Returns the UnifiedCard IR for rendering inside HubSpot Sidebar.
    """
    log = CorrelationAdapter(logger, corr_id)
    log.info("Fetching UI extension insight for %s %s", hs_object_type, objectId)

    # 1. Fetch Object
    obj = await hubspot.get_object(
        workspace_id=portalId,
        object_type=hs_object_type,
        object_id=objectId,
    )
    if not obj:
        raise HTTPException(status_code=404, detail="Object not found")

    # 2. Run Analysis

    # Universally fetch engagements (now cached behind AsyncTTL)
    engagements = await hubspot.get_object_engagements(
        portalId, hs_object_type, objectId
    )
    log.info(
        "Engagements fetched for %s card: %s",
        hs_object_type,
        len(engagements) if engagements else 0,
    )

    # Universally fetch all associated contacts, deals, companies, and tickets
    associated_objects = await hubspot.get_all_associations(
        portalId, hs_object_type, objectId
    )
    total_assocs = sum(len(objs) for objs in associated_objects.values())
    log.info("Associations fetched for %s card: %s", hs_object_type, total_assocs)

    analysis = await ai.analyze_polymorphic(
        obj,
        hs_object_type,
        engagements=engagements,
        associated_objects=associated_objects,
    )
    log.info("Object type: %s", hs_object_type)
    log.info("Engagement sample: %s", engagements[:1] if engagements else None)
    # 3. Build Unified IR
    is_pro = await integration_service.is_pro_workspace(portalId)
    builder = CardBuilder()
    unified_card = builder.build(obj, cast(Any, analysis), is_pro=is_pro)

    # 4. Return IR directly (Modern Extensions consumed JSON)
    return unified_card.model_dump()
