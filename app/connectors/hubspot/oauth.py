from fastapi import APIRouter, Query
import httpx
from app.core.config import settings

router = APIRouter()

@router.get("/callback")
def hubspot_callback(code: str = Query(...)):
    print("HubSpot auth code:", code)
    return {"status": "hubspot connected"}

async def exchange_hubspot_code(code: str):
    """Exchanges a temporary code for permanent tokens."""
    url = "https://api.hubapi.com/oauth/v1/token"
    data = {
        "grant_type": "authorization_code",
        "client_id": settings.HUBSPOT_CLIENT_ID,
        "client_secret": settings.HUBSPOT_CLIENT_SECRET,
        "redirect_uri": settings.HUBSPOT_REDIRECT_URI,
        "code": code
    }

    async with httpx.AsyncClient() as client:
        response = await client.post(url, data=data)
        return response.json()  # Contains access_token and refresh_token
