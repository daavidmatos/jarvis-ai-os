from __future__ import annotations

import json
import re
from typing import Any

from jarvis.missions import Mission, MissionEnvelope, mission_store
from jarvis.permissions import standing_permissions
from jarvis.router import ModelRouter


MISSION_SYSTEM = """You are JARVIS Mission Director.
Turn a high-level user objective into an autonomous mission proposal.
Prefer decisions over questions. Ask only for genuinely blocking information that cannot be inferred safely from memory, connected data, web research, standing permissions, or reversible defaults.
Return ONLY valid JSON:
{
  "title":"short title",
  "objective":"normalized objective",
  "channels":["channel"],
  "blockers":["only real blockers"],
  "daily_budget_limit":null,
  "total_budget_limit":null,
  "currency":"BRL",
  "allow_publish":false,
  "allow_external_messages":false,
  "allow_spend":false,
  "allow_commerce":false,
  "plan":[
    {"id":"m1","phase":"understand|design|produce|execute|monitor|optimize|report","action":"...","autonomous":true,"requires_approval":false}
  ],
  "approval_summary":"one concise approval summary"
}
Rules:
- Research, analysis, drafting, asset generation, and reversible preparation should be autonomous.
- If the user asked JARVIS to execute/publish/run a campaign, the proposal may request publish/external-message/commerce authority; the mission approval is the user's one-time authorization for that mission.
- Paid advertising may request spend authority only when a numeric daily or total ceiling is known from the request, memory, or standing permissions. Otherwise budget is a blocker.
- Never invent spend authority or a budget.
- Keep blockers minimal. Do not ask about details JARVIS can decide itself.
- Build a complete lifecycle: understand -> design -> produce -> execute -> monitor -> optimize -> report when relevant.
"""

FOLLOWUP_SYSTEM = """You update a blocked JARVIS mission from a user's follow-up.
Extract only information the user actually provided or explicitly authorized. Return ONLY JSON:
{
 "blockers":[],
 "daily_budget_limit":null,
 "total_budget_limit":null,
 "allow_publish":null,
 "allow_external_messages":null,
 "allow_spend":null,
 "allow_commerce":null,
 "currency":null,
 "approve_now":false,
 "summary":"short response"
}
If the user says OK/approved/go ahead and all blockers can now be resolved, set approve_now=true. Never infer a monetary limit that was not stated or already authorized."""


class MissionDirector:
    def __init__(self, router: ModelRouter):
        self.router = router

    @staticmethod
    def looks_like_mission(message: str) -> bool:
        text = message.lower()
        mission_markers = [
            "campanha", "campaign", "estratégia", "strategy", "projeto",
            "monitore", "monitorar", "cuide", "gerencie", "administre",
            "execute", "executar", "crie uma campanha", "faça uma campanha",
            "google ads", "instagram", "marketing", "lançamento", "launch",
        ]
        return any(marker in text for marker in mission_markers)

    async def propose(
        self, objective: str, context: str = "", session_id: str | None = None
    ) -> dict[str, Any]:
        provider = self.router.primary()
        permission_context = standing_permissions.context_text()
        reply = await provider.complete(
            MISSION_SYSTEM,
            f"User objective:\n{objective}\n\nKnown context:\n{context or '(none)'}\n\nStanding permissions:\n{permission_context}",
        )
        raw = reply.text.strip()
        match = re.search(r"\{.*\}", raw, re.S)
        data = json.loads(match.group(0) if match else raw)
        channels = [str(x).lower() for x in data.get("channels", [])]
        effective = standing_permissions.effective(channels)

        daily = data.get("daily_budget_limit")
        total = data.get("total_budget_limit")
        if daily is None:
            daily = effective.get("max_daily_spend")
        if total is None:
            total = effective.get("max_total_spend")

        envelope = MissionEnvelope(
            objective=data.get("objective") or objective,
            channels=channels,
            daily_budget_limit=daily,
            total_budget_limit=total,
            currency=str(data.get("currency") or "BRL"),
            allow_reversible_changes=True,
            allow_publish=bool(data.get("allow_publish", False) or effective.get("allow_publish")),
            allow_external_messages=bool(
                data.get("allow_external_messages", False)
                or effective.get("allow_external_messages")
            ),
            allow_spend=bool(data.get("allow_spend", False) or effective.get("allow_spend")),
            allow_commerce=bool(data.get("allow_commerce", False) or effective.get("allow_commerce")),
        )

        blockers = [str(x) for x in data.get("blockers", [])]
        if envelope.allow_spend and envelope.daily_budget_limit is None and envelope.total_budget_limit is None:
            blockers.append("Definir um teto de orçamento para mídia paga.")
        blockers = list(dict.fromkeys(blockers))

        mission = mission_store.create(
            title=str(data.get("title") or "Autonomous mission"),
            objective=envelope.objective,
            envelope=envelope,
            plan=list(data.get("plan") or []),
            blockers=blockers,
            session_id=session_id,
        )
        return {
            "mission": mission,
            "approval_summary": str(data.get("approval_summary") or ""),
            "provider": reply.provider,
            "model": reply.model,
        }

    async def apply_followup(
        self, mission: Mission, message: str, context: str = ""
    ) -> dict[str, Any]:
        provider = self.router.primary()
        reply = await provider.complete(
            FOLLOWUP_SYSTEM,
            json.dumps(
                {
                    "mission": {
                        "title": mission.title,
                        "objective": mission.objective,
                        "blockers": mission.blockers,
                        "envelope": mission.envelope,
                    },
                    "user_followup": message,
                    "context": context,
                },
                ensure_ascii=False,
            ),
        )
        raw = reply.text.strip()
        match = re.search(r"\{.*\}", raw, re.S)
        data = json.loads(match.group(0) if match else raw)

        changes = {}
        for key in (
            "daily_budget_limit",
            "total_budget_limit",
            "allow_publish",
            "allow_external_messages",
            "allow_spend",
            "allow_commerce",
            "currency",
        ):
            if data.get(key) is not None:
                changes[key] = data[key]
        if changes:
            mission = mission_store.update_envelope(mission.id, **changes)
        blockers = [str(x) for x in data.get("blockers", mission.blockers)]
        mission = mission_store.replace_blockers(mission.id, blockers)
        return {
            "mission": mission,
            "approve_now": bool(data.get("approve_now", False)) and not blockers,
            "summary": str(data.get("summary") or ""),
            "provider": reply.provider,
            "model": reply.model,
        }
