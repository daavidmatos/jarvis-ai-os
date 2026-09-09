from __future__ import annotations

from urllib.parse import quote_plus
from uuid import UUID

from jarvis.browser_assistant import BrowserAssistant
from jarvis.commerce_assistant import CommerceAssistant
from jarvis.content_assistant import ContentAssistant
from jarvis.fast_chat import FastChat
from jarvis.internet_assistant import InternetAssistant
from jarvis.local_assistant import LocalAssistantError, google_places
from jarvis.missions import mission_store
from jarvis.mobility_assistant import MobilityAssistant
from jarvis.orchestrator import Orchestrator as CoreOrchestrator
from jarvis.permissions import standing_permissions
from jarvis.universal_collaboration_desktop import EnhancedUniversalCollaborationHub
from jarvis.voice_persona import ensure_senhor


class UniversalOrchestrator(CoreOrchestrator):
    """Execution-first JARVIS router.

    Concrete assistant actions are resolved before generic model conversation so a
    capable tool is never replaced by an LLM saying it cannot do the task.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.collaboration = EnhancedUniversalCollaborationHub(self.router, self.tools)
        self.fast_chat = FastChat(self.router, self.db)
        self.internet = InternetAssistant(self.router, self.tools, self.db)
        self.mobility = MobilityAssistant(self.db)
        self.browser = BrowserAssistant(self.db)
        self.commerce = CommerceAssistant(self.db)
        self.content = ContentAssistant(self.router, self.db)

    @staticmethod
    def _mission_followup_like(message: str) -> bool:
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
        if self.commerce.looks_like_request(message):
            return False
        if self.content.looks_like_request(message):
            return False

        text = message.lower()
        tool_markers = (
            "pesquise", "pesquisar", "procure na internet", "busque na internet",
            "gmail", "e-mail", "email", "calendário", "calendario", "agenda",
            "google ads", "instagram", "trello", "figma", "blender", "photoshop",
            "illustrator", "after effects", "premiere", "planilha", "google sheets",
            "google docs", "documento", "arquivo", "github", "fuel", "cupom",
            "crie uma imagem", "gere uma imagem", "edite", "publique", "envie",
            "abra", "monitore", "monitorar", "automatize", "execute", "ifood", "uber",
        )
        return not any(marker in text for marker in tool_markers)

    def _conversation_context(self, sid: UUID, message: str, location: dict | None) -> str:
        memories = self.memory.context_text(message)
        history = self.db.recent_messages(sid, limit=10)
        history_text = "\n".join(f"{m['role']}: {m['content']}" for m in history[:-1])
        permissions = standing_permissions.context_text()
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

    async def _local_fallback(self, sid: UUID, message: str) -> dict:
        query = message.strip()
        url = f"https://www.google.com/maps/search/?api=1&query={quote_plus(query)}"
        text = ensure_senhor(
            "O Google Places estruturado ainda não está conectado, então não vou fingir que comparei avaliações. "
            "Vou abrir a busca real no Google Maps agora; depois de conectar o Maps, eu consigo ranquear os lugares por avaliações, volume de reviews, fotos, distância e horário."
        )
        wid = self.db.create_workflow(sid, message, {"type": "local_maps_fallback", "url": url})
        self.db.finish_workflow(wid, "completed", {"message": text, "url": url})
        return {
            "workflow_id": wid,
            "session_id": sid,
            "status": "completed",
            "message": text,
            "provider": "google_maps_handoff",
            "model": None,
            "sources": [],
            "actions": [{"type": "open_url", "label": "ABRIR MAPS", "url": url, "auto": True}],
        }

    async def handle(self, message: str, session_id: UUID | None = None, location: dict | None = None):
        sid = self.db.create_session(session_id)

        if self.mobility.looks_like_request(message):
            return await self._record_direct(sid, message, await self.mobility.handle(sid, message, location))

        if self.commerce.looks_like_request(message):
            return await self._record_direct(sid, message, await self.commerce.handle(sid, message, location))

        if self.content.looks_like_request(message):
            return await self._record_direct(sid, message, await self.content.handle(sid, message))

        if self.browser.looks_like_request(message):
            return await self._record_direct(sid, message, await self.browser.handle(sid, message))

        if self.local_assistant.looks_like_local_request(message):
            if not google_places.status()["configured"]:
                return await self._record_direct(sid, message, await self._local_fallback(sid, message))
            try:
                result = await self.local_assistant.recommend(str(sid), message, location)
            except LocalAssistantError:
                result = await self._local_fallback(sid, message)
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
            {"type": "collaborative_workspace", "workspace": collaborative.get("workspace")},
        )
        payload = {
            "message": ensure_senhor(collaborative.get("message") or ""),
            "workspace": collaborative.get("workspace"),
            "actions": collaborative.get("actions") or [],
        }
        self.db.finish_workflow(wid, "completed", payload)
        self.db.audit(
            "workspace.turn",
            {"session_id": str(sid), "kind": (collaborative.get("workspace") or {}).get("kind")},
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
