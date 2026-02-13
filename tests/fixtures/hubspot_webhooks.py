# tests/fixtures/hubspot_webhooks.py
from collections.abc import Mapping
from typing import Any

import pytest


@pytest.fixture
def hubspot_contact_webhook() -> Mapping[str, Any]:
    return {
        "objectId": "12345",
        "propertyName": "email",
        "propertyValue": "test@example.com",
        "eventId": 999,
        "subscriptionId": 111,
        "portalId": 222,
        "appId": 333,
        "occurredAt": 1700000000000,
        "subscriptionType": "contact.propertyChange",
    }


@pytest.fixture
def hubspot_deal_webhook() -> Mapping[str, Any]:
    return {
        "objectId": "98765",
        "propertyName": "dealstage",
        "propertyValue": "contractsent",
        "eventId": 888,
        "subscriptionId": 222,
        "portalId": 222,
        "appId": 333,
        "occurredAt": 1700000000000,
        "subscriptionType": "deal.propertyChange",
    }
