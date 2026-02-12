from typing import Any, Dict, Optional
from app.integrations.base_client import BaseClient


class SlackClient(BaseClient):
    """
    Slack HTTP client using BaseClient for async requests.
    """

    def __init__(self, token: str):
        self.token = token
        super().__init__(
            base_url="https://slack.com/api/",
            headers={"Authorization": f"Bearer {token}", "Content-Type": "application/json"},
        )

    # ---------------------------
    # Slack-specific API Methods
    # ---------------------------
    async def send_message(self, channel: str, text: str, blocks: Optional[list[Dict[str, Any]]] = None):
        """
        Send a message to a Slack channel.
        Supports text and optional block layout.
        """
        payload: Dict[str, Any] = {"channel": channel, "text": text}
        if blocks:
            payload["blocks"] = blocks
        return await self.post("chat.postMessage", data=payload)

    async def get_user_info(self, user_id: str) -> Dict[str, Any]:
        """Fetch Slack user info by user ID."""
        return await self.get(f"users.info?user={user_id}")

    async def list_channels(self) -> Dict[str, Any]:
        """List all channels in the workspace."""
        return await self.get("conversations.list")
