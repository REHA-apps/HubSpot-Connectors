# tests/conftest.py
import uuid

import pytest

from app.domains.crm.integration_service import IntegrationService


@pytest.fixture
def corr_id():
    return f"test_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def slack_integration():
    """Legacy fixture - returning dict for compatibility if used."""
    return {
        "slack_bot_token": "xoxb-test-token",
        "default_channel": "#general",
    }


@pytest.fixture
def integration_service(corr_id):
    return IntegrationService(corr_id)
