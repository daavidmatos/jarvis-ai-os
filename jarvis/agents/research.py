from jarvis.agents.base import Agent
from jarvis.schemas import AgentResult, PlanTask

class ResearchAgent(Agent):
    name="research"
    async def run(self,task:PlanTask,context:str,dependency_results:list[AgentResult]):
        search=await self.tools.execute("web.search",query=task.instruction,max_results=6)
        results=search.get("result",{}).get("results",[]) if search.get("ok") else []
        evidence="\n".join(f"- {x.get('title')}: {x.get('snippet')} ({x.get('url')})" for x in results)
        provider=self.router.select_for_task("research",task.required_capabilities)
        prompt=f"Research request: {task.instruction}\n\nMemory/context:\n{context}\n\nSearch evidence:\n{evidence or 'No live evidence was returned.'}\n\nProduce a useful synthesis. Clearly distinguish evidence from inference."
        reply=await provider.complete("You are JARVIS Research Agent. Never fabricate sources.",prompt)
        return AgentResult(ok=True,summary=reply.text,sources=results,data={"search_provider":search.get("result",{}).get("provider"),"routing_reason":getattr(self.router.last_decision,"reason",None)}),reply.provider,reply.model
