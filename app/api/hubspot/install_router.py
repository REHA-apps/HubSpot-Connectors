# app/api/hubspot/install_router.py
from fastapi import APIRouter
from fastapi.responses import RedirectResponse
from app.core.config import settings
import secrets
router = APIRouter(prefix="/hubspot", tags=["hubspot-install"])

@router.get("/install")
async def hubspot_install():
    state = secrets.token_urlsafe(32)
    oauth_url = (
        "https://app.hubspot.com/oauth/authorize"
        f"?client_id={settings.HUBSPOT_CLIENT_ID}"
        f"&redirect_uri={settings.HUBSPOT_REDIRECT_URI}"
        f"&scope={settings.HUBSPOT_SCOPES_ENCODED}"
        f"&state={state}"
    )
    return RedirectResponse(oauth_url)



