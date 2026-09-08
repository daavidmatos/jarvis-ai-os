from __future__ import annotations

from uuid import UUID

from jarvis.orchestrator import Orchestrator as CoreOrchestrator
from jarvis.universal_collaboration_desktop import EnhancedUniversalCollaborationHub


class UniversalOrchestrator(CoreOrchestrator):
    """Core orchestrator with collaboration routed ahead of Mission mode.

    This prevents phrases such as "vamos criar" from being mistaken for permission
    to autonomously execute a whole project. When no collaborative workspace is
    active or requested, behavior falls through unchanged to the core orchestrator.
    """

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.collaboration = EnhancedUniversalCollaborationHub(self.router, self.tools)

    async def handle(
        self,
        message: str,
        session_id: UUID | None = None,
        location: dict | None = None,
    ):
        # Resolve a stable session first so the visual workbench can persist across
        # turns. CoreOrchestrator reuses this same id if collaboration does not match.
        sid = self.db.create_session(session_id)
        collaborative = await self.collaboration.handle_or_start(str(sid), message)
        if collaborative is None:
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
            "message": collaborative.get("message") or "",
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
