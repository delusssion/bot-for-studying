"""
YooKassa payment integration.
Set YOOKASSA_SHOP_ID and YOOKASSA_SECRET_KEY in .env to enable.
"""
import hashlib
import hmac
import json
import os
from typing import Any, Dict, Optional

import httpx

YOOKASSA_API_URL = "https://api.yookassa.ru/v3"


async def create_yookassa_payment(
    amount_kopecks: int,
    description: str,
    metadata: Dict[str, Any],
    return_url: str,
    idempotency_key: str,
) -> Optional[Dict]:
    shop_id = os.getenv("YOOKASSA_SHOP_ID")
    secret_key = os.getenv("YOOKASSA_SECRET_KEY")
    if not shop_id or not secret_key:
        raise RuntimeError("YooKassa credentials not configured")

    payload = {
        "amount": {"value": f"{amount_kopecks / 100:.2f}", "currency": "RUB"},
        "confirmation": {"type": "redirect", "return_url": return_url},
        "description": description,
        "metadata": metadata,
        "capture": True,
    }

    async with httpx.AsyncClient(timeout=30) as client:
        resp = await client.post(
            f"{YOOKASSA_API_URL}/payments",
            auth=(shop_id, secret_key),
            json=payload,
            headers={"Idempotence-Key": idempotency_key},
        )
        resp.raise_for_status()
        return resp.json()


def verify_yookassa_webhook(body: bytes, signature: str, secret: str) -> bool:
    expected = hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()
    return hmac.compare_digest(expected, signature)
