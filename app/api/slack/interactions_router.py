from fastapi import APIRouter, Depends, Request
from app.api.deps import get_slack_connector
from app.api.slack.service import SlackConnector

router = APIRouter(prefix="/slack")

@router.post("/interactions")
async def slack_interaction(
    request: Request,
    slack: SlackConnector = Depends(get_slack_connector)
):
    event = await request.json()
    # Process the Slack interaction
    return await slack.handle_event(event)

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
