from app.api.hubspot.client import HubSpotClient
from app.integrations.slack.ui import build_contact_card
from app.integrations.ai_service import AIService
from app.db.supabase import StorageService
from app.utils.helpers import send_slack_error, send_slack_response

async def handle_hubspot_contact_search(team_id: str, email: str, response_url: str):
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

