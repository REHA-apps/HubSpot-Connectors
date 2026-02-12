from fastapi import APIRouter, HTTPException, Request, Depends
from app.integrations.security import verify_hubspot_signature
from app.api.deps import get_hubspot_connector
from app.api.hubspot.service import HubSpotConnector

router = APIRouter(prefix="/hubspot")

@router.post("/events")
async def hubspot_events(
    request: Request,
    hubspot: HubSpotConnector = Depends(get_hubspot_connector),
):
    """Handles incoming HubSpot event webhooks."""
    signature = request.headers.get("X-HubSpot-Signature")
    if not signature:
        raise HTTPException(status_code=401, detail="Missing signature header")

    body = await request.body()

    if not verify_hubspot_signature(signature, body, str(request.url)):
        raise HTTPException(status_code=401, detail="Invalid signature")

    events = await request.json()
    # Forward events to HubSpotConnector which handles Slack notifications internally
    for event in events:
        await hubspot.handle_event(
            {
                "contact": event.get("object"),
                "type": event.get("eventType"),
                "object_id": event.get("objectId"),
            },
            channel="#general",  # Or configure dynamically
        )

    return {"status": "ok"}


@router.post("/uninstall")
async def hubspot_uninstall(payload: dict):
    """Handles app uninstallation webhooks from HubSpot."""
    # TODO: Implement token cleanup in StorageService
    print("HubSpot App uninstalled:", payload)
    return {"status": "ok"}
