from fastapi import APIRouter, Depends, BackgroundTasks, HTTPException, Request
from app.api.slack.schemas import SendMessageSchema
from app.api.deps import get_slack_connector, get_hubspot_connector
from app.integrations.security import verify_slack_signature
from app.services.slack_service import handle_hubspot_contact_search
from app.api.hubspot.service import HubSpotConnector
from app.api.slack.service import SlackConnector

router = APIRouter(prefix="/slack")

@router.post("/send")
async def send_message(
    payload: SendMessageSchema,
    slack: SlackConnector = Depends(get_slack_connector)
):
    """Send a simple Slack message via DI connector."""
    return await slack.send_event({"channel": payload.channel, "text": payload.text})


@router.post("/slack-search")
async def handle_slack_search(
    request: Request,
    background_tasks: BackgroundTasks,
    slack: SlackConnector = Depends(get_slack_connector),
    hubspot: HubSpotConnector = Depends(get_hubspot_connector),
):
    """Handles Slack slash commands to search HubSpot."""
    form_data = await request.form()
    user_query = form_data.get("text")
    team_id = form_data.get("team_id")
    response_url = form_data.get("response_url")

    if not all([team_id, user_query, response_url]):
        raise HTTPException(status_code=400, detail="Missing required Slack fields")

    # Run the HubSpot search in background
    background_tasks.add_task(
        handle_hubspot_contact_search, team_id, user_query, response_url
    )

    return {"text": f"🔎 Searching HubSpot for {user_query}..."}


@router.post("/commands")
async def slack_commands(
    request: Request,
    background_tasks: BackgroundTasks,
    slack: SlackConnector = Depends(get_slack_connector),
    hubspot: HubSpotConnector = Depends(get_hubspot_connector),
):
    """Endpoint for Slack Slash Commands with signature verification."""
    body = await request.body()
    if not verify_slack_signature(request.headers, body):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    form = await request.form()
    command = form.get("command")
    text = str(form.get("text", "")).strip()
    team_id = str(form.get("team_id", ""))
    response_url = str(form.get("response_url", ""))

    if command == "/hs-find":
        if not text:
            return {"text": "❌ Please provide an email: `/hs-find user@example.com`"}

        # Background task triggers HubSpot search via connector
        background_tasks.add_task(
            handle_hubspot_contact_search, team_id, text, response_url
        )

        return {
            "response_type": "ephemeral",
            "text": f"🔎 Searching HubSpot for *{text}*...",
        }

    return {"text": "Unknown command received."}
