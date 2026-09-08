from jarvis.providers.base import LLMProvider, ModelReply

class MockProvider(LLMProvider):
    name="mock"; model="deterministic-local"
    @property
    def available(self): return True
    async def complete(self, system: str, user: str, *, temperature: float=0.2) -> ModelReply:
        return ModelReply(text=f"[Modo local sem API] {user[:1200]}",provider=self.name,model=self.model)
