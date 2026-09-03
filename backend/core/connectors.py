import os
import hmac
import hashlib
import time
import uuid
import httpx
import json
from typing import Dict, Any

async def dispatch_webhook(payload: Dict[str, Any], url: str = None) -> None:
    """
    Dispatch a webhook with HMAC-SHA256 signature.
    """
    webhook_url = url or os.getenv("WEBHOOK_URL", "https://example.com/webhook")
    webhook_secret = os.getenv("WEBHOOK_SECRET", "dummy_secret").encode("utf-8")
    
    timestamp = str(int(time.time()))
    idempotency_key = str(uuid.uuid4())
    
    body = json.dumps(payload)
    
    signature = hmac.new(webhook_secret, body.encode("utf-8"), hashlib.sha256).hexdigest()
    
    headers = {
        "Content-Type": "application/json",
        "X-DocFlow-Signature": signature,
        "X-Timestamp": timestamp,
        "X-Idempotency-Key": idempotency_key,
    }
    
    async with httpx.AsyncClient() as client:
        try:
            await client.post(webhook_url, content=body, headers=headers)
        except Exception as e:
            print(f"Webhook dispatch failed: {e}")
