import pytest
from app.integrations.schemas import HubSpotContactProperties

def test_hubspot_contact_properties_aliasing(mock_contact_data):
    """Verify that lead_score_ai is correctly aliased to hs_analytics_num_visits."""
    # Use the fixture's property value
    expected_visits = int(mock_contact_data["properties"]["hs_analytics_num_visits"])
    
    # We can use the core data from fixture but rename the keys for model testing
    data = {
        "email": mock_contact_data["properties"]["email"],
        "lead_score_ai": expected_visits
    }
    props = HubSpotContactProperties(**data)
    
    # Test property access
    assert props.lead_score_ai == expected_visits
    
    # Test serialization with aliases
    dump = props.model_dump(by_alias=True)
    assert "hs_analytics_num_visits" in dump
    assert dump["hs_analytics_num_visits"] == expected_visits
    assert "lead_score_ai" not in dump

def test_hubspot_contact_properties_validation(mock_contact_data):
    """Verify email validation and defaults."""
    valid_email = mock_contact_data["properties"]["email"]
    
    with pytest.raises(Exception):
        HubSpotContactProperties(email="not-an-email")
    
    props = HubSpotContactProperties(email=valid_email)
    assert props.lifecyclestage == "subscriber"
