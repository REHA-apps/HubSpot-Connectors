from fastapi import APIRouter, Request, HTTPException
from app.core.security import verify_slack_signature
from app.connectors.hubspot.client import HubSpotClient
from app.connectors.hubspot.models import HubSpotContactProperties
from app.services.storage_service import StorageService


router = APIRouter()

@router.post("/commands")
async def slack_command(request: Request):
    body = await request.body()

    if not verify_slack_signature(request.headers, body):
        raise HTTPException(status_code=401)

    form = await request.form()
    text = form.get("text")  # user input
    team_id = form.get("team_id")  # Slack team ID to retrieve HubSpot token

    # Validate that the required fields are strings and not None
    if not isinstance(text, str) or not text:
        raise HTTPException(status_code=400, detail="Missing or invalid text")
    if not isinstance(team_id, str) or not team_id:
        raise HTTPException(status_code=400, detail="Missing or invalid team_id")

    # Example input: email=a@b.com firstname=John
    data = dict(item.split("=") for item in text.split())

    # Get HubSpot access token from storage
    if not team_id:
        raise HTTPException(status_code=400, detail="Missing team_id")

    integration = await StorageService.get_by_slack_id(str(team_id))
    if not integration:
        raise HTTPException(status_code=404, detail="HubSpot integration not found")

    access_token = integration.get("hubspot_access_token")
    if not access_token:
        raise HTTPException(status_code=500, detail="HubSpot access token not configured")

    # Create HubSpotClient instance
    hubspot_client = HubSpotClient(access_token=access_token)

    # Convert dict to HubSpotContactProperties Pydantic model
    validated_data = {}
    for key, value in data.items():
        if key == "lead_score_ai":
            try:
                validated_data[key] = int(value)
            except ValueError:
                raise HTTPException(status_code=400, detail=f"{key} must be a valid integer")
        else:
            validated_data[key] = value

    contact_properties = HubSpotContactProperties(**validated_data)


    # Call create_contact with the properties parameter
    await hubspot_client.create_contact(properties=contact_properties)


    return {
        "response_type": "ephemeral",
        "text": "✅ Contact created in HubSpot"
    }
