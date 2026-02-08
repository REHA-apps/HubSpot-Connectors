from fastapi import APIRouter, Request
import json
from app.connectors.hubspot.client import HubSpotClient
from app.connectors.hubspot.models import HubSpotContactProperties
from app.services.storage_service import StorageService

router = APIRouter()

@router.post("/interactions")
async def slack_interactions(request: Request):
    form_data = await request.form()
    payload_str = form_data.get("payload")

    if not isinstance(payload_str, str):
        return {"text": "❌ Invalid or missing payload"}

    payload = json.loads(payload_str)

    # Extract team_id to look up integration
    team_id = payload.get("team", {}).get("id")
    if not team_id:
        return {"text": "❌ Missing Team ID in payload"}

    if payload.get("actions") and payload["actions"][0]["value"] == "create_contact":
        # 1. Get tokens from storage
        integration = await StorageService.get_by_slack_id(team_id)
        if not integration:
            return {"text": "❌ App not connected. Please install via the home page."}

        token = integration.get('access_token') or integration.get('hubspot_access_token')
        if not token:
            return {"text": "❌ HubSpot access token not found."}

        # 2. Instantiate client and call create_contact
        hs_client = HubSpotClient(token)
        try:
            properties = HubSpotContactProperties(
                email="fromslack@example.com",
                firstname="Slack",
                hs_analytics_num_visits=None
            )
            await hs_client.create_contact(properties)
            return {"text": "Contact created 🚀"}
        except Exception as e:
            return {"text": f"❌ Error creating contact: {str(e)}"}

    return {"text": "Interaction received"}
