import json
from uuid import UUID

from jarvis.agents.manager import AgentManager
from jarvis.config import settings
from jarvis.db import Database
from jarvis.memory import MemoryEngine
from jarvis.mission_director import MissionDirector
from jarvis.mission_executor import MissionExecutor
from jarvis.missions import MissionStatus, mission_store
from jarvis.permissions import standing_permissions
from jarvis.planner import Planner
from jarvis.router import ModelRouter
from jarvis.schemas import AgentResult
from jarvis.strategic_advisor import StrategicAdvisor
from jarvis.tools.registry import ToolRegistry
from jarvis.workflows import WorkflowEngine


FINALIZER_SYSTEM = """You are JARVIS Core, powered by OpenAI.
You are the user's primary intelligence and final decision/synthesis layer.
A specialist model may have performed a delegated subtask. Use its output as evidence,
not as unquestionable truth. Preserve useful source references and resolve contradictions.
Use independent judgment: do not assume the user's premise or proposed approach is good.
If there is a materially better option, say so directly and briefly, explain why, and offer the
best alternative. Do not be contrarian for style. Keep the answer concise and operational.
Never claim actions that were not actually executed."""

MISSION_FINALIZER_SYSTEM = """You are JARVIS Mission Director reporting mission execution.
Be concise and operational. State what was actually completed, what is now being monitored,
and any blocker that genuinely needs the user. Never claim publication, spend, messages, or
external mutations unless the tool logs show they succeeded."""

STRATEGIC_OVERRIDE_BLOCKER = (
    "Confirmar explicitamente que deseja prosseguir apesar da recomendação estratégica do JARVIS."
)


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
        self.strategic_advisor = StrategicAdvisor(self.router)
        self.mission_director = MissionDirector(self.router)
        self.mission_executor = MissionExecutor(self.router, self.tools)

    async def _finalize_with_primary(
        self,
        goal: str,
        result: AgentResult,
        delegated_provider: str | None,
        delegated_model: str | None,
        task_count: int,
    ) -> tuple[AgentResult, str | None, str | None]:
        primary = self.router.primary()
        should_finalize = result.ok and (
            task_count > 1 or delegated_provider != primary.name
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

    @staticmethod
    def _approval_like(message: str) -> bool:
        normalized = message.strip().lower()
        exact = {
            "ok", "sim", "pode", "pode executar", "execute", "aprovado",
            "aprovo", "vai", "pode fazer", "pode começar", "comece",
            "go", "go ahead", "approved",
        }
        return normalized in exact or any(
            phrase in normalized
            for phrase in ("pode executar", "pode começar", "está aprovado", "eu aprovo")
        )

    @staticmethod
    def _strategic_override_like(message: str) -> bool:
        normalized = message.strip().lower()
        phrases = (
            "execute mesmo assim",
            "faça mesmo assim",
            "faca mesmo assim",
            "prossiga mesmo assim",
            "quero prosseguir mesmo assim",
            "quero fazer mesmo assim",
            "ignore a recomendação",
            "ignore a recomendacao",
            "assumo o risco e pode executar",
        )
        return any(phrase in normalized for phrase in phrases)

    @staticmethod
    def _has_strategic_blocker(blockers: list[str]) -> bool:
        return any("recomendação estratégica" in b.lower() for b in blockers)

    async def _mission_response(
        self,
        sid: UUID,
        message: str,
        context: str,
    ) -> dict | None:
        pending = mission_store.latest_for_session(str(sid), active_only=True)

        if pending and pending.status == MissionStatus.BLOCKED.value:
            if self._has_strategic_blocker(pending.blockers):
                if self._strategic_override_like(message):
                    remaining = [
                        b for b in pending.blockers
                        if "recomendação estratégica" not in b.lower()
                    ]
                    pending = mission_store.replace_blockers(pending.id, remaining)
                    if not remaining:
                        mission_store.approve(pending.id)
                        return await self._execute_mission_workflow(sid, message, pending.id)
                elif self._approval_like(message):
                    wid = self.db.create_workflow(
                        sid,
                        message,
                        {"type": "strategic_override_required", "mission_id": pending.id},
                    )
                    text = (
                        "Eu não recomendo essa execução nas condições atuais. "
                        "Se você quiser assumir essa decisão mesmo assim, diga explicitamente: "
                        "'execute mesmo assim'."
                    )
                    self.db.finish_workflow(
                        wid, "completed", {"mission_id": pending.id, "message": text}
                    )
                    return {
                        "workflow_id": wid,
                        "session_id": sid,
                        "status": "completed",
                        "message": text,
                        "provider": "openai",
                        "model": None,
                        "sources": [],
                    }

            update = await self.mission_director.apply_followup(pending, message, context)
            mission = update["mission"]
            if update["approve_now"]:
                mission = mission_store.approve(mission.id)
                return await self._execute_mission_workflow(sid, message, mission.id)
            wid = self.db.create_workflow(
                sid,
                message,
                {"type": "mission_followup", "mission_id": mission.id},
            )
            if mission.blockers:
                text = update["summary"] or (
                    "Ainda preciso apenas de: " + "; ".join(mission.blockers)
                )
            else:
                text = update["summary"] or (
                    f"Missão '{mission.title}' pronta. Diga OK para eu executar dentro do escopo aprovado."
                )
            self.db.finish_workflow(wid, "completed", {"mission_id": mission.id, "message": text})
            return {
                "workflow_id": wid,
                "session_id": sid,
                "status": "completed",
                "message": text,
                "provider": update["provider"],
                "model": update["model"],
                "sources": [],
            }

        if (
            pending
            and pending.status == MissionStatus.APPROVAL_REQUIRED.value
            and self._approval_like(message)
        ):
            mission_store.approve(pending.id)
            return await self._execute_mission_workflow(sid, message, pending.id)

        if self.mission_director.looks_like_mission(message):
            assessment = await self.strategic_advisor.assess(message, context)
            strategy_context = (
                context
                + "\n\nStrategic assessment:\n"
                + json.dumps(assessment.to_dict(), ensure_ascii=False)
            )
            objective = (
                assessment.recommended_objective
                if assessment.verdict == "adjust" and assessment.recommended_objective
                else message
            )
            proposal = await self.mission_director.propose(
                objective,
                strategy_context,
                session_id=str(sid),
            )
            mission = proposal["mission"]
            mission_store.append_log(
                mission.id, "strategy.assessed", assessment.to_dict()
            )

            if assessment.verdict == "do_not_recommend":
                mission = mission_store.add_blocker(mission.id, STRATEGIC_OVERRIDE_BLOCKER)

            wid = self.db.create_workflow(
                sid,
                message,
                {
                    "type": "mission_proposal",
                    "mission_id": mission.id,
                    "strategic_verdict": assessment.verdict,
                },
            )

            advice = assessment.concise_text()
            if assessment.verdict == "do_not_recommend":
                text = (
                    f"{advice}\n\nEu não recomendo executar isso agora. "
                    "Se quiser prosseguir apesar da recomendação, diga: 'execute mesmo assim'."
                )
                other_blockers = [
                    b for b in mission.blockers if b != STRATEGIC_OVERRIDE_BLOCKER
                ]
                if other_blockers:
                    text += "\nTambém falta: " + "; ".join(other_blockers)
            elif mission.blockers:
                prefix = f"{advice}\n\n" if advice else ""
                text = (
                    prefix
                    + f"Missão '{mission.title}' estruturada. Preciso apenas de: "
                    + "; ".join(mission.blockers)
                )
            else:
                scope = proposal["approval_summary"] or "Plano completo preparado."
                prefix = f"{advice}\n\n" if advice else ""
                if assessment.verdict == "adjust":
                    prefix += "Ajustei a missão para a alternativa que considero mais forte.\n\n"
                text = (
                    prefix
                    + f"{scope}\n\nSe estiver de acordo, diga OK. Depois disso eu executo a missão "
                    "dentro desse escopo sem pedir confirmação a cada etapa."
                )

            self.db.finish_workflow(
                wid,
                "completed",
                {
                    "mission_id": mission.id,
                    "status": mission.status,
                    "strategic_assessment": assessment.to_dict(),
                    "message": text,
                },
            )
            return {
                "workflow_id": wid,
                "session_id": sid,
                "status": "completed",
                "message": text,
                "provider": proposal["provider"],
                "model": proposal["model"],
                "sources": [],
            }
        return None

    async def _execute_mission_workflow(
        self, sid: UUID, trigger_message: str, mission_id: str
    ) -> dict:
        wid = self.db.create_workflow(
            sid,
            trigger_message,
            {"type": "mission_execution", "mission_id": mission_id},
        )
        self.db.audit("mission.execution.started", {"mission_id": mission_id}, wid)
        result = await self.mission_executor.execute(mission_id)
        mission = result.get("mission")
        primary = self.router.primary()
        payload = {
            "mission_id": mission_id,
            "status": getattr(mission, "status", None),
            "blockers": getattr(mission, "blockers", []),
            "outputs": result.get("outputs", []),
            "ok": result.get("ok"),
            "error": result.get("error"),
        }
        reply = await primary.complete(
            MISSION_FINALIZER_SYSTEM,
            json.dumps(payload, ensure_ascii=False),
        )
        status = "completed" if result.get("ok") or result.get("blocked") else "failed"
        self.db.finish_workflow(wid, status, {"mission_id": mission_id, **payload})
        self.db.audit("mission.execution.finished", payload, wid)
        return {
            "workflow_id": wid,
            "session_id": sid,
            "status": status,
            "message": reply.text,
            "provider": reply.provider,
            "model": reply.model,
            "sources": [],
        }

    async def handle(self, message: str, session_id: UUID | None = None):
        sid = self.db.create_session(session_id)
        self.db.add_message(sid, "user", message)
        memories = self.memory.context_text(message)
        history = self.db.recent_messages(sid, limit=10)
        history_text = "\n".join(
            f"{m['role']}: {m['content']}" for m in history[:-1]
        )
        permissions = standing_permissions.context_text()
        context = (
            f"Relevant memory:\n{memories or '(none)'}\n\n"
            f"Recent conversation:\n{history_text or '(none)'}\n\n"
            f"Standing permissions:\n{permissions}"
        )

        mission_response = await self._mission_response(sid, message, context)
        if mission_response is not None:
            self.db.add_message(sid, "assistant", mission_response["message"])
            return mission_response

        # Normal single-turn workflow: planner always starts from the OpenAI primary brain.
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
