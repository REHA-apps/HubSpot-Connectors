import httpx
import os

SLACK_BOT_TOKEN = os.getenv("SLACK_BOT_TOKEN")
SLACK_API_URL = "https://slack.com/api/chat.postMessage"

async def post_message(channel: str, text: str):
    async with httpx.AsyncClient() as client:
        await client.post(
            "https://slack.com/api/chat.postMessage",
            headers={
                "Authorization": f"Bearer {SLACK_BOT_TOKEN}"
            },
            json={
                "channel": channel,
                "text": text
            }
        )


async def post_blocks(channel: str, blocks: dict):
    """
    Sends a Slack Block Kit message.
    `blocks` must already be a valid Block Kit payload.
    """
    async with httpx.AsyncClient() as client:
        response = await client.post(
            SLACK_API_URL,
            headers={
                "Authorization": f"Bearer {SLACK_BOT_TOKEN}",
                "Content-Type": "application/json",
            },
            json={
                "channel": channel,
                **blocks
            },
        )

    data = response.json()

    if not data.get("ok"):
        raise RuntimeError(f"Slack API error: {data}")
