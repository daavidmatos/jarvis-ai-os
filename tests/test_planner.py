import pytest
from jarvis.planner import Planner
from jarvis.router import ModelRouter

@pytest.mark.asyncio
async def test_fallback_research(monkeypatch):
    r=ModelRouter()
    for name in ["openai","anthropic","google"]: r.providers[name].__dict__["_disabled"]=True
    # No keys in CI -> mock path
    p=Planner(r)
    plan=await p.create("Pesquise o mercado de barras energéticas")
    assert plan.tasks
    assert plan.tasks[0].agent=="research"
