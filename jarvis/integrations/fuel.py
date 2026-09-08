from __future__ import annotations

import hashlib
import hmac
from typing import Any

import httpx

from jarvis.config import settings


class FuelAPIError(RuntimeError):
    pass


class FuelBusinessClient:
    """Connector for the Fuel/Lovable business API contract.

    The current Fuel site must expose the documented `/jarvis/*` endpoints before
    write operations can work. This connector intentionally does not guess the
    site's internal database or Supabase schema.
    """

    def status(self) -> dict[str, Any]:
        return {
            "configured": bool(settings.fuel_api_base_url and settings.fuel_api_token),
            "base_url": settings.fuel_api_base_url,
            "webhook_configured": bool(settings.fuel_webhook_secret),
        }

    async def request(self, method: str, path: str, **kwargs) -> Any:
        if not settings.fuel_api_base_url or not settings.fuel_api_token:
            raise FuelAPIError("Fuel business API is not configured.")
        headers = dict(kwargs.pop("headers", {}))
        headers["Authorization"] = f"Bearer {settings.fuel_api_token}"
        headers["Content-Type"] = "application/json"
        url = f"{settings.fuel_api_base_url.rstrip('/')}/{path.lstrip('/')}"
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.request(method, url, headers=headers, **kwargs)
        if response.status_code >= 400:
            raise FuelAPIError(f"Fuel API HTTP {response.status_code}: {response.text[:1500]}")
        if not response.content:
            return {}
        return response.json()

    async def recent_orders(self, limit: int = 20) -> list[dict[str, Any]]:
        data = await self.request("GET", "/jarvis/orders", params={"limit": min(max(limit, 1), 100)})
        if isinstance(data, list):
            return data
        return list(data.get("orders", []))

    async def create_coupon(
        self,
        code: str,
        percent_off: float,
        usage_limit: int = 1,
        customer_email: str | None = None,
        expires_at: str | None = None,
    ) -> dict[str, Any]:
        if not 0 < float(percent_off) <= 100:
            raise FuelAPIError("percent_off must be between 0 and 100")
        body: dict[str, Any] = {
            "code": code,
            "percent_off": float(percent_off),
            "usage_limit": max(int(usage_limit), 1),
        }
        if customer_email:
            body["customer_email"] = customer_email
        if expires_at:
            body["expires_at"] = expires_at
        return await self.request("POST", "/jarvis/coupons", json=body)

    async def sales_summary(self, days: int = 30) -> dict[str, Any]:
        data = await self.request(
            "GET", "/jarvis/analytics/sales", params={"days": min(max(days, 1), 365)}
        )
        return data if isinstance(data, dict) else {"data": data}

    def verify_webhook(self, body: bytes, signature_header: str | None) -> bool:
        if not settings.fuel_webhook_secret:
            return True
        if not signature_header:
            return False
        supplied = signature_header.removeprefix("sha256=")
        expected = hmac.new(
            settings.fuel_webhook_secret.encode("utf-8"), body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(supplied, expected)


fuel_business = FuelBusinessClient()
