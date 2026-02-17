# tests/test_slack_connector.py
import pytest
from unittest.mock import AsyncMock

from app.connectors.slack_connector import SlackConnector
from app.core.models.channel import OutboundMessage


@pytest.mark.asyncio
async def test_slack_connector_send_message(corr_id):
    fake_client = AsyncMock()
    connector = SlackConnector(
        slack_client=fake_client,
        corr_id=corr_id,
        default_channel="C123456",
    )

    msg = OutboundMessage(
        workspace_id="test_workspace",
        channel="#general",
        text="Hello",
        blocks=None,
    )


    await connector.send_message(msg)

    fake_client.chat_postMessage.assert_awaited_once()