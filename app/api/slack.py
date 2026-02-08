from fastapi import APIRouter, Request, HTTPException
import json
import shlex
from app.core.security import verify_slack_signature
from app.integrations.client import HubSpotClient
from app.integrations.schemas import HubSpotContactProperties
from app.services.storage_service import StorageService
from app.api.hubspot import exchange_hubspot_code
from app.integrations.slack.ui import build_contact_card
from app.services.ai_service import AIService
router = APIRouter()

def parse_command_text(text: str) -> dict:
    """Parses Slack command text like 'email=a@b.com name=John' into a dict."""
    try:
        parts = shlex.split(text)
        return dict(part.split('=', 1) for part in parts if '=' in part)
    except Exception:
        return {}

@router.get("/oauth/callback")
async def slack_oauth_callback(code: str, state: str):
    """Callback for HubSpot OAuth redirect."""
    try:
        # 1. Exchange code for tokens
        token_data = await exchange_hubspot_code(code)
        
        # 2. Extract the goodies
        # HubSpot returns: access_token, refresh_token, expires_in
        payload = {
            "slack_team_id": state,  # Assuming 'state' is the team_id
            "access_token": token_data.get("access_token"),
            "refresh_token": token_data.get("refresh_token"),
            "updated_at": "now()" # Good practice for tracking
        }

        # 3. Save to Supabase
        await StorageService.save_integration(payload)
        
        return {"status": "success", "message": "HubSpot connected successfully!"}
    
    except Exception as e:
        print(f"❌ OAuth Callback Error: {str(e)}")
        return {"status": "error", "message": str(e)}

@router.post("/commands")
async def slack_commands(request: Request):
    body = await request.body()
    if not verify_slack_signature(request.headers, body):
        raise HTTPException(status_code=401, detail="Invalid Slack signature")

    form = await request.form()
    command = form.get("command")  # e.g., "/hs-find" or "/hs-create"
    text = str(form.get("text", "")).strip()
    team_id = str(form.get("team_id", ""))

    if not team_id:
        raise HTTPException(status_code=400, detail="Missing or invalid team_id")

    data = parse_command_text(text)
    email=data.get("email")

    integration = await StorageService.get_by_slack_id(team_id)
    if not integration:
        return {
            "response_type": "ephemeral",
            "text": "❌ HubSpot integration not found. Please connect your account."
        }
    token = integration.get("hubspot_access_token") or integration.get("access_token")
    refresh = integration.get("hubspot_refresh_token") or integration.get("refresh_token")
    if not token:
        raise HTTPException(status_code=500, detail="HubSpot access token not configured")
    if not refresh:
        raise HTTPException(status_code=500, detail="HubSpot refresh token not configured")
    hubspot_client = HubSpotClient(access_token=token, refresh_token=refresh, slack_team_id=team_id)

    # --- HANDLE /hs-find ---
    if command == "/hs-find":
        if not email:
            return {
                "response_type": "ephemeral",
                "text": "❌ Invalid format. Use: `/hs-find email=user@example.com`"
            }
        try:
            contact = await hubspot_client.get_contact_by_email(email)
            
            if not contact:
                return {"text": f"🔍 No contact found for *{email}*"}

            # 1. Prepare data for the UI helper
            # We inject the portal_id from the database record so the URL button works
            contact["portal_id"] = integration.get("portal_id", "your-portal-id")
            
            # 2. Generate AI summary (or use a fallback)
            try:
                ai_summary = AIService.generate_contact_insight(contact)
            except Exception:
                ai_summary = "No specific AI insights available at this moment."

            # 3. Build the sophisticated Block Kit card
            payload = build_contact_card(contact, ai_summary)
            
            # 4. Add the response type
            payload["response_type"] = "ephemeral"
            
            return payload

        except Exception as e:
            return {"text": f"❌ Search error: {str(e)}"}   
    # --- HANDLE /hs-create (Existing Logic) ---
    elif command == "/hs-create":
        if not data:
            return {
                "response_type": "ephemeral",
                "text": "❌ Invalid format. Use: `/hs-create user@example.com firstname=John lastname=Doe`"
            }        
        try:    
            if "lead_score_ai" in data:
                try:
                    data["lead_score_ai"] = int(data["lead_score_ai"])
                except ValueError:
                    return {"text": "❌ `lead_score_ai` must be an integer"}

            contact_properties = HubSpotContactProperties(**data)
            await hubspot_client.create_contact(properties=contact_properties)

            return {
                "response_type": "ephemeral",
                "text": "✅ Contact created in HubSpot"
            }
        except Exception as e:
            return {
                "response_type": "ephemeral",
                "text": f"❌ Error creating contact: {str(e)}"
            }
    return {"text": "Unknown command"}

@router.post("/interactions")
async def slack_interactions(request: Request):
    """Handles Slack interactive components (buttons, modals)."""
    form_data = await request.form()
    payload_str = form_data.get("payload")

    if not isinstance(payload_str, str):
        return {"text": "❌ Invalid or missing payload"}

    try:
        payload = json.loads(payload_str)
    except json.JSONDecodeError:
        return {"text": "❌ Error parsing payload"}

    team_id = payload.get("team", {}).get("id")
    if not team_id:
        return {"text": "❌ Missing Team ID in payload"}

    actions = payload.get("actions", [])
    if actions and actions[0].get("value") == "create_contact":
        integration = await StorageService.get_by_slack_id(team_id)
        if not integration:
            return {"text": "❌ App not connected. Please install via the home page."}

        token = integration.get('hubspot_access_token') or integration.get('access_token')
        if not token:
            return {"text": "❌ HubSpot access token not found."}

        hs_client = HubSpotClient(token)
        try:
            properties = HubSpotContactProperties(
                email="fromslack@example.com",
                firstname="Slack",
                lastname="User"
            )
            await hs_client.create_contact(properties)
            return {"text": "Contact created 🚀"}
        except Exception as e:
            return {"text": f"❌ Error creating contact: {str(e)}"}

    return {"text": "Interaction received"}


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
#         # Note: 'block_email' and 'action_email' must match your Modal Block Kit IDs
#         values = view.get("state", {}).get("values", {})
        
#         try:
#             # This extraction logic depends on how you built your Modal blocks
#             email = values.get("block_email", {}).get("action_email", {}).get("value")
#             first_name = values.get("block_first", {}).get("action_first", {}).get("value")
#             last_name = values.get("block_last", {}).get("action_last", {}).get("value")

#             if not email:
#                 return {"response_action": "errors", "errors": {"block_email": "Email is required"}}

#             # 3. Connect to HubSpot
#             integration = await StorageService.get_by_slack_id(team_id)
#             token = integration.get('hubspot_access_token') or integration.get('access_token')
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
#             return {"response_action": "errors", "errors": {"block_email": "Failed to create contact."}}

#     # Handle existing button actions (if still needed)
#     return {"text": "Action received"}
