import json, re
from jarvis.config import settings
from jarvis.router import ModelRouter, PrimaryAIUnavailable
from jarvis.schemas import ExecutionPlan, PlanTask

SYSTEM="""You are JARVIS Planner, the primary planning brain. Return ONLY valid JSON with this shape:
{"goal":"...","tasks":[{"id":"t1","agent":"research|coding|creative|data|operations|general","action":"...","instruction":"...","dependencies":[],"required_capabilities":["text"]}]}
Create the smallest useful DAG. Choose agents/capabilities based on the user's goal. Do NOT choose an AI provider; the Model Router does that autonomously. Never create more than 8 tasks. Low/medium-risk reversible tools may be used autonomously. High-impact external actions must require approval."""

class Planner:
    def __init__(self, router: ModelRouter): self.router=router
    async def create(self,message:str,context:str="")->ExecutionPlan:
        try: provider=self.router.primary()
        except PrimaryAIUnavailable:
            if settings.allow_local_fallback: return self._fallback(message)
            raise
        if provider.name=="mock": return self._fallback(message)
        try:
            reply=await provider.complete(SYSTEM,f"User request:\n{message}\n\nContext:\n{context}")
            raw=reply.text.strip(); match=re.search(r"\{.*\}",raw,re.S); data=json.loads(match.group(0) if match else raw)
            plan=ExecutionPlan.model_validate(data); plan.tasks=plan.tasks[:settings.max_plan_tasks]; return plan
        except Exception:
            if settings.allow_local_fallback: return self._fallback(message)
            raise
    def _fallback(self,message:str)->ExecutionPlan:
        l=message.lower()
        if any(k in l for k in ["pesquise","pesquisar","research","mercado","compare","últimas","latest"]): agent="research";action="research_and_synthesize";caps=["text","research"]
        elif any(k in l for k in ["código","code","program","bug","api","python","javascript"]): agent="coding";action="analyze_and_implement";caps=["text","coding"]
        elif any(k in l for k in ["dados","planilha","métrica","análise","csv"]): agent="data";action="analyze_data";caps=["text","data"]
        elif any(k in l for k in ["email","calendário","agenda","enviar"]): agent="operations";action="prepare_operation";caps=["text","operations"]
        elif any(k in l for k in ["imagem","vídeo","copy","criativo"]): agent="creative";action="create_concept";caps=["text","creative"]
        else: agent="general";action="answer";caps=["text"]
        return ExecutionPlan(goal=message,tasks=[PlanTask(id="t1",agent=agent,action=action,instruction=message,required_capabilities=caps)])
