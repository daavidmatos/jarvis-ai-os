from jarvis.router import ModelRouter
from jarvis.schemas import AgentResult, PlanTask
from jarvis.tools.registry import ToolRegistry

class Agent:
    name="general"
    def __init__(self, router: ModelRouter, tools: ToolRegistry): self.router=router; self.tools=tools
    async def run(self, task: PlanTask, context: str, dependency_results: list[AgentResult]) -> tuple[AgentResult,str,str]:
        provider=self.router.select(task.required_capabilities)
        deps="\n\n".join(r.summary for r in dependency_results)
        prompt=f"Task: {task.instruction}\n\nContext:\n{context}\n\nDependency results:\n{deps}"
        reply=await provider.complete("You are JARVIS. Be concise, accurate, and action-oriented. Do not claim actions you did not perform.",prompt)
        return AgentResult(ok=True,summary=reply.text),reply.provider,reply.model
