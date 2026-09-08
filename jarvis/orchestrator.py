from uuid import UUID
from jarvis.db import Database
from jarvis.router import ModelRouter
from jarvis.tools.registry import ToolRegistry
from jarvis.agents.manager import AgentManager
from jarvis.planner import Planner
from jarvis.memory import MemoryEngine
from jarvis.workflows import WorkflowEngine

class Orchestrator:
    def __init__(self, db: Database | None=None):
        self.db=db or Database(); self.db.init()
        self.router=ModelRouter(); self.tools=ToolRegistry(); self.memory=MemoryEngine(self.db)
        self.planner=Planner(self.router); self.agents=AgentManager(self.router,self.tools)
        self.workflows=WorkflowEngine(self.db,self.agents)

    async def handle(self, message: str, session_id: UUID | None=None):
        sid=self.db.create_session(session_id)
        self.db.add_message(sid,"user",message)
        memories=self.memory.context_text(message)
        history=self.db.recent_messages(sid,limit=10)
        history_text="\n".join(f"{m['role']}: {m['content']}" for m in history[:-1])
        context=f"Relevant memory:\n{memories or '(none)'}\n\nRecent conversation:\n{history_text or '(none)'}"
        plan=await self.planner.create(message,context)
        wid=self.db.create_workflow(sid,message,plan.model_dump())
        self.db.audit("workflow.started",{"goal":message,"plan":plan.model_dump()},wid)
        result,provider,model=await self.workflows.execute(wid,plan,context)
        self.db.add_message(sid,"assistant",result.summary)
        self.db.audit("workflow.finished",{"ok":result.ok,"provider":provider,"model":model},wid)
        return {"workflow_id":wid,"session_id":sid,"status":"completed" if result.ok else "failed","message":result.summary,"provider":provider,"model":model,"sources":result.sources}
