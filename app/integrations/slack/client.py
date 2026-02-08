import httpx
from typing import Dict, Any
from app.core.config import settings
from app.utils.helpers import HTTPClient

async def post_message(channel: str, text: str):
    """Posts a simple text message to a Slack channel.
    
    Args:
        channel: The channel ID or name (e.g., "#general").
        text: The message text to post.
    """
    client = HTTPClient.get_client()
    response = await client.post(
        "https://slack.com/api/chat.postMessage",
        headers={
            "Authorization": f"Bearer {settings.SLACK_BOT_TOKEN}"
        },
        json={
            "channel": channel,
            "text": text
        }
    )
    response.raise_for_status()

async def post_blocks(channel: str, blocks: Dict[str, Any]):
    """Sends a Slack Block Kit message.
    
    Args:
        channel: The channel ID or name.
        blocks: A valid Slack Block Kit payload.
        
    Raises:
        RuntimeError: If the Slack API returns an error.
    """
    client = HTTPClient.get_client()
    response = await client.post(
        "https://slack.com/api/chat.postMessage",
        headers={
            "Authorization": f"Bearer {settings.SLACK_BOT_TOKEN}",
            "Content-Type": "application/json",
        },
        json={
            "channel": channel,
            **blocks
        },
    )
    response.raise_for_status()
    data = response.json()

    if not data.get("ok"):
        raise RuntimeError(f"Slack API error: {data.get('error')}")
