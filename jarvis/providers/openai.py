import httpx

from jarvis.config import settings
from jarvis.credentials import credential_store
from jarvis.providers.base import LLMProvider, ModelReply


class OpenAIProvider(LLMProvider):
    name = "openai"

    def __init__(self):
        self.model = settings.openai_model

    @property
    def api_key(self) -> str | None:
        return credential_store.get(self.name)

    @property
    def available(self):
        return bool(self.api_key)

    async def _responses(self, payload: dict) -> dict:
        key = self.api_key
        if not key:
            raise RuntimeError("OpenAI is not configured")
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(
                "https://api.openai.com/v1/responses",
                headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                json=payload,
            )
            r.raise_for_status()
            return r.json()

    @staticmethod
    def _text(data: dict) -> str:
        if data.get("output_text"):
            return data["output_text"]
        chunks = []
        for item in data.get("output", []):
            for c in item.get("content", []):
                if c.get("type") in {"output_text", "text"}:
                    chunks.append(c.get("text", ""))
        return "\n".join(chunks)

    async def complete(self, system: str, user: str, *, temperature: float = 0.2) -> ModelReply:
        data = await self._responses(
            {"model": self.model, "instructions": system, "input": user}
        )
        return ModelReply(text=self._text(data), provider=self.name, model=self.model)

    async def web_search(self, query: str) -> dict:
        data = await self._responses(
            {
                "model": self.model,
                "instructions": (
                    "Search the public web. Return a concise evidence summary and cite "
                    "source URLs when available. Do not invent sources."
                ),
                "input": query,
                "tools": [{"type": "web_search"}],
            }
        )
        citations = []
        for item in data.get("output", []):
            for c in item.get("content", []):
                for ann in c.get("annotations", []) or []:
                    url = ann.get("url") or ann.get("url_citation", {}).get("url")
                    title = ann.get("title") or ann.get("url_citation", {}).get("title")
                    if url and not any(x["url"] == url for x in citations):
                        citations.append({"title": title or url, "url": url})
        return {
            "provider": "openai",
            "summary": self._text(data),
            "citations": citations,
            "response_id": data.get("id"),
        }
