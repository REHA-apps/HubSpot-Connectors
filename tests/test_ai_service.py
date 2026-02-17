# tests/test_ai_service.py
from app.integrations.ai_service import AIService


def test_analyze_contact_basic():
    ai = AIService()
    ai.set_corr_id("test")

    contact = {
        "properties": {
            "firstname": "Alice",
            "lastname": "Smith",
            "email": "alice@example.com",
        }
    }

    result = ai.analyze_contact(contact)

    assert result.insight
    assert result.score is not None
    assert result.summary