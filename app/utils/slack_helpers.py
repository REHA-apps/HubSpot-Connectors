import httpx
from app.utils.helpers import send_slack_response

async def send_delayed_slack_response(response_url: str, payload: dict):
    """Sends a delayed response to Slack using the response_url."""
    async with httpx.AsyncClient() as client:
        await client.post(response_url, json=payload)

