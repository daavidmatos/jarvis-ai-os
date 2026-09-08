from abc import ABC, abstractmethod
from dataclasses import dataclass

@dataclass
class ModelReply:
    text: str
    provider: str
    model: str

class LLMProvider(ABC):
    name: str
    model: str

    @property
    @abstractmethod
    def available(self) -> bool: ...

    @abstractmethod
    async def complete(self, system: str, user: str, *, temperature: float = 0.2) -> ModelReply: ...
