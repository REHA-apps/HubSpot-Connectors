from app.db.supabase import StorageService
from app.api.hubspot.service import HubSpotClient
from app.integrations.ai_service import AIService
from app.integrations.slack.ui import build_contact_card
from app.utils.helpers import send_slack_error, send_slack_response

async def search_contact_and_respond_to_slack(team_id: str, user_query: str, response_url: str):
    """Background task to search HubSpot and send results to Slack."""

    try:
        integration = await StorageService.get_by_slack_id(team_id)
        if not integration:
            await send_slack_error(
                response_url, "App not connected. Please install via the home page."
            )
            return

        token = integration.access_token
        refresh = integration.refresh_token
        if not token:
            await send_slack_error(
                response_url,
                "HubSpot access token not found. Please reconnect the app.",
            )
            return
        if not refresh:
            await send_slack_error(
                response_url,
                "HubSpot refresh token not found. Please reconnect the app.",
            )
            return

        hs_client = HubSpotClient(
            access_token=token, refresh_token=refresh, slack_team_id=team_id
        )
        contact = await hs_client.get_contact_by_email(user_query)

        if not contact:
            await send_slack_error(response_url, f"No contact found for '{user_query}'")
            return

        ai_insight = AIService.generate_contact_insight(contact)

        payload = build_contact_card(contact, ai_insight)
        await send_slack_response(response_url, payload)

    except Exception as e:
        print(f"Error in background task: {str(e)}")
        await send_slack_error(response_url, f"An internal error occurred: {str(e)}")
