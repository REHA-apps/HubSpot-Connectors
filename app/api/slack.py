import shlex

import httpx
from fastapi import APIRouter, BackgroundTasks, HTTPException, Request

from app.api.hubspot import exchange_hubspot_code
from app.core.security import verify_slack_signature
from app.integrations.client import HubSpotClient
from app.integrations.slack.ui import build_contact_card
from app.services.ai_service import AIService
from app.services.storage_service import StorageService
from app.utils.helpers import send_slack_error, send_slack_response

router = APIRouter()


@router.get("/oauth/callback")
async def slack_oauth_callback(code: str, state: str):
    """Callback for HubSpot OAuth redirect."""
    try:
        # 1. Exchange code for tokens
        token_data = await exchange_hubspot_code(code)

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


# --- Helpers ---


def parse_command_text(text: str) -> dict:
    try:
        parts = shlex.split(text)
        return dict(part.split("=", 1) for part in parts if "=" in part)
    except Exception:
        return {}


async def send_delayed_slack_response(response_url: str, payload: dict):
    """Sends a delayed response to Slack using the response_url."""
    async with httpx.AsyncClient() as client:
        await client.post(response_url, json=payload)


# --- Background Task ---


async def process_hs_find_task(team_id: str, email: str, response_url: str):
    """
    Handles the heavy lifting:

    Fetch DB -> Search HubSpot -> Get AI Insights -> Send to Slack.
    """
    try:
        # 1. Fetch the integration using your storage service
        integration = await StorageService.get_by_slack_id(team_id)
        if not integration:
            await send_slack_error(
                response_url, "HubSpot is not connected to this Slack workspace."
            )
            return

        # 2. Extract tokens using your hubspot_ prefixed keys
        token = integration.access_token
        refresh = integration.refresh_token
        portal_id = integration.portal_id

        if not token or not refresh:
            await send_slack_error(
                response_url, "HubSpot credentials missing. Please re-authenticate."
            )
            return

        # 3. Initialize the client (Auto-refresh is handled inside the client)
        hs_client = HubSpotClient(
            access_token=token, refresh_token=refresh, slack_team_id=team_id
        )

        # 4. Search for the contact
        contact = await hs_client.get_contact_by_email(email)

        if not contact:
            await send_slack_response(
                response_url, {"text": f"🔍 No HubSpot contact found for *{email}*"}
            )
            return

        # 5. Inject portal_id for the 'Open in HubSpot' button in your UI
        contact["portal_id"] = portal_id

        # 6. Get AI Insights
        try:
            ai_insight = AIService.generate_contact_insight(contact)
        except Exception:
            ai_insight = "AI summary currently unavailable."

        # 7. Build and send the final Block Kit card
        payload = build_contact_card(contact, ai_insight)
        await send_slack_response(response_url, payload)

    except Exception as e:
        print(f"🔥 Background Task Error: {str(e)}")
        await send_slack_error(
            response_url, "An internal error occurred during the search."
        )


# --- Routes ---


@router.post("/commands")
async def slack_commands(request: Request, background_tasks: BackgroundTasks):
    """
    Endpoint for Slack Slash Commands.
    """
    # Verify the request is actually from Slack
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

        # 🚀 THE CRITICAL STEP:
        # Start the background task and return 200 OK to Slack
        # immediately (< 3 seconds)
        background_tasks.add_task(process_hs_find_task, team_id, text, response_url)

        return {
            "response_type": "ephemeral",
            "text": f"🔎 Searching HubSpot for *{text}*...",
        }

    return {"text": "Unknown command received."}


# @router.post("/interactions")
# async def slack_interactions(request: Request):
#     """Handles Slack interactive components (buttons, modals)."""
#     form_data = await request.form()
#     payload_str = form_data.get("payload")

#     if not isinstance(payload_str, str):
#         return {"text": "❌ Invalid or missing payload"}

#     try:
#         payload = json.loads(payload_str)
#     except json.JSONDecodeError:
#         return {"text": "❌ Error parsing payload"}

#     team_id = payload.get("team", {}).get("id")
#     if not team_id:
#         return {"text": "❌ Missing Team ID in payload"}

#     actions = payload.get("actions", [])
#     if actions and actions[0].get("value") == "create_contact":
#         integration = await StorageService.get_by_slack_id(team_id)
#         if not integration:
#             return
# {"text": "❌ App not connected. Please install via the home page."}

#         token = integration.get("hubspot_access_token") or integration.get(
#             "access_token"
#         )
#         if not token:
#             return {"text": "❌ HubSpot access token not found."}

#         refresh = integration.get("hubspot_refresh_token") or integration.get(
#             "refresh_token"
#         )
#         if not refresh:
#             return {"text": "❌ HubSpot refresh token not found."}
#         hubspot_client = HubSpotClient(
#             access_token=token, refresh_token=refresh, slack_team_id=team_id
#         )
#         try:
#             properties = HubSpotContactProperties(
#             email="fromslack@example.com", firstname="Slack", lastname="User"
#             )
#             await hubspot_client.create_contact(properties)
#             return {"text": "Contact created 🚀"}
#         except Exception as e:
#             return {"text": f"❌ Error creating contact: {str(e)}"}

#     return {"text": "Interaction received"}


# @router.post("/interactions")
# async def slack_interactions(request: Request):
#     form_data = await request.form()
#     payload_str = form_data.get("payload")

#     if not isinstance(payload_str, str):
#         return {"text": "❌ Invalid payload"}

#     payload = json.loads(payload_str)

#     # 1. Identify if this is a Modal Submission
#     if payload.get("type") == "view_submission":
#         view = payload.get("view", {})
#         team_id = payload.get("team", {}).get("id")

#         # 2. Extract values from the Modal state
#         # Note:
#  'block_email' and 'action_email' must match your Modal Block Kit IDs
#         values = view.get("state", {}).get("values", {})

#         try:
#             # This extraction logic depends on how you built your Modal blocks
#             email =
#             values.get("block_email", {}).get("action_email", {}).get("value")
#             first_name =
#             values.get("block_first", {}).get("action_first", {}).get("value")
#             last_name =
#  values.get("block_last", {}).get("action_last", {}).get("value")

#             if not email:
#                 return
# {"response_action": "errors", "errors": {"block_email": "Email is required"}}

#             # 3. Connect to HubSpot
#             integration = await StorageService.get_by_slack_id(team_id)
#             token =
# integration.get('hubspot_access_token') or integration.get('access_token')
#             hs_client = HubSpotClient(token)

#             # 4. Create the Contact with Dynamic Data
#             properties = HubSpotContactProperties(
#                 email=email,
#                 firstname=first_name,
#                 lastname=last_name
#             )
#             await hs_client.create_contact(properties)

#             # 5. Tell Slack the submission was successful (empty response)
#             return {}

#         except Exception as e:
#             print(f"Error processing modal: {e}")
#             return
#  {"response_action": "errors", "errors":
#  {"block_email": "Failed to create contact."}}

#     # Handle existing button actions (if still needed)
#     return {"text": "Action received"}
