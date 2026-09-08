from __future__ import annotations

from uuid import UUID

from jarvis.voice_persona import JARVIS_CHAT_SYSTEM, ensure_senhor


class FastChat:
    """Single-model-call path for ordinary conversation.

    The full planner/agent workflow is valuable when tools or multi-step work are needed,
    but it adds avoidable latency to greetings, follow-up questions and normal dialogue.
    """

    def __init__(self, router, db):
        self.router = router
        self.db = db

    async def reply(self, sid: UUID, message: str, context: str) -> dict:
        provider = self.router.primary()
        reply = await provider.complete(
            JARVIS_CHAT_SYSTEM,
            f"Conversation context:\n{context}\n\nUser message:\n{message}",
            temperature=0.2,
        )
        text = ensure_senhor(reply.text)
        wid = self.db.create_workflow(
            sid,
            message,
            {"type": "fast_chat", "provider": reply.provider, "model": reply.model},
        )
        self.db.finish_workflow(
            wid,
            "completed",
            {"message": text, "provider": reply.provider, "model": reply.model},
        )
        self.db.audit(
            "chat.fast",
            {"provider": reply.provider, "model": reply.model},
            wid,
        )
        return {
            "workflow_id": wid,
            "session_id": sid,
            "status": "completed",
            "message": text,
            "provider": reply.provider,
            "model": reply.model,
            "sources": [],
            "actions": [],
        }
