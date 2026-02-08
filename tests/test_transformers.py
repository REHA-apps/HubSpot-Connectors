import pytest
from datetime import datetime, timezone
from app.utils.transformers import to_hubspot_timestamp, from_hubspot_timestamp, flatten_properties

def test_to_hubspot_timestamp(sample_datetime):
    """Verify conversion from datetime to HubSpot millisecond timestamp."""
    # sample_datetime is 2024-01-01 12:00:00 UTC
    expected_ms = 1704110400000
    assert to_hubspot_timestamp(sample_datetime) == expected_ms

def test_from_hubspot_timestamp():
    """Verify conversion from HubSpot millisecond timestamp to datetime."""
    ms = 1704110400000
    expected_dt = datetime(2024, 1, 1, 12, 0, 0, tzinfo=timezone.utc)
    assert from_hubspot_timestamp(ms) == expected_dt

def test_flatten_properties_success(mock_contact_data):
    """Verify that properties are successfully flattened into the core object."""
    flattened = flatten_properties(mock_contact_data)
    assert flattened["id"] == mock_contact_data["id"]
    assert flattened["email"] == mock_contact_data["properties"]["email"]
    assert flattened["firstname"] == mock_contact_data["properties"]["firstname"]

def test_flatten_properties_missing_properties():
    """Verify behavior when the 'properties' key is missing."""
    hubspot_obj = {"id": "123"}
    flattened = flatten_properties(hubspot_obj)
    assert flattened == hubspot_obj

def test_flatten_properties_non_dict_properties():
    """Verify behavior when 'properties' is not a dictionary."""
    hubspot_obj = {"id": "123", "properties": "not-a-dict"}
    flattened = flatten_properties(hubspot_obj)
    assert flattened == hubspot_obj
