# app/api/hubspot/ai_cards_router.py
from fastapi import APIRouter, Depends, HTTPException, Request
from app.integrations.ai_service import AIService
from app.services.hubspot_service import HubSpotService
from app.core.logging import CorrelationAdapter, get_logger, get_corr_id

router = APIRouter(prefix="/api/hubspot/ai", tags=["hubspot-ai"])
logger = get_logger("hubspot.ai")


@router.get("/contact-analysis")
async def contact_analysis(
    request: Request,
    objectId: str,
    portalId: str,
    corr_id: str = Depends(get_corr_id),
):
    log = CorrelationAdapter(logger, corr_id)
    if not portalId:
        raise HTTPException(400, "Missing portalId")

    hubspot = HubSpotService(corr_id=corr_id)
    ai = AIService()
    ai.set_corr_id(corr_id)

    contact = await hubspot.get_contact(objectId, portalId)
    if not contact:
        raise HTTPException(404, "Contact not found")

    analysis = ai.analyze_contact(contact)
    return {"analysis": analysis.__dict__}