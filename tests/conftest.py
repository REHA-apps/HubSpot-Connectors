# tests/conftest.py
import pytest
import uuid
from pydantic import SecretStr

from app.services.integration_service import IntegrationService
from app.integrations.slack_integration import SlackIntegration


@pytest.fixture
def corr_id():
    return f"test_{uuid.uuid4().hex[:8]}"


@pytest.fixture
def slack_integration():
    return SlackIntegration(
        slack_bot_token=SecretStr("xoxb-test-token"),
        default_channel="#general",
    )


@pytest.fixture
def integration_service(corr_id):
    return IntegrationService(corr_id=corr_id)