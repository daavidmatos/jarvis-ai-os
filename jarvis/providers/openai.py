import base64

import httpx

from jarvis.config import settings
from jarvis.credentials import credential_store
from jarvis.providers.base import LLMProvider, ModelReply, ProviderAPIError


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

    @staticmethod
    def _upstream_error(response: httpx.Response) -> tuple[str | None, str | None]:
        try:
            payload = response.json()
        except Exception:
            return None, None
        error = payload.get("error") if isinstance(payload, dict) else None
        if not isinstance(error, dict):
            return None, None
        code = error.get("code") or error.get("type")
        message = error.get("message")
        return (str(code) if code else None, str(message) if message else None)

    def _provider_error(self, response: httpx.Response) -> ProviderAPIError:
        status = response.status_code
        code, raw_message = self._upstream_error(response)
        raw_message = (raw_message or "").strip().replace("\n", " ")[:320]

        if status in {401, 403}:
            message = (
                "A OpenAI recusou a credencial da API ou as permissões do projeto. "
                "Verifique a OPENAI_API_KEY configurada no servidor."
            )
            api_status = 502
        elif status == 429 and code == "insufficient_quota":
            message = (
                "A API da OpenAI está sem cota/créditos de faturamento. "
                "A assinatura do ChatGPT é separada da API; configure billing/créditos na OpenAI Platform."
            )
            api_status = 429
        elif status == 429:
            message = "A API da OpenAI atingiu um limite temporário de uso. Tente novamente em instantes."
            api_status = 429
        elif status == 404:
            message = f"O modelo OpenAI configurado ({self.model}) não está disponível para este projeto."
            api_status = 502
        elif status == 400:
            message = "A OpenAI recusou a solicitação enviada pelo JARVIS."
            if raw_message:
                message += f" Detalhe: {raw_message}"
            api_status = 502
        elif status >= 500:
            message = "A OpenAI está temporariamente indisponível. Tente novamente em instantes."
            api_status = 502
        else:
            message = f"Falha ao consultar a OpenAI (HTTP {status})."
            if raw_message:
                message += f" Detalhe: {raw_message}"
            api_status = 502

        return ProviderAPIError(
            self.name,
            message,
            status_code=api_status,
            upstream_code=code,
        )

    async def _responses(self, payload: dict) -> dict:
        key = self.api_key
        if not key:
            raise RuntimeError("OpenAI is not configured")
        try:
            async with httpx.AsyncClient(timeout=120) as client:
                r = await client.post(
                    "https://api.openai.com/v1/responses",
                    headers={"Authorization": f"Bearer {key}", "Content-Type": "application/json"},
                    json=payload,
                )
        except httpx.HTTPError as exc:
            raise ProviderAPIError(
                self.name,
                "Não foi possível conectar à API da OpenAI. Tente novamente em instantes.",
                status_code=502,
                upstream_code=exc.__class__.__name__,
            ) from None

        if r.is_error:
            raise self._provider_error(r)
        try:
            return r.json()
        except ValueError:
            raise ProviderAPIError(
                self.name,
                "A OpenAI retornou uma resposta inválida ao JARVIS.",
                status_code=502,
                upstream_code="invalid_json",
            ) from None

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

    async def complete_vision(
        self,
        system: str,
        user: str,
        image_bytes: bytes,
        mime_type: str = "image/jpeg",
    ) -> ModelReply:
        """Analyze one bounded local Desktop Bridge frame through Responses API.

        Frames remain server-side and are embedded as a data URL only for this model
        request; no public screenshot URL is required.
        """
        if mime_type not in {"image/jpeg", "image/png", "image/webp"}:
            raise ValueError("Unsupported image MIME type")
        encoded = base64.b64encode(image_bytes).decode("ascii")
        data = await self._responses(
            {
                "model": self.model,
                "instructions": system,
                "input": [
                    {
                        "role": "user",
                        "content": [
                            {"type": "input_text", "text": user},
                            {
                                "type": "input_image",
                                "image_url": f"data:{mime_type};base64,{encoded}",
                            },
                        ],
                    }
                ],
            }
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
