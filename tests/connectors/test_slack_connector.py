# tests/connectors/test_slack_connector.py
from unittest.mock import AsyncMock

import pytest

from app.connectors.slack_connector import SlackConnector


@pytest.mark.asyncio
async def test_send_event_success(corr_id):
    mock_client = AsyncMock()
    connector = SlackConnector(client=mock_client)

    event = {"channel": "#general", "text": "Hello", "corr_id": corr_id}

    await connector.send_event(event, corr_id=corr_id)

    mock_client.chat_postMessage.assert_awaited_once_with(
        channel="#general",
        text="Hello",
        blocks=None,
    )


@pytest.mark.asyncio
async def test_send_event_missing_channel(corr_id):
    mock_client = AsyncMock()
    connector = SlackConnector(client=mock_client)

    event = {"text": "Hello", "corr_id": corr_id}

    result = await connector.send_event(event, corr_id=corr_id)

    assert result is None
    mock_client.chat_postMessage.assert_not_called()
