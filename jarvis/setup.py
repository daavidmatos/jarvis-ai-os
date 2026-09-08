import httpx

from jarvis.config import settings
from jarvis.credentials import credential_store


class ProviderSetupService:
    providers = {"openai", "anthropic", "google"}

    async def validate(self, provider: str, api_key: str) -> None:
        if provider not in self.providers:
            raise ValueError(f"Unsupported provider: {provider}")
        key = api_key.strip()
        if len(key) < 20:
            raise ValueError("API key is too short")

        try:
            async with httpx.AsyncClient(timeout=30) as client:
                if provider == "openai":
                    response = await client.get(
                        f"https://api.openai.com/v1/models/{settings.openai_model}",
                        headers={"Authorization": f"Bearer {key}"},
                    )
                elif provider == "anthropic":
                    response = await client.post(
                        "https://api.anthropic.com/v1/messages",
                        headers={
                            "x-api-key": key,
                            "anthropic-version": "2023-06-01",
                            "content-type": "application/json",
                        },
                        json={
                            "model": settings.anthropic_model,
                            "max_tokens": 1,
                            "messages": [{"role": "user", "content": "Reply OK"}],
                        },
                    )
                else:
                    response = await client.get(
                        f"https://generativelanguage.googleapis.com/v1beta/models/{settings.google_model}",
                        params={"key": key},
                    )
                response.raise_for_status()
        except httpx.HTTPStatusError as exc:
            status = exc.response.status_code
            if status in {401, 403}:
                raise ValueError(f"{provider.title()} rejected this API key") from None
            if status == 404:
                raise ValueError(
                    f"{provider.title()} accepted the request, but the configured model is not available"
                ) from None
            raise ValueError(f"{provider.title()} validation failed with HTTP {status}") from None
        except httpx.HTTPError:
            raise ValueError(f"Could not reach {provider.title()} to validate the credential") from None

    async def configure(self, provider: str, api_key: str) -> dict:
        await self.validate(provider, api_key)
        credential_store.set(provider, api_key)
        return {"provider": provider, "configured": True}

    def disconnect(self, provider: str) -> dict:
        if provider not in self.providers:
            raise ValueError(f"Unsupported provider: {provider}")
        removed = credential_store.delete(provider)
        return {"provider": provider, "configured": False, "removed": removed}


setup_service = ProviderSetupService()
