from __future__ import annotations

import base64
from pathlib import Path
from uuid import uuid4

import httpx

from jarvis.config import settings
from jarvis.credentials import credential_store
from jarvis.integrations.fuel import fuel_business
from jarvis.integrations.google_ads import google_ads
from jarvis.integrations.meta import instagram
from jarvis.schemas import RiskLevel
from jarvis.tools.base import Tool


class InstagramStatusTool(Tool):
    name = "instagram.status"
    description = "Check whether the Instagram/Meta connector is configured and read the connected profile."
    risk = RiskLevel.LOW

    async def run(self):
        status = instagram.status()
        if status["configured"]:
            try:
                status["profile"] = await instagram.profile()
            except Exception as exc:
                status["profile_error"] = str(exc)
        return status


class InstagramTaggedMediaTool(Tool):
    name = "instagram.tagged_media"
    description = "List recent Instagram media where the connected business account was tagged. Read-only."
    risk = RiskLevel.LOW

    async def run(self, limit: int = 25):
        return {"media": await instagram.tagged_media(limit)}


class InstagramPublishPhotoTool(Tool):
    name = "instagram.publish_photo"
    description = "Publish a photo and caption to the connected Instagram business account."
    risk = RiskLevel.HIGH
    requires_approval = True
    mission_permission = "publish"

    async def run(self, image_url: str, caption: str):
        return await instagram.publish_photo(image_url, caption)


class GoogleAdsStatusTool(Tool):
    name = "google_ads.status"
    description = "Check Google Ads API configuration and OAuth readiness."
    risk = RiskLevel.LOW

    async def run(self):
        return google_ads.status()


class GoogleAdsPerformanceTool(Tool):
    name = "google_ads.performance"
    description = "Read Google Ads campaign performance metrics. Read-only."
    risk = RiskLevel.LOW

    async def run(self, days: int = 30):
        return {"rows": await google_ads.performance(days)}


class GoogleAdsKeywordsTool(Tool):
    name = "google_ads.keywords"
    description = "Read keywords and keyword performance for one Google Ads campaign. Read-only."
    risk = RiskLevel.LOW

    async def run(self, campaign_id: str, days: int = 30):
        return {"rows": await google_ads.keywords(campaign_id, days)}


class GoogleAdsAddKeywordsTool(Tool):
    name = "google_ads.add_keywords"
    description = "Add explicitly requested keywords to a Google Ads ad group. This can change paid traffic and spend."
    risk = RiskLevel.HIGH
    requires_approval = True
    mission_permission = "spend"

    async def run(
        self,
        ad_group_resource: str,
        keywords: list[str],
        match_type: str = "PHRASE",
    ):
        return await google_ads.add_keywords(ad_group_resource, keywords, match_type)


class GoogleAdsRemoveKeywordTool(Tool):
    name = "google_ads.remove_keyword"
    description = "Remove one explicitly requested Google Ads keyword criterion."
    risk = RiskLevel.HIGH
    requires_approval = True
    mission_permission = "spend"

    async def run(self, criterion_resource: str):
        return await google_ads.remove_keyword(criterion_resource)


class GoogleAdsReplaceKeywordTool(Tool):
    name = "google_ads.replace_keyword"
    description = "Replace one explicitly requested Google Ads keyword with another."
    risk = RiskLevel.HIGH
    requires_approval = True
    mission_permission = "spend"

    async def run(
        self,
        criterion_resource: str,
        ad_group_resource: str,
        new_keyword: str,
        match_type: str = "PHRASE",
    ):
        return await google_ads.replace_keyword(
            criterion_resource,
            ad_group_resource,
            new_keyword,
            match_type,
        )


class GoogleAdsCreateSearchCampaignTool(Tool):
    name = "google_ads.create_search_campaign"
    description = "Create a complete Search campaign in PAUSED state with budget, ad group, keywords and responsive search ad."
    risk = RiskLevel.HIGH
    requires_approval = True
    mission_permission = "spend"
    spend_arg = "daily_budget_brl"

    async def run(
        self,
        name: str,
        daily_budget_brl: float,
        final_url: str,
        headlines: list[str],
        descriptions: list[str],
        keywords: list[str],
        match_type: str = "PHRASE",
    ):
        return await google_ads.create_search_campaign(
            name=name,
            daily_budget_brl=daily_budget_brl,
            final_url=final_url,
            headlines=headlines,
            descriptions=descriptions,
            keywords=keywords,
            match_type=match_type,
        )


class GoogleAdsSetCampaignStatusTool(Tool):
    name = "google_ads.set_campaign_status"
    description = "Enable or pause an existing Google Ads campaign. Enabling may spend money."
    risk = RiskLevel.HIGH
    requires_approval = True
    mission_permission = "spend"
    spend_arg = "expected_daily_budget_brl"

    async def run(
        self,
        campaign_resource: str,
        status: str,
        expected_daily_budget_brl: float,
    ):
        return await google_ads.set_campaign_status(campaign_resource, status)


class CreativeImageGenerateTool(Tool):
    name = "creative.generate_image"
    description = "Generate a campaign image with the configured OpenAI image model and save it as a JARVIS artifact."
    risk = RiskLevel.MEDIUM

    async def run(
        self,
        prompt: str,
        size: str = "1024x1024",
        quality: str = "high",
    ):
        api_key = credential_store.get("openai")
        if not api_key:
            raise RuntimeError("OpenAI is not configured.")
        async with httpx.AsyncClient(timeout=180) as client:
            response = await client.post(
                "https://api.openai.com/v1/images/generations",
                headers={
                    "Authorization": f"Bearer {api_key}",
                    "Content-Type": "application/json",
                },
                json={
                    "model": settings.openai_image_model,
                    "prompt": prompt,
                    "size": size,
                    "quality": quality,
                },
            )
        if response.status_code >= 400:
            raise RuntimeError(
                f"OpenAI image generation failed with HTTP {response.status_code}: {response.text[:1200]}"
            )
        data = response.json().get("data", [])
        if not data:
            raise RuntimeError("OpenAI image generation returned no image data.")
        item = data[0]
        folder = settings.workspace_path / "generated"
        folder.mkdir(parents=True, exist_ok=True)
        filename = f"{uuid4().hex}.png"
        path = folder / filename
        if item.get("b64_json"):
            path.write_bytes(base64.b64decode(item["b64_json"]))
        elif item.get("url"):
            async with httpx.AsyncClient(timeout=90) as client:
                image = await client.get(item["url"])
                image.raise_for_status()
                path.write_bytes(image.content)
        else:
            raise RuntimeError("OpenAI image response had neither b64_json nor url.")
        public_url = None
        if settings.public_base_url.startswith("https://"):
            public_url = f"{settings.public_base_url.rstrip('/')}/v1/assets/{filename}"
        return {
            "artifact_path": str(path),
            "filename": filename,
            "public_url": public_url,
            "model": settings.openai_image_model,
        }


class FuelStatusTool(Tool):
    name = "fuel.status"
    description = "Check whether the Fuel business API connector is configured."
    risk = RiskLevel.LOW

    async def run(self):
        return fuel_business.status()


class FuelRecentOrdersTool(Tool):
    name = "fuel.recent_orders"
    description = "Read recent Fuel orders from the business API. Read-only."
    risk = RiskLevel.LOW

    async def run(self, limit: int = 20):
        return {"orders": await fuel_business.recent_orders(limit)}


class FuelSalesSummaryTool(Tool):
    name = "fuel.sales_summary"
    description = "Read Fuel sales analytics for a time window. Read-only."
    risk = RiskLevel.LOW

    async def run(self, days: int = 30):
        return await fuel_business.sales_summary(days)


class FuelCreateCouponTool(Tool):
    name = "fuel.create_coupon"
    description = "Create a customer discount coupon through the Fuel business API."
    risk = RiskLevel.HIGH
    requires_approval = True
    mission_permission = "commerce"

    async def run(
        self,
        code: str,
        percent_off: float,
        usage_limit: int = 1,
        customer_email: str | None = None,
        expires_at: str | None = None,
    ):
        return await fuel_business.create_coupon(
            code=code,
            percent_off=percent_off,
            usage_limit=usage_limit,
            customer_email=customer_email,
            expires_at=expires_at,
        )
