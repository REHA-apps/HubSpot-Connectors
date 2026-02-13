# tests/clients/test_hubspot_client.py
from unittest.mock import AsyncMock

import pytest

from app.clients.hubspot_client import HubSpotClient


@pytest.mark.asyncio
async def test_create_task_success(corr_id):
    mock_http = AsyncMock()
    mock_http.post.return_value.json.return_value = {"id": "task123"}

    client = HubSpotClient(access_token="fake", http_client=mock_http)

    result = await client.create_task({"hs_task_subject": "Call John"}, corr_id=corr_id)

    assert result == {"id": "task123"}
    mock_http.post.assert_awaited_once()


@pytest.mark.asyncio
async def test_create_task_failure(corr_id):
    mock_http = AsyncMock()
    mock_http.post.side_effect = Exception("Boom")

    client = HubSpotClient(access_token="fake", http_client=mock_http)

    with pytest.raises(Exception):
        await client.create_task({"hs_task_subject": "Call John"}, corr_id=corr_id)
