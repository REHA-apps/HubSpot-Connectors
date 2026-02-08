import pytest
from datetime import datetime, timezone
from typing import Dict, Any

@pytest.fixture
def mock_contact_data() -> Dict[str, Any]:
    """Provides a standard mock HubSpot contact object."""
    return {
        "id": "12345",
        "properties": {
            "email": "test@example.com",
            "firstname": "John",
            "lastname": "Doe",
            "company": "Test Corp",
            "hs_analytics_num_visits": "10",
            "lifecyclestage": "subscriber"
        }
    }

@pytest.fixture
def sample_datetime() -> datetime:
    """Provides a fixed datetime object for consistent timestamp testing."""
    return datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
