from fastapi import APIRouter, Query
from app.connectors.hubspot.oauth import exchange_hubspot_code
from app.services.storage_service import StorageService
import os

router = APIRouter()

@router.get("/hubspot")
async def hubspot_callback(code: str = Query(...), error: str | None = None):
    """This is where HubSpot sends the user after they click 'Approve'."""
    # Check if HubSpot sent an error
    if error:
        return {"error": f"HubSpot Auth Failed: {error}"}
    try:
        # 2. Exchange the temporary code for real tokens
        # This calls your auth service which handles the POST request
        tokens = await exchange_hubspot_code(code)

        if not tokens or 'access_token' not in tokens:
            return {"error": "Failed to retrieve tokens from HubSpot"}

        # 3. Save these tokens to Supabase
        await StorageService.save_integration({
            "portal_id": str(tokens.get('portal_id')),
            "access_token": tokens.get('access_token'),
            "refresh_token": tokens.get('refresh_token'),
            "expires_in": tokens.get('expires_in'),
            "slack_team_id": "T0ADL24SKF0", # Use your real Team ID here later
            "slack_bot_token": os.getenv("SLACK_BOT_TOKEN")
        })

        return {"message": "Installation Successful! You can close this tab and try /hs-find in Slack."}

    except Exception as e:
        return {"error": f"Internal Server Error: {str(e)}"}
