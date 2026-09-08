import json
from uuid import UUID

from jarvis.agents.manager import AgentManager
from jarvis.config import settings
from jarvis.db import Database
from jarvis.memory import MemoryEngine
from jarvis.planner import Planner
from jarvis.router import ModelRouter
from jarvis.schemas import AgentResult
from jarvis.tools.registry import ToolRegistry
from jarvis.workflows import WorkflowEngine


FINALIZER_SYSTEM = """You are JARVIS Core, powered by OpenAI.
You are the user's primary intelligence and final decision/synthesis layer.
A specialist model may have performed a delegated subtask. Use its output as evidence,
not as unquestionable truth. Preserve useful source references, resolve contradictions,
and return the best concise final answer. Never claim actions that were not actually executed."""


class Orchestrator:
    def __init__(self, db: Database | None = None):
        self.db = db or Database()
        self.db.init()
        self.router = ModelRouter()
        self.tools = ToolRegistry()
        self.memory = MemoryEngine(self.db)
        self.planner = Planner(self.router)
        self.agents = AgentManager(self.router, self.tools)
        self.workflows = WorkflowEngine(self.db, self.agents)

    async def _finalize_with_primary(
        self,
        goal: str,
        result: AgentResult,
        delegated_provider: str | None,
        delegated_model: str | None,
        task_count: int,
    ) -> tuple[AgentResult, str | None, str | None]:
        primary = self.router.primary()
        should_finalize = (
            result.ok
            and (
                task_count > 1
                or delegated_provider != primary.name
            )
        )
        if not settings.finalize_with_primary or not should_finalize:
            return result, delegated_provider, delegated_model

        payload = {
            "goal": goal,
            "delegated_provider": delegated_provider,
            "delegated_model": delegated_model,
            "result": result.summary,
            "sources": result.sources,
        }
        reply = await primary.complete(
            FINALIZER_SYSTEM,
            json.dumps(payload, ensure_ascii=False),
        )
        data = dict(result.data)
        data.update(
            {
                "delegated_provider": delegated_provider,
                "delegated_model": delegated_model,
                "finalized_by": primary.name,
            }
        )
        return (
            AgentResult(
                ok=True,
                summary=reply.text,
                data=data,
                sources=result.sources,
                artifacts=result.artifacts,
            ),
            reply.provider,
            reply.model,
        )

    async def handle(self, message: str, session_id: UUID | None = None):
        sid = self.db.create_session(session_id)
        self.db.add_message(sid, "user", message)
        memories = self.memory.context_text(message)
        history = self.db.recent_messages(sid, limit=10)
        history_text = "\n".join(
            f"{m['role']}: {m['content']}" for m in history[:-1]
        )
        context = (
            f"Relevant memory:\n{memories or '(none)'}\n\n"
            f"Recent conversation:\n{history_text or '(none)'}"
        )

        # The planner always starts from the OpenAI primary brain.
        plan = await self.planner.create(message, context)
        wid = self.db.create_workflow(sid, message, plan.model_dump())
        self.db.audit("workflow.started", {"goal": message, "plan": plan.model_dump()}, wid)

        result, provider, model = await self.workflows.execute(wid, plan, context)
        if result.ok:
            result, provider, model = await self._finalize_with_primary(
                message, result, provider, model, len(plan.tasks)
            )

        self.db.add_message(sid, "assistant", result.summary)
        self.db.audit(
            "workflow.finished",
            {"ok": result.ok, "provider": provider, "model": model},
            wid,
        )
        return {
            "workflow_id": wid,
            "session_id": sid,
            "status": "completed" if result.ok else "failed",
            "message": result.summary,
            "provider": provider,
            "model": model,
            "sources": result.sources,
        }
