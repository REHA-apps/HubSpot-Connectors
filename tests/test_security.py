import hmac
import hashlib
import base64
from app.core.security import verify_hubspot_signature, from app.core.config import settings

def test_verify_hubspot_signature(monkeypatch):
    """Verify HubSpot signature validation."""
    secret = "test_secret"
    monkeypatch.setattr(settings, "HUBSPOT_CLIENT_SECRET", secret)
    
    url = "https://example.com/webhook"
    body = b'{"event": "test"}'
    
    # Calculate expected signature
    digest = hmac.new(
        secret.encode(),
        msg=(url + body.decode()).encode(),
        digestmod=hashlib.sha256
    ).digest()
    signature = base64.b64encode(digest).decode()
    
    assert verify_hubspot_signature(signature, body, url) is True
    assert verify_hubspot_signature("wrong", body, url) is False
