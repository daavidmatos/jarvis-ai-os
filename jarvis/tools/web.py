import ipaddress, socket
from urllib.parse import urlparse
import httpx
from jarvis.config import settings
from jarvis.schemas import RiskLevel
from jarvis.tools.base import Tool

def _assert_safe_url(url: str):
    parsed=urlparse(url)
    if parsed.scheme not in {"http","https"} or not parsed.hostname:
        raise ValueError("Only http/https URLs are allowed")
    host=parsed.hostname.lower()
    if host in {"localhost","127.0.0.1","::1"} or host.endswith(".local"):
        raise ValueError("Local/private hosts are blocked")
    try:
        for info in socket.getaddrinfo(host,None):
            ip=ipaddress.ip_address(info[4][0])
            if ip.is_private or ip.is_loopback or ip.is_link_local or ip.is_reserved:
                raise ValueError("Private network targets are blocked")
    except socket.gaierror:
        pass

class WebFetchTool(Tool):
    name="web.fetch"; description="Fetch public web text with SSRF protections."; risk=RiskLevel.LOW
    async def run(self, url: str):
        _assert_safe_url(url)
        async with httpx.AsyncClient(timeout=20,follow_redirects=True,headers={"User-Agent":"JARVIS/0.2"}) as client:
            r=await client.get(url); r.raise_for_status()
        ctype=r.headers.get("content-type","")
        if "text" not in ctype and "json" not in ctype:
            raise ValueError("Only text/json resources are supported")
        return {"url":str(r.url),"status":r.status_code,"text":r.text[:30000]}

class WebSearchTool(Tool):
    name="web.search"; description="Search the web using Tavily or Serper when configured."; risk=RiskLevel.LOW
    async def run(self, query: str, max_results: int=5):
        max_results=max(1,min(max_results,10))
        if settings.tavily_api_key:
            async with httpx.AsyncClient(timeout=30) as client:
                r=await client.post("https://api.tavily.com/search",json={"api_key":settings.tavily_api_key,"query":query,"max_results":max_results,"search_depth":"basic"}); r.raise_for_status(); d=r.json()
            return {"provider":"tavily","results":[{"title":x.get("title"),"url":x.get("url"),"snippet":x.get("content","")} for x in d.get("results",[])]}
        if settings.serper_api_key:
            async with httpx.AsyncClient(timeout=30) as client:
                r=await client.post("https://google.serper.dev/search",headers={"X-API-KEY":settings.serper_api_key,"Content-Type":"application/json"},json={"q":query,"num":max_results}); r.raise_for_status(); d=r.json()
            return {"provider":"serper","results":[{"title":x.get("title"),"url":x.get("link"),"snippet":x.get("snippet","")} for x in d.get("organic",[])[:max_results]]}
        return {"provider":None,"results":[],"warning":"Configure TAVILY_API_KEY or SERPER_API_KEY for live web research."}
