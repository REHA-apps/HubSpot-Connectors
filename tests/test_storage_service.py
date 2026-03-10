# tests/test_storage_service.py
"""Tests for StorageService: caching, invalidation, cross-cache pre-population."""

from unittest.mock import AsyncMock, MagicMock

import pytest
import pytest_asyncio

from app.db.records import IntegrationRecord, Provider
from app.db.storage_service import StorageService


def _make_integration(
    workspace_id: str = "ws-1",
    provider: Provider = Provider.SLACK,
    **kwargs,
) -> IntegrationRecord:
    return IntegrationRecord(
        id=kwargs.get("id", "integ-1"),
        workspace_id=workspace_id,
        provider=provider,
        credentials=kwargs.get("credentials", {"slack_bot_token": "xoxb-test"}),
        metadata=kwargs.get("metadata", {"slack_team_id": "T123"}),
    )


@pytest.fixture
def storage():
    """StorageService with mocked Supabase repos."""
    svc = StorageService.__new__(StorageService)

    svc.client = MagicMock()
    svc.integrations = MagicMock()
    svc.workspaces = MagicMock()
    return svc


@pytest_asyncio.fixture(autouse=True)
async def clear_caches():
    """Clear module-level caches between tests."""
    from app.db import storage_service as mod  # noqa: PLC0415

    await mod._record_cache.clear()
    await mod._slack_mapping_cache.clear()
    await mod._hubspot_mapping_cache.clear()
    yield
    await mod._record_cache.clear()
    await mod._slack_mapping_cache.clear()
    await mod._hubspot_mapping_cache.clear()


# --- get_integration caching ---


@pytest.mark.asyncio
async def test_get_integration_caches_result(storage):
    """Second call should return cached result, not hit DB again."""
    record = _make_integration()
    storage.integrations.fetch_single = AsyncMock(return_value=record)

    r1 = await storage.get_integration("ws-1", Provider.SLACK)
    r2 = await storage.get_integration("ws-1", Provider.SLACK)

    assert r1 is record
    assert r2 is record
    storage.integrations.fetch_single.assert_awaited_once()


@pytest.mark.asyncio
async def test_upsert_invalidates_cache(storage):
    """Upsert should invalidate the record cache so next get refetches."""
    record = _make_integration()
    storage.integrations.fetch_single = AsyncMock(return_value=record)
    storage.integrations.upsert = AsyncMock(return_value=record)

    # Populate cache
    await storage.get_integration("ws-1", Provider.SLACK)
    assert storage.integrations.fetch_single.await_count == 1

    # Upsert invalidates cache
    await storage.upsert_integration(
        {
            "id": "integ-1",
            "workspace_id": "ws-1",
            "provider": Provider.SLACK,
            "credentials": {},
            "metadata": {"slack_team_id": "T123"},
        }
    )

    # Next get should hit DB again
    await storage.get_integration("ws-1", Provider.SLACK)
    EXPECTED_FETCH_CALLS = 2
    assert storage.integrations.fetch_single.await_count == EXPECTED_FETCH_CALLS


# --- Slack team ID lookup + cross-cache population ---


@pytest.mark.asyncio
async def test_get_by_slack_team_id_populates_both_caches(storage):
    """get_integration_by_slack_team_id should pre-populate the record cache."""
    record = _make_integration()
    storage.integrations.fetch_single = AsyncMock(return_value=record)

    # First call — fetches directly
    r1 = await storage.get_integration_by_slack_team_id("T123")
    assert r1 is record

    # Second call via get_integration should use record cache, not DB
    r2 = await storage.get_integration("ws-1", Provider.SLACK)
    assert r2 is record
    # fetch_single called only once (by slack_team_id lookup)
    storage.integrations.fetch_single.assert_awaited_once()


# --- Portal ID lookup ---


@pytest.mark.asyncio
async def test_get_by_portal_id(storage):
    record = _make_integration(
        provider=Provider.HUBSPOT, metadata={"portal_id": "P456"}
    )
    storage.integrations.fetch_single = AsyncMock(return_value=record)

    result = await storage.get_integration_by_portal_id("P456")
    assert result is record
    assert result.provider == Provider.HUBSPOT


# --- Delete invalidation ---


@pytest.mark.asyncio
async def test_delete_invalidates_cache(storage):
    record = _make_integration()
    storage.integrations.fetch_single = AsyncMock(return_value=record)
    storage.integrations.delete = AsyncMock(return_value=1)

    # Populate cache
    await storage.get_integration("ws-1", Provider.SLACK)
    assert storage.integrations.fetch_single.await_count == 1

    # Delete invalidates
    await storage.delete_integration("ws-1", Provider.SLACK)

    # Next get refetches
    await storage.get_integration("ws-1", Provider.SLACK)
    EXPECTED_FETCH_CALLS = 2
    assert storage.integrations.fetch_single.await_count == EXPECTED_FETCH_CALLS


@pytest.mark.asyncio
async def test_upsert_invalidates_mapping_caches(storage):
    """Upserting an integration with a Slack team ID should invalidate the
    mapping cache.
    """
    record = _make_integration()
    storage.integrations.fetch_single = AsyncMock(return_value=record)
    storage.integrations.upsert = AsyncMock(return_value=record)

    # Populate both caches
    await storage.get_integration_by_slack_team_id("T123")

    from app.db.storage_service import _slack_mapping_cache  # noqa: PLC0415

    assert await _slack_mapping_cache.get("T123") == "ws-1"

    # Upsert with same mapping
    await storage.upsert_integration(
        {
            "workspace_id": "ws-1",
            "provider": Provider.SLACK,
            "metadata": {"slack_team_id": "T123"},
        }
    )

    # Mapping cache should be invalidated (None or must be refetched)
    assert await _slack_mapping_cache.get("T123") is None


@pytest.mark.asyncio
async def test_mapping_miss_self_healing(storage):
    """If mapping exists but record is missing in DB, mapping should be purged."""
    from app.db.storage_service import _slack_mapping_cache  # noqa: PLC0415

    # Manually seed a stale mapping
    await _slack_mapping_cache.set("T-stale", "ws-stale")

    # Storage.get_integration will return None (mocked)
    storage.integrations.fetch_single = AsyncMock(return_value=None)

    # Try resolver
    result = await storage.get_integration_by_slack_team_id("T-stale")

    assert result is None
    # Slack mapping for 'T-stale' should have been invalidated
    assert await _slack_mapping_cache.get("T-stale") is None
