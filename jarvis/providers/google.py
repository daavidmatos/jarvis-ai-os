import httpx
from jarvis.config import settings
from jarvis.providers.base import LLMProvider, ModelReply

class GoogleProvider(LLMProvider):
    name = "google"
    def __init__(self): self.model = settings.google_model
    @property
    def available(self): return bool(settings.google_api_key)

    async def complete(self, system: str, user: str, *, temperature: float = 0.2) -> ModelReply:
        if not self.available: raise RuntimeError("GOOGLE_API_KEY is not configured")
        url=f"https://generativelanguage.googleapis.com/v1beta/models/{self.model}:generateContent?key={settings.google_api_key}"
        payload={"systemInstruction":{"parts":[{"text":system}]},"contents":[{"role":"user","parts":[{"text":user}]}],"generationConfig":{"temperature":temperature}}
        async with httpx.AsyncClient(timeout=120) as client:
            r=await client.post(url,json=payload); r.raise_for_status(); data=r.json()
        parts=data.get("candidates",[{}])[0].get("content",{}).get("parts",[])
        text="\n".join(p.get("text","") for p in parts)
        return ModelReply(text=text,provider=self.name,model=self.model)
