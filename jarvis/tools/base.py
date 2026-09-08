from abc import ABC, abstractmethod
from typing import Any
from jarvis.schemas import RiskLevel, ToolSpec

class Tool(ABC):
    name: str
    description: str
    risk: RiskLevel = RiskLevel.LOW
    requires_approval: bool = False

    @property
    def spec(self) -> ToolSpec:
        return ToolSpec(name=self.name, description=self.description, risk=self.risk, requires_approval=self.requires_approval)

    @abstractmethod
    async def run(self, **kwargs) -> dict[str, Any]: ...
