import httpx

from jarvis.config import settings
from jarvis.credentials import credential_store
from jarvis.providers.base import LLMProvider, ModelReply


class GoogleProvider(LLMProvider):
    name = "google"

    def __init__(self):
        self.model = settings.google_model

    @property
    def api_key(self) -> str | None:
        return credential_store.get(self.name)

    @property
    def available(self):
        return bool(self.api_key)

    async def complete(self, system: str, user: str, *, temperature: float = 0.2) -> ModelReply:
        key = self.api_key
        if not key:
            raise RuntimeError("Google AI is not configured")
        url = (
            f"https://generativelanguage.googleapis.com/v1beta/models/"
            f"{self.model}:generateContent"
        )
        payload = {
            "systemInstruction": {"parts": [{"text": system}]},
            "contents": [{"role": "user", "parts": [{"text": user}]}],
            "generationConfig": {"temperature": temperature},
        }
        async with httpx.AsyncClient(timeout=120) as client:
            r = await client.post(url, params={"key": key}, json=payload)
            r.raise_for_status()
            data = r.json()
        parts = data.get("candidates", [{}])[0].get("content", {}).get("parts", [])
        text = "\n".join(p.get("text", "") for p in parts)
        return ModelReply(text=text, provider=self.name, model=self.model)
