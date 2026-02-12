# app/api/hubspot/router.py
from fastapi import APIRouter, Depends, Request
from app.services.hubspot_webhook_service import HubSpotWebhookService
from app.api.deps import get_hubspot_connector

router = APIRouter(prefix="/hubspot")

@router.post("/events")
async def hubspot_events(
    request: Request,
    connector = Depends(get_hubspot_connector)
):
    body = await request.body()
    headers = request.headers
    return await HubSpotWebhookService.process_webhook(headers, body, connector)