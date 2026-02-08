from fastapi import APIRouter, Request, HTTPException, BackgroundTasks, Query
from typing import Dict, Any
from app.core.config import settings
from app.core.security import verify_hubspot_signature
from app.integrations.client import HubSpotClient
from app.services.storage_service import StorageService
from app.services.ai_service import AIService
from app.utils.helpers import HTTPClient, send_slack_error, send_slack_response

router = APIRouter()

# --- OAuth & Installation ---

async def exchange_hubspot_code(code: str) -> Dict[str, Any]:
    """Exchanges a temporary code for permanent tokens."""
    url = "https://api.hubapi.com/oauth/v1/token"
    data = {
        "grant_type": "authorization_code",
        "client_id": settings.HUBSPOT_CLIENT_ID,
        "client_secret": settings.HUBSPOT_CLIENT_SECRET,
        "redirect_uri": settings.HUBSPOT_REDIRECT_URI,
        "code": code
    }

    client = HTTPClient.get_client()
    response = await client.post(url, data=data)
    response.raise_for_status()
    return response.json()

@router.get("/install/hubspot")
async def hubspot_install_callback(code: str = Query(...), state: str = Query(None), error: str | None = None):
    """Callback for HubSpot app installation."""
    if error:
        return {"error": f"HubSpot Auth Failed: {error}"}
    try:
        tokens = await exchange_hubspot_code(code)

        if not tokens or 'access_token' not in tokens:
            return {"error": "Failed to retrieve tokens from HubSpot"}

        portal_id = tokens.get('portal_id')
        await StorageService.save_integration({
            "portal_id": str(portal_id) if portal_id is not None else "",
            "access_token": tokens.get('access_token'),
            "refresh_token": tokens.get('refresh_token'),
            "expires_in": tokens.get('expires_in', 1800),
            "slack_team_id": state,
            "slack_bot_token": settings.SLACK_BOT_TOKEN
        })

        return {"message": "Installation Successful! You can close this tab and try /hs-find in Slack."}

    except Exception as e:
        return {"error": f"Internal Server Error: {str(e)}"}

@router.get("/oauth/callback")
def hubspot_oauth_callback(code: str = Query(...)):
    """General OAuth callback (if different from install)."""
    return {"status": "hubspot connected"}

# --- Webhooks & Events ---

@router.post("/events")
async def hubspot_events(request: Request):
    """Handles incoming HubSpot event webhooks."""
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
    # Note: Logic moved to dynamic integration flow
    from app.integrations.slack.actions import SlackConnector # Local import to avoid circular dep if any
    connector = SlackConnector()

    for event in events:
        await connector.send_event({
            "type": event.get("eventType"),
            "object_id": event.get("objectId")
        })

    return {"status": "ok"}

@router.post("/uninstall")
async def hubspot_uninstall(payload: dict):
    """Handles app uninstallation webhooks from HubSpot."""
    # TODO: Implement token cleanup in StorageService
    print("HubSpot App uninstalled:", payload)
    return {"status": "ok"}

# --- Slack Integration Background Tasks ---

async def process_hubspot_search(team_id: str, user_query: str, response_url: str):
    """Background task to search HubSpot and send results to Slack."""
    from app.integrations.slack.ui import build_contact_card # Local import
    try:
        integration = await StorageService.get_by_slack_id(team_id)
        if not integration:
            await send_slack_error(response_url, "App not connected. Please install via the home page.")
            return

        token = integration.get('hubspot_access_token') or integration.get('access_token')
        refresh = integration.get("hubspot_refresh_token") or integration.get("refresh_token")
        if not token:
            await send_slack_error(response_url, "HubSpot access token not found. Please reconnect the app.")
            return
        if not refresh:
            await send_slack_error(response_url, "HubSpot refresh token not found. Please reconnect the app.")
            return

        hs_client = HubSpotClient(
            access_token=token,
            refresh_token=refresh,
            slack_team_id=team_id
        )
        contact = await hs_client.get_contact_by_email(user_query)

        if not contact:
            await send_slack_error(response_url, f"No contact found for '{user_query}'")
            return

        ai_insight = AIService.generate_contact_insight(contact)

        payload = build_contact_card(contact, ai_insight)
        await send_slack_response(response_url, payload)

    except Exception as e:
        print(f"Error in background task: {str(e)}")
        await send_slack_error(response_url, f"An internal error occurred: {str(e)}")

@router.post("/slack-search")
async def handle_slack_search(request: Request, background_tasks: BackgroundTasks):
    """Handles Slack slash commands to search HubSpot."""
    form_data = await request.form()
    user_query = form_data.get("text")
    team_id = form_data.get("team_id")
    response_url = form_data.get("response_url")

    if not isinstance(team_id, str) or not team_id:
        raise HTTPException(status_code=400, detail="Missing or invalid team_id")
    if not isinstance(user_query, str) or not user_query:
        raise HTTPException(status_code=400, detail="Missing or invalid search query")
    if not isinstance(response_url, str) or not response_url:
        raise HTTPException(status_code=400, detail="Missing or invalid response_url")

    background_tasks.add_task(process_hubspot_search, team_id, user_query, response_url)

    return {"text": f"🔎 Searching HubSpot for {user_query}..."}
