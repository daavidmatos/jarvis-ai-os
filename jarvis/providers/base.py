from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class ModelReply:
    text: str
    provider: str
    model: str


class ProviderAPIError(RuntimeError):
    """Safe, user-facing wrapper for an upstream model-provider failure.

    Provider implementations should translate raw HTTP/client errors into this
    exception so the API can return a useful JSON error without leaking secrets or
    dumping an upstream response body into the browser.
    """

    def __init__(
        self,
        provider: str,
        message: str,
        *,
        status_code: int = 502,
        upstream_code: str | None = None,
    ) -> None:
        super().__init__(message)
        self.provider = provider
        self.status_code = status_code
        self.upstream_code = upstream_code


class LLMProvider(ABC):
    name: str
    model: str

    @property
    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    async def complete(self, system: str, user: str, *, temperature: float = 0.2) -> ModelReply: ...
