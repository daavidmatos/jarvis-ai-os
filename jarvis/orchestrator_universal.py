from __future__ import annotations

from uuid import UUID

from jarvis.browser_assistant import BrowserAssistant
from jarvis.fast_chat import FastChat
from jarvis.internet_assistant import InternetAssistant
from jarvis.missions import mission_store
from jarvis.mobility_assistant import MobilityAssistant
from jarvis.orchestrator import Orchestrator as CoreOrchestrator
from jarvis.permissions import standing_permissions
from jarvis.universal_collaboration_desktop import EnhancedUniversalCollaborationHub
from jarvis.voice_persona import ensure_senhor


class UniversalOrchestrator(CoreOrchestrator):
    """Core orchestrator with collaboration, live internet and low-latency chat routing.

    Direct assistant utilities such as mobility, browser tabs and live research are
    routed before sticky workspaces/missions. This prevents an old blocked task from
    hijacking unrelated commands such as "abra uma nova guia" or "pesquise para mim".
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.collaboration = EnhancedUniversalCollaborationHub(self.router, self.tools)
        self.fast_chat = FastChat(self.router, self.db)
        self.internet = InternetAssistant(self.router, self.tools, self.db)
        self.mobility = MobilityAssistant(self.db)
        self.browser = BrowserAssistant(self.db)

    @staticmethod
    def _mission_followup_like(message: str) -> bool:
        """Return True only for text that plausibly continues an active mission.

        Missions are durable, but they must not turn the whole chat into one giant
        modal state. Explicit approvals, budgets and mission/campaign follow-ups stay
        attached; ordinary conversation and assistant utilities remain independent.
        """
        text = " ".join(message.lower().strip().split())
        exact = {
            "ok", "sim", "pode", "pode sim", "aprovado", "aprovo", "continue",
            "continua", "prossiga", "pode prosseguir", "pode executar",
            "execute", "execute mesmo assim", "faça mesmo assim", "faca mesmo assim",
        }
        if text in exact:
            return True
        markers = (
            "missão", "missao", "campanha", "orçamento", "orcamento", "budget",
            "por dia", "por mês", "por mes", "r$", "reais", "bloqueio", "blocker",
            "aprovar", "aprovação", "aprovacao", "prosseguir", "executar a missão",
            "executar a missao", "essa missão", "essa missao", "essa campanha",
        )
        return any(marker in text for marker in markers)

    def _fast_chat_eligible(self, sid: UUID, message: str) -> bool:
        active_mission = mission_store.latest_for_session(str(sid), active_only=True)
        if active_mission and self._mission_followup_like(message):
            return False
        if self.local_assistant.looks_like_local_request(message):
            return False
        if self.local_assistant.navigation_followup(message):
            return False
        if self.mission_director.looks_like_mission(message):
            return False
        if self.internet.looks_like_request(message):
            return False
        if self.mobility.looks_like_request(message):
            return False
        if self.browser.looks_like_request(message):
            return False

        text = message.lower()
        tool_markers = (
            "pesquise", "pesquisar", "procure na internet", "busque na internet",
            "gmail", "e-mail", "email", "calendário", "calendario", "agenda",
            "google ads", "instagram", "trello", "figma", "blender", "photoshop",
            "illustrator", "after effects", "premiere", "planilha", "google sheets",
            "google docs", "documento", "arquivo", "github", "fuel", "cupom",
            "crie uma imagem", "gere uma imagem", "edite", "publique", "envie",
            "abra", "monitore", "monitorar", "automatize", "execute", "ifood",
            "uber",
        )
        return not any(marker in text for marker in tool_markers)

    def _conversation_context(self, sid: UUID, message: str, location: dict | None) -> str:
        memories = self.memory.context_text(message)
        history = self.db.recent_messages(sid, limit=10)
        history_text = "\n".join(
            f"{m['role']}: {m['content']}" for m in history[:-1]
        )
        permissions = standing_permissions.context_text()
        # Precise coordinates are intentionally not exposed to generic model context.
        # Location-aware assistants receive the ephemeral coordinates directly as tool
        # input and may use them operationally without echoing them back to the user.
        location_text = "available to location-aware tools" if location else "not supplied"
        return (
            f"Relevant memory:\n{memories or '(none)'}\n\n"
            f"Recent conversation:\n{history_text or '(none)'}\n\n"
            f"Standing permissions:\n{permissions}\n\n"
            "Current device location (ephemeral; never memorize):\n"
            f"{location_text}"
        )

    async def _record_direct(self, sid: UUID, message: str, result: dict) -> dict:
        self.db.add_message(sid, "user", message)
        self.db.add_message(sid, "assistant", result["message"])
        return result

    async def handle(
        self,
        message: str,
        session_id: UUID | None = None,
        location: dict | None = None,
    ):
        # Resolve a stable session first so workspaces and normal dialogue persist.
        sid = self.db.create_session(session_id)

        # Assistant utilities outrank stale collaborative/mission context.
        if self.mobility.looks_like_request(message):
            result = await self.mobility.handle(sid, message, location)
            return await self._record_direct(sid, message, result)

        if self.browser.looks_like_request(message):
            result = await self.browser.handle(sid, message)
            return await self._record_direct(sid, message, result)

        if self.internet.looks_like_request(message):
            self.db.add_message(sid, "user", message)
            context = self._conversation_context(sid, message, location)
            result = await self.internet.research(sid, message, context)
            self.db.add_message(sid, "assistant", result["message"])
            return result

        collaborative = await self.collaboration.handle_or_start(str(sid), message)
        if collaborative is None:
            if self._fast_chat_eligible(sid, message):
                self.db.add_message(sid, "user", message)
                context = self._conversation_context(sid, message, location)
                result = await self.fast_chat.reply(sid, message, context)
                self.db.add_message(sid, "assistant", result["message"])
                return result
            return await super().handle(message, sid, location)

        self.db.add_message(sid, "user", message)
        wid = self.db.create_workflow(
            sid,
            message,
            {
                "type": "collaborative_workspace",
                "workspace": collaborative.get("workspace"),
            },
        )
        payload = {
            "message": ensure_senhor(collaborative.get("message") or ""),
            "workspace": collaborative.get("workspace"),
            "actions": collaborative.get("actions") or [],
        }
        self.db.finish_workflow(wid, "completed", payload)
        self.db.audit(
            "workspace.turn",
            {
                "session_id": str(sid),
                "kind": (collaborative.get("workspace") or {}).get("kind"),
            },
            wid,
        )
        self.db.add_message(sid, "assistant", payload["message"])
        return {
            "workflow_id": wid,
            "session_id": sid,
            "status": "completed",
            "message": payload["message"],
            "provider": collaborative.get("provider") or "workspace",
            "model": collaborative.get("model"),
            "sources": [],
            "actions": payload["actions"],
            "workspace": payload["workspace"],
        }
