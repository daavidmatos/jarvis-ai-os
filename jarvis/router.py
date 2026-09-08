from jarvis.providers.openai import OpenAIProvider
from jarvis.providers.anthropic import AnthropicProvider
from jarvis.providers.google import GoogleProvider
from jarvis.providers.mock import MockProvider
from jarvis.config import settings

class ModelRouter:
    def __init__(self):
        self.providers={p.name:p for p in [OpenAIProvider(),AnthropicProvider(),GoogleProvider(),MockProvider()]}

    def select(self, capabilities: list[str] | None=None, preferred: str | None=None):
        preferred = preferred or settings.default_provider
        if preferred != "auto" and preferred in self.providers and self.providers[preferred].available:
            return self.providers[preferred]
        for name in ("openai","anthropic","google"):
            if self.providers[name].available: return self.providers[name]
        return self.providers["mock"]

    def catalog(self):
        return [{"provider":p.name,"model":p.model,"available":p.available} for p in self.providers.values()]
