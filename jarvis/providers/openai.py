import httpx
from jarvis.config import settings
from jarvis.providers.base import LLMProvider, ModelReply

class OpenAIProvider(LLMProvider):
    name = "openai"
    def __init__(self): self.model = settings.openai_model
    @property
    def available(self): return bool(settings.openai_api_key)

    async def complete(self, system: str, user: str, *, temperature: float = 0.2) -> ModelReply:
        if not self.available: raise RuntimeError("OPENAI_API_KEY is not configured")
        payload = {"model": self.model, "instructions": system, "input": user}
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post("https://api.openai.com/v1/responses", headers={"Authorization": f"Bearer {settings.openai_api_key}", "Content-Type": "application/json"}, json=payload)
            r.raise_for_status(); data = r.json()
        text = data.get("output_text")
        if not text:
            chunks=[]
            for item in data.get("output", []):
                for c in item.get("content", []):
                    if c.get("type") in {"output_text","text"}: chunks.append(c.get("text", ""))
            text="\n".join(chunks)
        return ModelReply(text=text or "", provider=self.name, model=self.model)
