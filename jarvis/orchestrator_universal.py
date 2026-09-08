from __future__ import annotations

import json
from uuid import UUID

from jarvis.fast_chat import FastChat
from jarvis.missions import mission_store
from jarvis.orchestrator import Orchestrator as CoreOrchestrator
from jarvis.permissions import standing_permissions
from jarvis.universal_collaboration_desktop import EnhancedUniversalCollaborationHub
from jarvis.voice_persona import ensure_senhor


class UniversalOrchestrator(CoreOrchestrator):
    """Core orchestrator with collaboration and low-latency chat routing.

    Collaborative requests are routed before Mission mode. Ordinary conversation
    skips the planner/agent DAG and uses a single primary-model call, while requests
    that need tools, local search, missions or external applications still use the
    full orchestration stack.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.collaboration = EnhancedUniversalCollaborationHub(self.router, self.tools)
        self.fast_chat = FastChat(self.router, self.db)

    def _fast_chat_eligible(self, sid: UUID, message: str) -> bool:
        if mission_store.latest_for_session(str(sid), active_only=True):
            return False
        if self.local_assistant.looks_like_local_request(message):
            return False
        if self.local_assistant.navigation_followup(message):
            return False
        if self.mission_director.looks_like_mission(message):
            return False

        text = message.lower()
        tool_markers = (
            "pesquise", "pesquisar", "procure na internet", "busque na internet",
            "gmail", "e-mail", "email", "calendário", "calendario", "agenda",
            "google ads", "instagram", "trello", "figma", "blender", "photoshop",
            "illustrator", "after effects", "premiere", "planilha", "google sheets",
            "google docs", "documento", "arquivo", "github", "fuel", "cupom",
            "crie uma imagem", "gere uma imagem", "edite", "publique", "envie",
            "abra", "monitore", "monitorar", "automatize", "execute",
        )
        return not any(marker in text for marker in tool_markers)

    def _conversation_context(self, sid: UUID, message: str, location: dict | None) -> str:
        memories = self.memory.context_text(message)
        history = self.db.recent_messages(sid, limit=10)
        history_text = "\n".join(
            f"{m['role']}: {m['content']}" for m in history[:-1]
        )
        permissions = standing_permissions.context_text()
        location_text = json.dumps(location, ensure_ascii=False) if location else "(not supplied)"
        return (
            f"Relevant memory:\n{memories or '(none)'}\n\n"
            f"Recent conversation:\n{history_text or '(none)'}\n\n"
            f"Standing permissions:\n{permissions}\n\n"
            "Current device location (ephemeral; never memorize):\n"
            f"{location_text}"
        )

    async def handle(
        self,
        message: str,
        session_id: UUID | None = None,
        location: dict | None = None,
    ):
        # Resolve a stable session first so workspaces and normal dialogue persist.
        sid = self.db.create_session(session_id)
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
