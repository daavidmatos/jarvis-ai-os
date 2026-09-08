import httpx

from jarvis.config import settings
from jarvis.credentials import credential_store
from jarvis.providers.base import LLMProvider, ModelReply, ProviderAPIError


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

    @staticmethod
    def _upstream_error(response: httpx.Response) -> tuple[str | None, str | None]:
        try:
            payload = response.json()
        except Exception:
            return None, None
        error = payload.get("error") if isinstance(payload, dict) else None
        if not isinstance(error, dict):
            return None, None
        code = error.get("status") or error.get("code")
        message = error.get("message")
        return (str(code) if code is not None else None, str(message) if message else None)

    def _provider_error(self, response: httpx.Response) -> ProviderAPIError:
        status = response.status_code
        code, raw_message = self._upstream_error(response)
        raw_message = (raw_message or "").strip().replace("\n", " ")[:320]
        normalized_code = (code or "").upper()

        if status in {401, 403}:
            message = (
                "O Google Gemini recusou a chave da API ou as permissões do projeto. "
                "Verifique a GOOGLE_API_KEY configurada no servidor."
            )
            api_status = 502
        elif status == 429 or normalized_code == "RESOURCE_EXHAUSTED":
            message = (
                "O Gemini atingiu um limite de cota/rate limit da API. "
                "No Free Tier, aguarde a cota liberar ou use o modelo Flash-Lite para testes de maior volume."
            )
            api_status = 429
        elif status == 404:
            message = f"O modelo Gemini configurado ({self.model}) não está disponível para este projeto."
            api_status = 502
        elif status == 400:
            message = "O Gemini recusou a solicitação enviada pelo JARVIS."
            if raw_message:
                message += f" Detalhe: {raw_message}"
            api_status = 502
        elif status >= 500:
            message = "O Gemini está temporariamente indisponível. Tente novamente em instantes."
            api_status = 502
        else:
            message = f"Falha ao consultar o Gemini (HTTP {status})."
            if raw_message:
                message += f" Detalhe: {raw_message}"
            api_status = 502

        return ProviderAPIError(
            self.name,
            message,
            status_code=api_status,
            upstream_code=code,
        )

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
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                r = await client.post(url, params={"key": key}, json=payload)
        except httpx.HTTPError as exc:
            raise ProviderAPIError(
                self.name,
                "Não foi possível conectar à API do Gemini. Tente novamente em instantes.",
                status_code=502,
                upstream_code=exc.__class__.__name__,
            ) from None

        if r.is_error:
            raise self._provider_error(r)
        try:
            data = r.json()
        except ValueError:
            raise ProviderAPIError(
                self.name,
                "O Gemini retornou uma resposta inválida ao JARVIS.",
                status_code=502,
                upstream_code="invalid_json",
            ) from None

        candidates = data.get("candidates") or []
        if not candidates:
            raise ProviderAPIError(
                self.name,
                "O Gemini não retornou uma resposta utilizável para esta solicitação.",
                status_code=502,
                upstream_code="empty_candidates",
            )
        parts = candidates[0].get("content", {}).get("parts", [])
        text = "\n".join(p.get("text", "") for p in parts if isinstance(p, dict))
        if not text.strip():
            raise ProviderAPIError(
                self.name,
                "O Gemini retornou uma resposta vazia ao JARVIS.",
                status_code=502,
                upstream_code="empty_text",
            )
        return ModelReply(text=text, provider=self.name, model=self.model)
