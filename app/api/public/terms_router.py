from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["public"])

@router.get("/terms", response_class=HTMLResponse)
async def terms():
    return """
    <h1>Terms of Service</h1>
    <p>This service provides a Slack integration for HubSpot CRM search.</p>
    <p>By installing the app, you grant permission to access your Slack workspace and HubSpot portal.</p>
    <p>We provide this service as-is without warranties.</p>
    """