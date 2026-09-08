import json, re
from jarvis.config import settings
from jarvis.router import ModelRouter
from jarvis.schemas import ExecutionPlan, PlanTask

SYSTEM = """You are JARVIS Planner. Return ONLY valid JSON with this shape:
{"goal":"...","tasks":[{"id":"t1","agent":"research|coding|creative|data|operations|general","action":"...","instruction":"...","dependencies":[],"required_capabilities":["text"]}]}
Create the smallest useful DAG. Never create more than 8 tasks. High-impact external actions should be represented as analysis/preparation, not executed automatically."""

class Planner:
    def __init__(self, router: ModelRouter): self.router=router

    async def create(self, message: str, context: str="") -> ExecutionPlan:
        provider=self.router.select(["text"])
        if provider.name != "mock":
            try:
                reply=await provider.complete(SYSTEM, f"User request:\n{message}\n\nContext:\n{context}")
                raw=reply.text.strip()
                match=re.search(r"\{.*\}",raw,re.S)
                data=json.loads(match.group(0) if match else raw)
                plan=ExecutionPlan.model_validate(data)
                plan.tasks=plan.tasks[:settings.max_plan_tasks]
                return plan
            except Exception:
                pass
        return self._fallback(message)

    def _fallback(self, message: str) -> ExecutionPlan:
        l=message.lower()
        if any(k in l for k in ["pesquise","pesquisar","research","mercado","compare","últimas","latest"]):
            agent="research"; action="research_and_synthesize"
        elif any(k in l for k in ["código","code","program","bug","api","python","javascript"]):
            agent="coding"; action="analyze_and_implement"
        elif any(k in l for k in ["dados","planilha","métrica","análise","csv"]):
            agent="data"; action="analyze_data"
        elif any(k in l for k in ["email","calendário","agenda","enviar"]):
            agent="operations"; action="prepare_operation"
        elif any(k in l for k in ["imagem","vídeo","copy","criativo"]):
            agent="creative"; action="create_concept"
        else:
            agent="general"; action="answer"
        return ExecutionPlan(goal=message,tasks=[PlanTask(id="t1",agent=agent,action=action,instruction=message)])
