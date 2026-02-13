from collections.abc import Mapping
from datetime import UTC, datetime
from typing import Any

import pytest


@pytest.fixture
def corr_id() -> str:
    """Provides a stable correlation ID for tests."""
    return "test_evt_123456"


@pytest.fixture
def mock_contact_data() -> Mapping[str, Any]:
    """Provides a standard mock HubSpot contact object."""
    return {
        "id": "12345",
        "properties": {
            "email": "test@example.com",
            "firstname": "John",
            "lastname": "Doe",
            "company": "Test Corp",
            "hs_analytics_num_visits": "10",
            "lifecyclestage": "subscriber",
        },
    }


@pytest.fixture
def minimal_contact_data() -> Mapping[str, Any]:
    """Provides a minimal HubSpot contact for edge-case testing."""
    return {
        "id": "999",
        "properties": {
            "email": None,
            "firstname": None,
            "lastname": None,
        },
    }


@pytest.fixture
def sample_datetime() -> datetime:
    """Provides a fixed datetime object for consistent timestamp testing."""
    return datetime(2024, 1, 1, 12, 0, 0, tzinfo=UTC)
