# app/api/hubspot/actions_router.py
from fastapi import APIRouter, Depends, HTTPException
from app.core.logging import get_corr_id
from app.integrations.ai_service import AIService
from app.services.hubspot_service import HubSpotService
from app.services.channel_service import ChannelService
from app.services.integration_service import IntegrationService
from fastapi import Request 
from app.db.records import Provider

router = APIRouter(prefix="/api/hubspot/actions", tags=["hubspot-actions"])

@router.post("/send-ai-insights-to-slack")
async def send_ai_insights_to_slack(
    objectId: str,
    portalId: str,
    channel: str | None = None,
    corr_id: str = Depends(get_corr_id),
):
    hubspot = HubSpotService(corr_id=corr_id)
    ai = AIService()
    ai.set_corr_id(corr_id)

    contact = await hubspot.get_contact(objectId, portalId)
    if not contact:
        raise HTTPException(404, "Contact not found")

    analysis = ai.analyze_contact(contact)

    integration_service = IntegrationService(corr_id=corr_id)
    slack_integration = await integration_service.get_integration(
        workspace_id=portalId,
        provider=Provider.SLACK,
    )

    channel_service = ChannelService(
        corr_id=corr_id,
        integration_service=integration_service,
        slack_integration=slack_integration,
    )

    await channel_service.send_slack_ai_insights(
        workspace_id=portalId,
        channel=channel,
        analysis=analysis,
    )

    return {"status": "ok"}
