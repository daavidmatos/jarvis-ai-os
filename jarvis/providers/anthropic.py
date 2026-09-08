import httpx
from jarvis.config import settings
from jarvis.providers.base import LLMProvider, ModelReply

class AnthropicProvider(LLMProvider):
    name = "anthropic"
    def __init__(self): self.model = settings.anthropic_model
    @property
    def available(self): return bool(settings.anthropic_api_key)

    async def complete(self, system: str, user: str, *, temperature: float = 0.2) -> ModelReply:
        if not self.available: raise RuntimeError("ANTHROPIC_API_KEY is not configured")
        payload={"model":self.model,"max_tokens":4096,"system":system,"messages":[{"role":"user","content":user}]}
        headers={"x-api-key":settings.anthropic_api_key,"anthropic-version":"2023-06-01","content-type":"application/json"}
        async with httpx.AsyncClient(timeout=120) as client:
            r=await client.post("https://api.anthropic.com/v1/messages",headers=headers,json=payload); r.raise_for_status(); data=r.json()
        text="\n".join(x.get("text","") for x in data.get("content",[]) if x.get("type")=="text")
        return ModelReply(text=text,provider=self.name,model=self.model)
