import json, re
from jarvis.config import settings
from jarvis.router import ModelRouter
from jarvis.schemas import AgentResult, PlanTask
from jarvis.tools.registry import ToolRegistry

TOOL_SYSTEM="""You are JARVIS, an autonomous but policy-constrained AI agent.
You may use the safe tools listed by the runtime when doing so materially helps complete the user's task.
Never claim a tool was used unless the runtime returned a tool result.
For each step, output either normal final text OR exactly one JSON tool request:
{"tool":"tool.name","arguments":{...}}
Use tools only when useful. Do not attempt high-risk or destructive actions without approval."""

class Agent:
    name="general"
    def __init__(self,router:ModelRouter,tools:ToolRegistry): self.router=router; self.tools=tools
    @staticmethod
    def _tool_call(text:str):
        match=re.search(r"\{.*\}",text.strip(),re.S)
        if not match: return None
        try: data=json.loads(match.group(0))
        except Exception: return None
        return data if isinstance(data,dict) and isinstance(data.get("tool"),str) and isinstance(data.get("arguments",{}),dict) else None
    async def run(self,task:PlanTask,context:str,dependency_results:list[AgentResult])->tuple[AgentResult,str,str]:
        provider=self.router.select_for_task(task.agent,task.required_capabilities)
        deps="\n\n".join(r.summary for r in dependency_results)
        tool_specs=self.tools.autonomous_specs()
        transcript=[]
        base=f"Task: {task.instruction}\n\nContext:\n{context}\n\nDependency results:\n{deps or '(none)'}\n\nAvailable safe tools:\n{json.dumps(tool_specs,ensure_ascii=False)}"
        for _ in range(settings.max_agent_steps):
            prompt=base+("\n\nTool transcript:\n"+"\n".join(transcript) if transcript else "")
            reply=await provider.complete(TOOL_SYSTEM,prompt)
            call=self._tool_call(reply.text)
            if not call:
                return AgentResult(ok=True,summary=reply.text,data={"routing_reason":getattr(self.router.last_decision,"reason",None)}),reply.provider,reply.model
            name=call["tool"]
            if name not in self.tools.tools:
                transcript.append(f"Unknown tool requested: {name}"); continue
            result=await self.tools.execute(name,**call.get("arguments",{}))
            transcript.append(json.dumps({"tool":name,"result":result},ensure_ascii=False)[:12000])
        reply=await provider.complete("You are JARVIS. Give the best final answer using the tool results already provided. Do not request another tool.",base+"\n\nTool transcript:\n"+"\n".join(transcript))
        return AgentResult(ok=True,summary=reply.text,data={"tool_steps":len(transcript)}),reply.provider,reply.model
