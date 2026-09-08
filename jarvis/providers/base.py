from abc import ABC, abstractmethod
from dataclasses import dataclass

from fastapi import HTTPException


@dataclass
class ModelReply:
    text: str
    provider: str
    model: str


class ProviderAPIError(HTTPException):
    """Safe HTTP error for an upstream model-provider failure.

    Provider implementations translate raw upstream failures into this exception so
    FastAPI returns useful JSON instead of an opaque 500 page. Secrets and raw
    response bodies are never exposed.
    """

    def __init__(
        self,
        provider: str,
        message: str,
        *,
        status_code: int = 502,
        upstream_code: str | None = None,
    ) -> None:
        detail = {
            "code": "provider_error",
            "provider": provider,
            "message": message,
        }
        if upstream_code:
            detail["upstream_code"] = upstream_code
        super().__init__(status_code=status_code, detail=detail)
        self.provider = provider
        self.upstream_code = upstream_code


class LLMProvider(ABC):
    name: str
    model: str

    @property
    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    async def complete(self, system: str, user: str, *, temperature: float = 0.2) -> ModelReply: ...
