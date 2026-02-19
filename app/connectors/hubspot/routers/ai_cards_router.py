# app/api/hubspot/ai_cards_router.py
from fastapi import APIRouter, Depends, HTTPException, Request

from app.core.dependencies import get_ai_service, get_hubspot_service
from app.core.logging import get_corr_id, get_logger
from app.domains.ai.service import AIService
from app.domains.crm.hubspot.service import HubSpotService

router = APIRouter(prefix="/hubspot/ai", tags=["hubspot-ai"])
logger = get_logger("hubspot.ai")


@router.get("/contact-analysis")
async def contact_analysis(
    request: Request,
    objectId: str,
    portalId: str,
    corr_id: str = Depends(get_corr_id),
    hubspot: HubSpotService = Depends(get_hubspot_service),
    ai: AIService = Depends(get_ai_service),
):
    # log = CorrelationAdapter(logger, corr_id)
    if not portalId:
        raise HTTPException(400, "Missing portalId")

    # hubspot and ai injected via Depends()

    contact = await hubspot.get_contact(portalId, objectId)
    if not contact:
        raise HTTPException(404, "Contact not found")

    analysis = ai.analyze_contact(contact)
    return {"analysis": analysis.__dict__}
