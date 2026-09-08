from __future__ import annotations

from typing import Any

import httpx

from jarvis.config import settings
from jarvis.google_workspace import (
    GOOGLE_WORKSPACE_SCOPES,
    GoogleWorkspaceError,
    google_workspace,
)


GOOGLE_ADS_SCOPE = "https://www.googleapis.com/auth/adwords"
if GOOGLE_ADS_SCOPE not in GOOGLE_WORKSPACE_SCOPES:
    # The Workspace OAuth screen is the single Google connection surface in JARVIS.
    # Importing this connector extends that consent with Google Ads access.
    GOOGLE_WORKSPACE_SCOPES.append(GOOGLE_ADS_SCOPE)


class GoogleAdsError(RuntimeError):
    pass


class GoogleAdsClient:
    def status(self) -> dict[str, Any]:
        scopes = google_workspace.status().get("scopes", [])
        return {
            "configured": bool(
                settings.google_ads_developer_token
                and settings.google_ads_customer_id
                and settings.google_oauth_client_id
                and settings.google_oauth_client_secret
            ),
            "customer_id": settings.google_ads_customer_id,
            "login_customer_id": settings.google_ads_login_customer_id,
            "api_version": settings.google_ads_api_version,
            "oauth_connected": google_workspace.status().get("connected", False),
            "oauth_scope_granted": GOOGLE_ADS_SCOPE in scopes,
        }

    @staticmethod
    def _clean_customer_id(value: str | None) -> str:
        if not value:
            raise GoogleAdsError("GOOGLE_ADS_CUSTOMER_ID is not configured.")
        return value.replace("-", "").strip()

    async def request(self, method: str, path: str, **kwargs) -> Any:
        if not settings.google_ads_developer_token:
            raise GoogleAdsError("GOOGLE_ADS_DEVELOPER_TOKEN is not configured.")
        try:
            token = await google_workspace.access_token()
        except GoogleWorkspaceError as exc:
            raise GoogleAdsError(str(exc)) from None
        headers = dict(kwargs.pop("headers", {}))
        headers.update(
            {
                "Authorization": f"Bearer {token}",
                "Developer-Token": settings.google_ads_developer_token,
                "Content-Type": "application/json",
            }
        )
        if settings.google_ads_login_customer_id:
            headers["login-customer-id"] = self._clean_customer_id(
                settings.google_ads_login_customer_id
            )
        version = settings.google_ads_api_version.strip("/")
        url = f"https://googleads.googleapis.com/{version}/{path.lstrip('/')}"
        async with httpx.AsyncClient(timeout=60) as client:
            response = await client.request(method, url, headers=headers, **kwargs)
        if response.status_code >= 400:
            detail = response.text[:2000]
            if response.status_code in {401, 403} and (
                "scope" in detail.lower() or "permission" in detail.lower()
            ):
                raise GoogleAdsError(
                    "Google Ads access is not authorized. Reconnect Google in JARVIS so the adwords OAuth scope is granted."
                )
            raise GoogleAdsError(f"Google Ads API HTTP {response.status_code}: {detail}")
        if not response.content:
            return {}
        return response.json()

    async def search(self, query: str) -> list[dict[str, Any]]:
        customer_id = self._clean_customer_id(settings.google_ads_customer_id)
        data = await self.request(
            "POST",
            f"customers/{customer_id}/googleAds:searchStream",
            json={"query": query},
        )
        rows: list[dict[str, Any]] = []
        batches = data if isinstance(data, list) else [data]
        for batch in batches:
            rows.extend(batch.get("results", []) if isinstance(batch, dict) else [])
        return rows

    async def performance(self, days: int = 30) -> list[dict[str, Any]]:
        days = min(max(int(days), 1), 90)
        macro = f"LAST_{days}_DAYS" if days in {7, 14, 30, 90} else "LAST_30_DAYS"
        query = f"""
            SELECT campaign.id, campaign.name, campaign.status,
                   metrics.impressions, metrics.clicks, metrics.cost_micros,
                   metrics.conversions, metrics.conversions_value
            FROM campaign
            WHERE segments.date DURING {macro}
            ORDER BY metrics.cost_micros DESC
            LIMIT 50
        """.strip()
        return await self.search(query)

    async def keywords(self, campaign_id: str, days: int = 30) -> list[dict[str, Any]]:
        campaign_id = "".join(ch for ch in str(campaign_id) if ch.isdigit())
        if not campaign_id:
            raise GoogleAdsError("A valid campaign_id is required.")
        days = min(max(int(days), 1), 90)
        macro = f"LAST_{days}_DAYS" if days in {7, 14, 30, 90} else "LAST_30_DAYS"
        query = f"""
            SELECT campaign.id, campaign.name,
                   ad_group.id, ad_group.name, ad_group.resource_name,
                   ad_group_criterion.resource_name, ad_group_criterion.status,
                   ad_group_criterion.keyword.text, ad_group_criterion.keyword.match_type,
                   metrics.impressions, metrics.clicks, metrics.cost_micros, metrics.conversions
            FROM keyword_view
            WHERE campaign.id = {campaign_id}
              AND segments.date DURING {macro}
            ORDER BY metrics.impressions DESC
            LIMIT 200
        """.strip()
        return await self.search(query)

    async def _mutate(self, service: str, operations: list[dict[str, Any]]) -> dict[str, Any]:
        customer_id = self._clean_customer_id(settings.google_ads_customer_id)
        data = await self.request(
            "POST",
            f"customers/{customer_id}/{service}:mutate",
            json={"operations": operations},
        )
        return data if isinstance(data, dict) else {"data": data}

    @staticmethod
    def _match_type(value: str) -> str:
        normalized = str(value or "PHRASE").upper()
        return normalized if normalized in {"EXACT", "PHRASE", "BROAD"} else "PHRASE"

    async def add_keywords(
        self,
        ad_group_resource: str,
        keywords: list[str],
        match_type: str = "PHRASE",
    ) -> dict[str, Any]:
        words = [str(x).strip()[:80] for x in keywords if str(x).strip()]
        if not ad_group_resource or not words:
            raise GoogleAdsError("ad_group_resource and at least one keyword are required.")
        operations = [
            {
                "create": {
                    "adGroup": ad_group_resource,
                    "status": "ENABLED",
                    "keyword": {"text": word, "matchType": self._match_type(match_type)},
                }
            }
            for word in words[:50]
        ]
        return await self._mutate("adGroupCriteria", operations)

    async def remove_keyword(self, criterion_resource: str) -> dict[str, Any]:
        if not criterion_resource:
            raise GoogleAdsError("criterion_resource is required.")
        return await self._mutate("adGroupCriteria", [{"remove": criterion_resource}])

    async def replace_keyword(
        self,
        criterion_resource: str,
        ad_group_resource: str,
        new_keyword: str,
        match_type: str = "PHRASE",
    ) -> dict[str, Any]:
        new_keyword = str(new_keyword).strip()
        if not criterion_resource or not ad_group_resource or not new_keyword:
            raise GoogleAdsError(
                "criterion_resource, ad_group_resource and new_keyword are required."
            )
        # Google Ads keyword text is effectively immutable. Replace = remove old criterion + create new.
        removed = await self.remove_keyword(criterion_resource)
        created = await self.add_keywords(ad_group_resource, [new_keyword], match_type)
        return {"removed": removed, "created": created}

    async def create_search_campaign(
        self,
        name: str,
        daily_budget_brl: float,
        final_url: str,
        headlines: list[str],
        descriptions: list[str],
        keywords: list[str],
        match_type: str = "PHRASE",
    ) -> dict[str, Any]:
        if daily_budget_brl <= 0:
            raise GoogleAdsError("daily_budget_brl must be greater than zero")
        if len(headlines) < 3 or len(descriptions) < 2 or not keywords:
            raise GoogleAdsError(
                "Search campaigns require at least 3 headlines, 2 descriptions, and 1 keyword."
            )
        amount_micros = int(round(float(daily_budget_brl) * 1_000_000))
        budget = await self._mutate(
            "campaignBudgets",
            [
                {
                    "create": {
                        "name": f"{name} - Budget",
                        "amountMicros": str(amount_micros),
                        "deliveryMethod": "STANDARD",
                        "explicitlyShared": False,
                    }
                }
            ],
        )
        budget_resource = budget.get("results", [{}])[0].get("resourceName")
        if not budget_resource:
            raise GoogleAdsError("Google Ads did not return a campaign budget resource name.")

        campaign = await self._mutate(
            "campaigns",
            [
                {
                    "create": {
                        "name": name,
                        "campaignBudget": budget_resource,
                        "advertisingChannelType": "SEARCH",
                        "status": "PAUSED",
                        "manualCpc": {},
                        "networkSettings": {
                            "targetGoogleSearch": True,
                            "targetSearchNetwork": True,
                            "targetContentNetwork": False,
                            "targetPartnerSearchNetwork": False,
                        },
                    }
                }
            ],
        )
        campaign_resource = campaign.get("results", [{}])[0].get("resourceName")
        if not campaign_resource:
            raise GoogleAdsError("Google Ads did not return a campaign resource name.")

        ad_group = await self._mutate(
            "adGroups",
            [
                {
                    "create": {
                        "name": f"{name} - Ad Group",
                        "campaign": campaign_resource,
                        "status": "ENABLED",
                        "type": "SEARCH_STANDARD",
                    }
                }
            ],
        )
        ad_group_resource = ad_group.get("results", [{}])[0].get("resourceName")
        if not ad_group_resource:
            raise GoogleAdsError("Google Ads did not return an ad group resource name.")

        await self.add_keywords(ad_group_resource, keywords, match_type)

        ad = await self._mutate(
            "adGroupAds",
            [
                {
                    "create": {
                        "adGroup": ad_group_resource,
                        "status": "ENABLED",
                        "ad": {
                            "finalUrls": [final_url],
                            "responsiveSearchAd": {
                                "headlines": [{"text": str(text)[:30]} for text in headlines[:15]],
                                "descriptions": [{"text": str(text)[:90]} for text in descriptions[:4]],
                            },
                        },
                    }
                }
            ],
        )
        return {
            "status": "PAUSED",
            "daily_budget_brl": float(daily_budget_brl),
            "budget_resource": budget_resource,
            "campaign_resource": campaign_resource,
            "ad_group_resource": ad_group_resource,
            "ad_resource": ad.get("results", [{}])[0].get("resourceName"),
        }

    async def set_campaign_status(self, campaign_resource: str, status: str) -> dict[str, Any]:
        status = status.upper()
        if status not in {"ENABLED", "PAUSED"}:
            raise GoogleAdsError("status must be ENABLED or PAUSED")
        return await self._mutate(
            "campaigns",
            [
                {
                    "updateMask": "status",
                    "update": {"resourceName": campaign_resource, "status": status},
                }
            ],
        )


google_ads = GoogleAdsClient()
