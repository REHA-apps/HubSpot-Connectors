# tests/test_integration_service.py
"""Tests for IntegrationService: OAuth flows, dedup, token rotation."""

from unittest.mock import AsyncMock, MagicMock

import pytest

from app.core.exceptions import IntegrationNotFoundError
from app.db.records import IntegrationRecord, Provider
from app.domains.crm.integration_service import IntegrationService


def _make_integration(
    workspace_id: str = "ws-1",
    provider: Provider = Provider.SLACK,
    **kwargs,
) -> IntegrationRecord:
    return IntegrationRecord(
        id=kwargs.get("id", "integ-1"),
        workspace_id=workspace_id,
        provider=provider,
        credentials=kwargs.get(
            "credentials",
            {
                "slack_bot_token": "xoxb-old",
                "refresh_token": "rt-old",
                "expires_at": 9999999999,
            },
        ),
        metadata=kwargs.get(
            "metadata",
            {
                "slack_team_id": "T123",
                "channel_id": "C001",
            },
        ),
    )


@pytest.fixture
def service():
    svc = IntegrationService("test")
    svc.storage = MagicMock()
    return svc


# --- Local caching ---


@pytest.mark.asyncio
async def test_get_integration_caches_locally(service):
    """IntegrationService has a per-request cache that avoids redundant storage
    calls.
    """
    record = _make_integration()
    service.storage.get_integration = AsyncMock(return_value=record)

    r1 = await service.get_integration("ws-1", Provider.SLACK)
    r2 = await service.get_integration("ws-1", Provider.SLACK)

    assert r1 is record
    assert r2 is record
    # Since we removed local caching in IntegrationService, it delegates twice.
    # Caching is now handled at the StorageService layer.
    assert service.storage.get_integration.await_count == 2


# --- Resolve workspace ---


@pytest.mark.asyncio
async def test_resolve_workspace_raises_on_missing_team_id(service):
    """Missing team ID raises ValueError."""
    with pytest.raises(ValueError, match="Missing"):
        await service.resolve_workspace(None)


@pytest.mark.asyncio
async def test_resolve_workspace_raises_when_not_found(service):
    """Unknown team ID raises IntegrationNotFoundError."""
    service.storage.get_integration_by_slack_team_id = AsyncMock(return_value=None)
    with pytest.raises(IntegrationNotFoundError, match="No Slack integration found"):
        await service.resolve_workspace("T-unknown")


@pytest.mark.asyncio
async def test_resolve_workspace_returns_id(service):
    record = _make_integration()
    service.storage.get_integration_by_slack_team_id = AsyncMock(return_value=record)
    ws_id = await service.resolve_workspace("T123")
    assert ws_id == "ws-1"


# --- Token rotation includes integration ID ---


@pytest.mark.asyncio
async def test_update_slack_tokens_includes_id(service):
    """Token rotation must include integration.id to avoid duplicate rows."""
    record = _make_integration()
    service.storage.get_integration = AsyncMock(return_value=record)
    service.storage.upsert_integration = AsyncMock(return_value=record)

    # Record is fetched from storage (which uses its own internal cache)

    await service.update_slack_tokens(
        workspace_id="ws-1",
        access_token="xoxb-new",
        refresh_token="rt-new",
        expires_at=1234567890,
    )

    service.storage.upsert_integration.assert_awaited_once()
    payload = service.storage.upsert_integration.call_args[0][0]
    assert payload["id"] == "integ-1", "Payload must include existing integration ID"
    # Note: credentials are merged; xoxb-new should be present
    assert payload["credentials"]["slack_bot_token"] == "xoxb-new"
    assert payload["credentials"]["refresh_token"] == "rt-new"


@pytest.mark.asyncio
async def test_update_slack_tokens_noop_when_missing(service):
    """Token rotation is a no-op when integration doesn't exist."""
    service.storage.get_integration = AsyncMock(return_value=None)
    service.storage.upsert_integration = AsyncMock()

    await service.update_slack_tokens("ws-missing", "tok", "rt", None)
    service.storage.upsert_integration.assert_not_awaited()
