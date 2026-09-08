from uuid import UUID
from jarvis.config import settings
from jarvis.db import Database
from jarvis.schemas import ExecutionPlan, AgentResult
from jarvis.agents.manager import AgentManager
from jarvis.verification import VerificationEngine

class WorkflowEngine:
    def __init__(self, db: Database, agents: AgentManager):
        self.db=db; self.agents=agents; self.verifier=VerificationEngine()

    async def execute(self, workflow_id: UUID, plan: ExecutionPlan, context: str):
        completed: dict[str,AgentResult]={}
        provider_used=None; model_used=None
        pending={t.id:t for t in plan.tasks}

        while pending:
            progressed=False
            for key,task in list(pending.items()):
                if not all(dep in completed for dep in task.dependencies):
                    continue
                progressed=True
                tid=self.db.create_task(workflow_id,task.id,task.agent,task.model_dump())
                self.db.update_task(tid,"running")
                deps=[completed[d] for d in task.dependencies]
                attempts=0
                last=None
                while attempts <= settings.max_task_retries:
                    attempts+=1
                    try:
                        result,provider_used,model_used=await self.agents.get(task.agent).run(task,context,deps)
                        ok,reason=self.verifier.verify(result)
                        if ok:
                            self.db.update_task(tid,"completed",result.model_dump(),attempts-1)
                            completed[key]=result
                            break
                        last=reason
                    except Exception as e:
                        last=str(e)
                    if attempts > settings.max_task_retries:
                        self.db.update_task(tid,"failed",{"error":last or "unknown"},attempts-1)
                        failed=AgentResult(ok=False,summary=f"Task {task.id} failed: {last}")
                        self.db.finish_workflow(workflow_id,"failed",failed.model_dump())
                        return failed,provider_used,model_used
                del pending[key]
            if not progressed:
                failed=AgentResult(ok=False,summary="Workflow contains unresolved or cyclic dependencies.")
                self.db.finish_workflow(workflow_id,"failed",failed.model_dump())
                return failed,provider_used,model_used

        ordered=[completed[t.id] for t in plan.tasks if t.id in completed]
        if len(ordered)==1:
            final=ordered[0]
        else:
            final=AgentResult(ok=True,summary="\n\n".join(r.summary for r in ordered),sources=[s for r in ordered for s in r.sources],artifacts=[a for r in ordered for a in r.artifacts])
        self.db.finish_workflow(workflow_id,"completed",final.model_dump())
        return final,provider_used,model_used
