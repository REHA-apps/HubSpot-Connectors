from fastapi import APIRouter
from fastapi.responses import HTMLResponse

router = APIRouter(tags=["public"])

@router.get("/privacy", response_class=HTMLResponse)
async def privacy():
    return """
    <h1>Privacy Policy</h1>
    <p>We do not store any personal data beyond what is required to operate the Slack integration.</p>
    <p>We store only workspace identifiers and OAuth tokens needed to communicate with Slack and HubSpot.</p>
    <p>No CRM data is stored on our servers.</p>
    <p>You may uninstall the app at any time to revoke access.</p>
    """