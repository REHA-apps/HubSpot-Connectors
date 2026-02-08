from fastapi import APIRouter, Request, HTTPException, BackgroundTasks
from app.core.security import verify_hubspot_signature
from app.connectors.slack.actions import SlackConnector
from app.connectors.hubspot.client import HubSpotClient
from app.services.storage_service import StorageService
from app.connectors.slack.ui import build_contact_card
import httpx

router = APIRouter()

@router.post("/events")
async def hubspot_events(request: Request):
    signature = request.headers.get("X-HubSpot-Signature")
    if not signature:
        raise HTTPException(status_code=401, detail="Missing signature header")

    body = await request.body()

    if not verify_hubspot_signature(
        signature,
        body,
        str(request.url)
    ):
        raise HTTPException(status_code=401, detail="Invalid signature")

    events = await request.json()
    connector = SlackConnector()

    for event in events:
        await connector.send_event({
            "type": event["eventType"],
            "object_id": event["objectId"]
        })

    return {"status": "ok"}

@router.post("/uninstall")
async def uninstall(payload: dict):
    # delete tokens, cleanup
    print("App uninstalled:", payload)
    return {"status": "ok"}



async def process_hubspot_search(team_id: str, user_query: str, response_url: str):
    try:
        # 1. Get tokens from Supabase
        integration = await StorageService.get_by_slack_id(team_id)
        if not integration:
            async with httpx.AsyncClient() as client:
                await client.post(response_url, json={"text": "❌ App not connected. Please install via the home page."})
            return
        # 2. Search HubSpot
        token = integration.get('access_token') or integration.get('hubspot_access_token')
        if not token:
            async with httpx.AsyncClient() as client:
                await client.post(response_url, json={"text": "❌ HubSpot access token not found. Please reconnect the app."})
            return
        hs_client = HubSpotClient(token) # Check if your DB column is 'access_token' or 'hubspot_access_token'
        contact = await hs_client.get_contact_by_email(user_query)

        if not contact:
            async with httpx.AsyncClient() as client:
                await client.post(response_url, json={"text": f"❌ No contact found for '{user_query}'"})
            return

        # 3. Generate AI Summary
        company = contact.get('properties', {}).get('company', 'Unknown Company')
        ai_insight = f"This lead is from {company}. They were recently updated in HubSpot."

        # 4. Build and Send UI
        payload = build_contact_card(contact, ai_insight)

        async with httpx.AsyncClient() as client:
            await client.post(response_url, json=payload)

    except Exception as e:
        print(f"Error in background task: {str(e)}")
        async with httpx.AsyncClient() as client:
            await client.post(response_url, json={"text": f"⚠️ Error: {str(e)}"})

@router.post("/slack/commands")
async def handle_commands(request: Request, background_tasks: BackgroundTasks):
    form_data = await request.form()
    user_query = form_data.get("text")      # e.g., "john@apple.com"
    team_id = form_data.get("team_id")      # Slack Workspace ID
    response_url = form_data.get("response_url")

    # Validate that the required fields are strings and not None
    if not isinstance(team_id, str) or not team_id:
        raise HTTPException(status_code=400, detail="Missing or invalid team_id")
    if not isinstance(user_query, str) or not user_query:
        raise HTTPException(status_code=400, detail="Missing or invalid search query")
    if not isinstance(response_url, str) or not response_url:
        raise HTTPException(status_code=400, detail="Missing or invalid response_url")

    print(f"DEBUG: Team ID is {team_id}")
    # print(f"--- YOUR REAL SLACK TEAM ID IS: {team_id} ---")

    # return {"text": f"I caught your Team ID: {team_id}"}
    # Start the HubSpot search in the background so Slack doesn't timeout
    background_tasks.add_task(process_hubspot_search, team_id, user_query, response_url)

    # Respond to Slack immediately (within 3 seconds)
    return {"text": f"🔎 Searching HubSpot for {user_query}..."}
