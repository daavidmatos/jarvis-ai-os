from __future__ import annotations

import asyncio
from typing import Any
from urllib.parse import quote_plus

import httpx

from jarvis.config import settings


class BrowserlessAgentError(RuntimeError):
    pass


class BrowserlessAgentClient:
    TERMINAL = {"succeeded", "failed", "timed_out", "stopped"}

    def status(self) -> dict[str, Any]:
        return {
            "configured": bool(settings.browserless_api_token),
            "provider": "browserless_agent",
            "base_url": settings.browserless_base_url,
            "ifood_profile": bool(settings.browserless_ifood_profile),
        }

    async def run(
        self,
        query: str,
        *,
        start_url: str | None = None,
        allowed_domains: list[str] | None = None,
        profile: str | None = None,
        max_steps: int | None = None,
        timeout_ms: int | None = None,
        response_schema: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        token = settings.browserless_api_token
        if not token:
            raise BrowserlessAgentError("Browserless ainda não está conectado ao JARVIS.")

        base = settings.browserless_base_url.rstrip("/")
        timeout_ms = min(max(int(timeout_ms or settings.browserless_default_timeout_ms), 10000), 120000)
        max_steps = min(max(int(max_steps or settings.browserless_max_steps), 1), 60)
        body: dict[str, Any] = {
            "query": query.strip(),
            "timeout": timeout_ms,
            "maxSteps": max_steps,
        }
        if start_url:
            body["startUrl"] = start_url
        if allowed_domains:
            body["allowedDomains"] = allowed_domains
        if profile:
            body["profile"] = profile
        if response_schema:
            body["responseSchema"] = response_schema

        try:
            async with httpx.AsyncClient(timeout=max(timeout_ms / 1000 + 15, 30)) as client:
                start = await client.post(
                    f"{base}/agent/run",
                    params={"token": token},
                    headers={"Content-Type": "application/json"},
                    json=body,
                )
                if start.status_code >= 400:
                    raise BrowserlessAgentError(
                        f"Browserless HTTP {start.status_code}: {start.text[:500]}"
                    )
                run = start.json()
                run_id = run.get("id")
                if not run_id:
                    raise BrowserlessAgentError("Browserless não retornou um run id.")

                deadline = asyncio.get_running_loop().time() + timeout_ms / 1000 + 8
                last: dict[str, Any] = run
                while asyncio.get_running_loop().time() < deadline:
                    await asyncio.sleep(1.0)
                    response = await client.get(
                        f"{base}/agent/run/{run_id}",
                        params={"token": token},
                    )
                    if response.status_code >= 400:
                        raise BrowserlessAgentError(
                            f"Browserless poll HTTP {response.status_code}: {response.text[:500]}"
                        )
                    last = response.json()
                    if last.get("status") in self.TERMINAL:
                        break
                status = str(last.get("status") or "unknown")
                if status != "succeeded":
                    raise BrowserlessAgentError(
                        str(last.get("error") or f"Browserless terminou com status {status}.")
                    )
                return last
        except httpx.HTTPError as exc:
            raise BrowserlessAgentError(f"Falha de rede no Browserless: {exc}") from None

    async def web_search(self, query: str, max_results: int = 5) -> list[dict[str, Any]]:
        max_results = min(max(int(max_results), 1), 8)
        schema = {
            "type": "object",
            "properties": {
                "results": {
                    "type": "array",
                    "items": {
                        "type": "object",
                        "properties": {
                            "title": {"type": "string"},
                            "url": {"type": "string"},
                            "snippet": {"type": "string"},
                        },
                        "required": ["title", "url", "snippet"],
                    },
                }
            },
            "required": ["results"],
        }
        run = await self.run(
            (
                f"Search Google for: {query}. Return the best {max_results} organic results. "
                "Do not invent URLs. Read the actual search results page and return title, URL and a short snippet."
            ),
            start_url=f"https://www.google.com/search?q={quote_plus(query)}&hl=pt-BR",
            allowed_domains=["google.com", "www.google.com"],
            max_steps=10,
            timeout_ms=60000,
            response_schema=schema,
        )
        data = run.get("data") or {}
        rows = data.get("results") or []
        return [x for x in rows if isinstance(x, dict) and x.get("url")][:max_results]


browserless_agent = BrowserlessAgentClient()
