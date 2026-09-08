import html
import ipaddress
import re
import socket
from urllib.parse import parse_qs, unquote, urlparse

import httpx

from jarvis.config import settings
from jarvis.providers.openai import OpenAIProvider
from jarvis.schemas import RiskLevel
from jarvis.tools.base import Tool


def _assert_safe_url(url: str):
    parsed = urlparse(url)
    if parsed.scheme not in {"http", "https"} or not parsed.hostname:
        raise ValueError("Only http/https URLs are allowed")
    host = parsed.hostname.lower()
    if host in {"localhost", "127.0.0.1", "::1"} or host.endswith(".local"):
        raise ValueError("Local/private hosts are blocked")
    try:
        for info in socket.getaddrinfo(host, None):
            ip = ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise ValueError("Private network targets are blocked")
    except socket.gaierror:
        pass


def _strip_html(value: str) -> str:
    value = re.sub(r"<[^>]+>", " ", value or "")
    value = html.unescape(value)
    return re.sub(r"\s+", " ", value).strip()


def _duckduckgo_target(href: str) -> str:
    href = html.unescape(href or "")
    if href.startswith("//"):
        href = "https:" + href
    parsed = urlparse(href)
    if parsed.hostname and "duckduckgo.com" in parsed.hostname:
        target = (parse_qs(parsed.query).get("uddg") or [None])[0]
        if target:
            return unquote(target)
    return href


def _parse_duckduckgo_html(body: str, max_results: int) -> list[dict]:
    # DuckDuckGo's no-JavaScript HTML endpoint is intentionally simple. Keep the
    # parser bounded and conservative so a markup change fails closed instead of
    # inventing search results.
    anchors = list(
        re.finditer(
            r'<a[^>]*class="[^"]*result__a[^"]*"[^>]*href="([^"]+)"[^>]*>(.*?)</a>',
            body or "",
            re.I | re.S,
        )
    )
    snippets = [
        _strip_html(x)
        for x in re.findall(
            r'<(?:a|div)[^>]*class="[^"]*result__snippet[^"]*"[^>]*>(.*?)</(?:a|div)>',
            body or "",
            re.I | re.S,
        )
    ]
    results: list[dict] = []
    for idx, match in enumerate(anchors[:max_results]):
        url = _duckduckgo_target(match.group(1))
        title = _strip_html(match.group(2))
        if not title or not url.startswith(("http://", "https://")):
            continue
        results.append(
            {
                "title": title,
                "url": url,
                "snippet": snippets[idx] if idx < len(snippets) else "",
            }
        )
    return results


class WebFetchTool(Tool):
    name = "web.fetch"
    description = "Fetch public web text with SSRF protections."
    risk = RiskLevel.LOW

    async def run(self, url: str):
        _assert_safe_url(url)
        async with httpx.AsyncClient(
            timeout=20,
            follow_redirects=True,
            headers={"User-Agent": "JARVIS/0.8"},
        ) as client:
            r = await client.get(url)
            r.raise_for_status()
        ctype = r.headers.get("content-type", "")
        if "text" not in ctype and "json" not in ctype:
            raise ValueError("Only text/json resources are supported")
        return {"url": str(r.url), "status": r.status_code, "text": r.text[:30000]}


class WebSearchTool(Tool):
    name = "web.search"
    description = (
        "Search the live public web. Uses Tavily/Serper when configured, otherwise "
        "a zero-cost DuckDuckGo HTML fallback, then OpenAI hosted web search as last resort."
    )
    risk = RiskLevel.LOW

    async def _duckduckgo(self, query: str, max_results: int) -> list[dict]:
        try:
            async with httpx.AsyncClient(
                timeout=20,
                follow_redirects=True,
                headers={
                    "User-Agent": (
                        "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
                        "Chrome/128 Safari/537.36"
                    )
                },
            ) as client:
                r = await client.get(
                    "https://html.duckduckgo.com/html/",
                    params={"q": query, "kl": "br-pt"},
                )
                r.raise_for_status()
            return _parse_duckduckgo_html(r.text, max_results)
        except httpx.HTTPError:
            return []

    async def run(self, query: str, max_results: int = 5):
        max_results = max(1, min(max_results, 10))
        if settings.tavily_api_key:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    "https://api.tavily.com/search",
                    json={
                        "api_key": settings.tavily_api_key,
                        "query": query,
                        "max_results": max_results,
                        "search_depth": "basic",
                    },
                )
                r.raise_for_status()
                d = r.json()
            return {
                "provider": "tavily",
                "results": [
                    {
                        "title": x.get("title"),
                        "url": x.get("url"),
                        "snippet": x.get("content", ""),
                    }
                    for x in d.get("results", [])
                ],
            }
        if settings.serper_api_key:
            async with httpx.AsyncClient(timeout=30) as client:
                r = await client.post(
                    "https://google.serper.dev/search",
                    headers={
                        "X-API-KEY": settings.serper_api_key,
                        "Content-Type": "application/json",
                    },
                    json={"q": query, "num": max_results},
                )
                r.raise_for_status()
                d = r.json()
            return {
                "provider": "serper",
                "results": [
                    {
                        "title": x.get("title"),
                        "url": x.get("link"),
                        "snippet": x.get("snippet", ""),
                    }
                    for x in d.get("organic", [])[:max_results]
                ],
            }

        # Free testing path: this works even when an OpenAI key exists but its
        # account has no credits, which is common while the JARVIS MVP is being
        # validated on Gemini Free Tier.
        ddg_results = await self._duckduckgo(query, max_results)
        if ddg_results:
            return {"provider": "duckduckgo", "results": ddg_results}

        openai = OpenAIProvider()
        if openai.available:
            try:
                result = await openai.web_search(query)
            except Exception:
                result = {}
            citations = result.get("citations", [])[:max_results]
            rows = [
                {
                    "title": x.get("title"),
                    "url": x.get("url"),
                    "snippet": result.get("summary", ""),
                }
                for x in citations
            ]
            if not rows and result.get("summary"):
                rows = [
                    {
                        "title": "OpenAI web search synthesis",
                        "url": None,
                        "snippet": result.get("summary", ""),
                    }
                ]
            if rows:
                return {
                    "provider": "openai",
                    "results": rows,
                    "summary": result.get("summary", ""),
                }

        return {
            "provider": None,
            "results": [],
            "warning": "No live search provider returned results.",
        }
