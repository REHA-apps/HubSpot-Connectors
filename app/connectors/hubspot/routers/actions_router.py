# app/api/hubspot/actions_router.py
from fastapi import APIRouter, Depends, HTTPException

from app.core.dependencies import (
    get_ai_service,
    get_hubspot_service,
    get_integration_service,
)
from app.core.logging import get_corr_id
from app.db.records import Provider
from app.domains.ai.service import AIService
from app.domains.crm.channel_service import ChannelService
from app.domains.crm.hubspot.service import HubSpotService
from app.domains.crm.integration_service import IntegrationService

router = APIRouter(prefix="/hubspot/actions", tags=["hubspot-actions"])


@router.post("/send-ai-insights-to-slack")
async def send_ai_insights_to_slack(
    objectId: str,
    portalId: str,
    channel: str | None = None,
    corr_id: str = Depends(get_corr_id),
    hubspot: HubSpotService = Depends(get_hubspot_service),
    ai: AIService = Depends(get_ai_service),
    integration_service: IntegrationService = Depends(get_integration_service),
):
    contact = await hubspot.get_contact(portalId, objectId)
    if not contact:
        raise HTTPException(404, "Contact not found")

    analysis = ai.analyze_contact(contact)

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
