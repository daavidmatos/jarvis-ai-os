from __future__ import annotations

import json
import re
from typing import Any

from jarvis.missions import MissionEnvelope, mission_store
from jarvis.router import ModelRouter


MISSION_SYSTEM = """You are JARVIS Mission Director.
Turn a high-level user objective into an autonomous mission proposal.
Prefer decisions over questions. Ask only for genuinely blocking information that cannot be inferred safely from memory, connected data, web research or reversible defaults.
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
  "plan":[
    {"id":"m1","phase":"understand|design|produce|execute|monitor|optimize|report","action":"...","autonomous":true,"requires_approval":false}
  ],
  "approval_summary":"one concise approval summary"
}
Budget is a blocker for paid advertising only when neither the request nor known authorization provides a spend ceiling. Do not invent spend authority. External publishing, customer messages and paid spend default to false unless explicitly authorized in the user's request/context. Preparation, research, analysis and drafts should be autonomous.
"""


class MissionDirector:
    def __init__(self, router: ModelRouter):
        self.router = router

    async def propose(self, objective: str, context: str = "") -> dict[str, Any]:
        provider = self.router.primary()
        reply = await provider.complete(
            MISSION_SYSTEM,
            f"User objective:\n{objective}\n\nKnown context and standing permissions:\n{context or '(none)'}",
        )
        raw = reply.text.strip()
        match = re.search(r"\{.*\}", raw, re.S)
        data = json.loads(match.group(0) if match else raw)
        envelope = MissionEnvelope(
            objective=data.get("objective") or objective,
            channels=[str(x) for x in data.get("channels", [])],
            daily_budget_limit=data.get("daily_budget_limit"),
            total_budget_limit=data.get("total_budget_limit"),
            currency=str(data.get("currency") or "BRL"),
            allow_reversible_changes=True,
            allow_publish=bool(data.get("allow_publish", False)),
            allow_external_messages=bool(data.get("allow_external_messages", False)),
            allow_spend=bool(data.get("allow_spend", False)),
        )
        mission = mission_store.create(
            title=str(data.get("title") or "Autonomous mission"),
            objective=envelope.objective,
            envelope=envelope,
            plan=list(data.get("plan") or []),
            blockers=[str(x) for x in data.get("blockers", [])],
        )
        return {
            "mission": mission,
            "approval_summary": str(data.get("approval_summary") or ""),
            "provider": reply.provider,
            "model": reply.model,
        }
