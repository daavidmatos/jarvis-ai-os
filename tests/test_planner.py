import pytest
from jarvis.planner import Planner
from jarvis.router import ModelRouter
from jarvis.config import settings

@pytest.mark.asyncio
async def test_explicit_local_fallback_research(monkeypatch):
    monkeypatch.setattr(settings,"allow_local_fallback",True)
    r=ModelRouter()
    p=Planner(r)
    plan=await p.create("Pesquise o mercado de barras energéticas")
    assert plan.tasks
    assert plan.tasks[0].agent=="research"

def test_openai_is_primary():
    r=ModelRouter()
    first=r.catalog()[0]
    assert first["provider"]=="openai"
    assert first["primary"] is True
