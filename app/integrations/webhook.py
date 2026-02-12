import hmac, hashlib

def verify_signature(secret: str, body: bytes, signature: str):
    digest = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return digest == signature
