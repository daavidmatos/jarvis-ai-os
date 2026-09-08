from __future__ import annotations

import hashlib
import hmac
from typing import Any

import httpx

from jarvis.config import settings


class MetaError(RuntimeError):
    pass


class MetaInstagramClient:
    @property
    def base(self) -> str:
        version = settings.meta_graph_version.strip("/")
        return f"https://graph.facebook.com/{version}"

    def status(self) -> dict[str, Any]:
        return {
            "configured": bool(settings.meta_access_token and settings.meta_instagram_user_id),
            "instagram_user_id": settings.meta_instagram_user_id,
            "graph_version": settings.meta_graph_version,
            "webhook_configured": bool(settings.meta_webhook_verify_token),
            "signature_verification": bool(settings.meta_app_secret),
        }

    async def request(self, method: str, path: str, **kwargs) -> dict[str, Any]:
        if not settings.meta_access_token:
            raise MetaError("META_ACCESS_TOKEN is not configured.")
        headers = dict(kwargs.pop("headers", {}))
        params = dict(kwargs.pop("params", {}))
        params["access_token"] = settings.meta_access_token
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.request(
                method,
                f"{self.base}/{path.lstrip('/')}",
                headers=headers,
                params=params,
                **kwargs,
            )
        if response.status_code >= 400:
            raise MetaError(f"Meta Graph API HTTP {response.status_code}: {response.text[:1500]}")
        return response.json() if response.content else {}

    async def profile(self) -> dict[str, Any]:
        user_id = settings.meta_instagram_user_id
        if not user_id:
            raise MetaError("META_INSTAGRAM_USER_ID is not configured.")
        return await self.request(
            "GET",
            user_id,
            params={"fields": "id,username,name,profile_picture_url,followers_count,media_count"},
        )

    async def tagged_media(self, limit: int = 25) -> list[dict[str, Any]]:
        user_id = settings.meta_instagram_user_id
        if not user_id:
            raise MetaError("META_INSTAGRAM_USER_ID is not configured.")
        result = await self.request(
            "GET",
            f"{user_id}/tags",
            params={
                "fields": "id,caption,media_type,media_url,permalink,timestamp,username",
                "limit": min(max(int(limit), 1), 50),
            },
        )
        return result.get("data", [])

    async def publish_photo(self, image_url: str, caption: str) -> dict[str, Any]:
        user_id = settings.meta_instagram_user_id
        if not user_id:
            raise MetaError("META_INSTAGRAM_USER_ID is not configured.")
        if not image_url.startswith("https://"):
            raise MetaError("Instagram publishing requires a publicly accessible HTTPS image URL.")
        container = await self.request(
            "POST",
            f"{user_id}/media",
            data={"image_url": image_url, "caption": caption},
        )
        creation_id = container.get("id")
        if not creation_id:
            raise MetaError("Meta did not return a media container ID.")
        published = await self.request(
            "POST",
            f"{user_id}/media_publish",
            data={"creation_id": creation_id},
        )
        return {
            "container_id": creation_id,
            "media_id": published.get("id"),
            "status": "published",
        }

    def verify_signature(self, body: bytes, signature_header: str | None) -> bool:
        if not settings.meta_app_secret:
            return True
        if not signature_header or not signature_header.startswith("sha256="):
            return False
        supplied = signature_header.split("=", 1)[1]
        expected = hmac.new(
            settings.meta_app_secret.encode("utf-8"), body, hashlib.sha256
        ).hexdigest()
        return hmac.compare_digest(supplied, expected)


instagram = MetaInstagramClient()
