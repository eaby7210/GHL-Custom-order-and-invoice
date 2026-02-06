
import hmac
import hashlib
import json

def generate_signature(secret, payload):
    """
    Generates a HMAC-SHA256 signature for the given payload using the secret.
    Payload should be a dict or list (JSON serializable).
    """
    payload_str = json.dumps(payload, sort_keys=True)
    secret_bytes = bytes(secret, 'utf-8')
    payload_bytes = bytes(payload_str, 'utf-8')
    
    signature = hmac.new(secret_bytes, payload_bytes, hashlib.sha256).hexdigest()
    return signature
