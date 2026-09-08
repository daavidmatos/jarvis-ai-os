from dataclasses import dataclass
from jarvis.providers.openai import OpenAIProvider
from jarvis.providers.anthropic import AnthropicProvider
from jarvis.providers.google import GoogleProvider
from jarvis.providers.mock import MockProvider
from jarvis.config import settings

class PrimaryAIUnavailable(RuntimeError):
    pass

@dataclass
class RoutingDecision:
    provider: object
    reason: str
    score: float

class ModelRouter:
    CAPABILITIES={"openai":{"text","reasoning","coding","research","vision","tools","data","creative","operations"},"anthropic":{"text","reasoning","coding","analysis","research"},"google":{"text","reasoning","vision","multimodal","data","creative","research"},"mock":{"text"}}
    FIT={"general":{"openai":1.00,"anthropic":0.84,"google":0.82},"research":{"openai":1.00,"anthropic":0.88,"google":0.93},"coding":{"openai":0.97,"anthropic":1.00,"google":0.84},"creative":{"openai":0.94,"anthropic":0.80,"google":1.00},"data":{"openai":0.95,"anthropic":0.87,"google":1.00},"operations":{"openai":1.00,"anthropic":0.80,"google":0.86}}
    def __init__(self):
        self.providers={p.name:p for p in [OpenAIProvider(),AnthropicProvider(),GoogleProvider(),MockProvider()]}; self.last_decision=None
    def primary(self):
        p=self.providers.get(settings.primary_provider)
        if p and p.available:
            self.last_decision=RoutingDecision(p,"primary cognition",1.0); return p
        if settings.allow_local_fallback:
            p=self.providers["mock"]; self.last_decision=RoutingDecision(p,"explicit local fallback",0.0); return p
        raise PrimaryAIUnavailable("JARVIS primary AI is not configured. Configure OPENAI_API_KEY once; after that OpenAI is used automatically and provider selection is autonomous.")
    def _eligible(self,name,required):
        p=self.providers[name]; return p.available and required.issubset(self.CAPABILITIES.get(name,{"text"}))
    def select_for_task(self,agent,capabilities=None):
        required=set(capabilities or ["text"]); primary=self.primary()
        if not settings.autonomous_routing or not settings.allow_external_ai: return primary
        candidates=[]; fit=self.FIT.get(agent,self.FIT["general"])
        for name in ("openai","anthropic","google"):
            if not self._eligible(name,required): continue
            score=fit.get(name,0.75)+(0.025 if name==settings.primary_provider else 0)
            candidates.append(RoutingDecision(self.providers[name],f"autonomous fit for {agent}",score))
        if not candidates: return primary
        d=max(candidates,key=lambda x:x.score); self.last_decision=d; return d.provider
    def select(self,capabilities=None,preferred=None):
        if preferred and preferred!="auto" and preferred in self.providers and self.providers[preferred].available:
            p=self.providers[preferred]; self.last_decision=RoutingDecision(p,"explicit architecture preference",1.0); return p
        return self.select_for_task("general",capabilities)
    def catalog(self):
        return [{"provider":p.name,"model":p.model,"available":p.available,"primary":p.name==settings.primary_provider,"role":"primary" if p.name==settings.primary_provider else ("specialist" if p.name!="mock" else "fallback"),"capabilities":sorted(self.CAPABILITIES.get(p.name,{"text"}))} for p in self.providers.values()]
