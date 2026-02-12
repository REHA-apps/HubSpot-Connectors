from fastapi import APIRouter, Query
from app.integrations.oauth import OAuthService
from app.db.supabase import StorageService
from app.core.config import settings

router = APIRouter(prefix="/hubspot/oauth", tags=["hubspot-oauth"])

@router.get("/install/hubspot")
async def hubspot_install_callback(
    code: str = Query(...), state: str = Query(None), error: str | None = None
):
    """Callback for HubSpot app installation."""
    if error:
        return {"error": f"HubSpot Auth Failed: {error}"}
    try:
        tokens = await OAuthService.exchange_hubspot_token(code)

        if not tokens or "access_token" not in tokens:
            return {"error": "Failed to retrieve tokens from HubSpot"}

        data = {
            "hubspot_access_token": tokens.get("access_token"),
            "hubspot_refresh_token": tokens.get("refresh_token"),
            "hubspot_portal_id": str(tokens.get("portal_id")),
            "hubspot_expires_at": tokens.get(
                "expires_in"
            ),  # or calculate actual timestamp
            "slack_bot_token": settings.SLACK_BOT_TOKEN,
        }

        await StorageService.save_integration(
            slack_team_id=state, provider="hubspot", data=data
        )
        return {"message": "Installation Successful!"}
    except Exception as e:
        return {"error": f"Internal Server Error: {str(e)}"}

@router.get("/oauth/callback")
async def hubspot_oauth_callback(code: str, state: str):
    """Callback for HubSpot OAuth redirect."""
    try:
        # 1. Exchange code for tokens
        token_data = await OAuthService.exchange_hubspot_token(code)

        # 2. Extract the goodies
        # HubSpot returns: access_token, refresh_token, expires_in
        data = {
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
            "updated_at": "now()",  # Good practice for tracking
        }

        # 3. Save to Supabase
        await StorageService.save_integration(
            slack_team_id=state, provider="hubspot", data=data
        )

        return {"status": "success", "message": "HubSpot connected successfully!"}

    except Exception as e:
        print(f"❌ OAuth Callback Error: {str(e)}")
        return {"status": "error", "message": str(e)}

