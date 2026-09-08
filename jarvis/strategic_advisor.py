from __future__ import annotations

import json
import re
from dataclasses import asdict, dataclass
from typing import Any, Literal

from jarvis.router import ModelRouter


StrategicVerdict = Literal["proceed", "adjust", "do_not_recommend"]


@dataclass
class StrategicAssessment:
    verdict: StrategicVerdict
    recommendation: str
    reasons: list[str]
    alternatives: list[str]
    recommended_objective: str | None
    confidence: float
    assumptions: list[str]

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)

    def concise_text(self) -> str:
        if self.verdict == "proceed":
            return self.recommendation.strip()
        lines = [self.recommendation.strip()]
        if self.reasons:
            lines.append("Motivo: " + "; ".join(self.reasons[:3]))
        if self.alternatives:
            lines.append("Melhores opções: " + " | ".join(self.alternatives[:3]))
        return "\n".join(x for x in lines if x)


ADVISOR_SYSTEM = """You are JARVIS Strategic Advisor, an independent decision-quality layer.
Your job is not to agree with the user. Evaluate whether the proposed idea is strategically sensible NOW using the available company context, memory, connected-data summaries and conversation.

Be decisive, commercially literate, evidence-aware and concise. Challenge weak premises. Do not manufacture facts or pretend certainty. If evidence is incomplete, distinguish assumptions from known context, but do not use missing data as an excuse for unnecessary questions; prefer a reversible research/test step.

Evaluate the idea on the dimensions that actually matter: objective fit, timing, expected upside, opportunity cost, execution complexity, brand/customer fit, economics/budget, measurability, reversibility and downside risk. Do not mechanically enumerate every dimension.

Return ONLY valid JSON:
{
  "verdict":"proceed|adjust|do_not_recommend",
  "recommendation":"direct recommendation in at most 2 short sentences",
  "reasons":["up to 3 concrete reasons"],
  "alternatives":["0 to 3 better options, specific and actionable"],
  "recommended_objective":"reframed objective if verdict=adjust, otherwise null",
  "confidence":0.0,
  "assumptions":["material assumptions only"]
}

Decision rules:
- proceed: the idea is sensible enough to execute, even if execution details should improve.
- adjust: the underlying goal is good but the proposed approach/timing/channel should materially change. Provide a better objective JARVIS can execute instead.
- do_not_recommend: expected downside/opportunity cost is materially worse than plausible upside. Do not silently execute it.
- Never reject merely because success is uncertain. Marketing is probabilistic; prefer controlled tests when appropriate.
- Never flatter the user's idea. Never be contrarian for style.
- Keep reasons concrete and short.
"""


class StrategicAdvisor:
    def __init__(self, router: ModelRouter):
        self.router = router

    async def assess(self, idea: str, context: str = "") -> StrategicAssessment:
        provider = self.router.primary()
        reply = await provider.complete(
            ADVISOR_SYSTEM,
            f"Idea/request to assess:\n{idea}\n\nAvailable context:\n{context or '(none)'}",
        )
        raw = reply.text.strip()
        match = re.search(r"\{.*\}", raw, re.S)
        data = json.loads(match.group(0) if match else raw)

        verdict = str(data.get("verdict") or "proceed").strip().lower()
        if verdict not in {"proceed", "adjust", "do_not_recommend"}:
            verdict = "proceed"
        confidence = data.get("confidence", 0.5)
        try:
            confidence = min(max(float(confidence), 0.0), 1.0)
        except (TypeError, ValueError):
            confidence = 0.5

        recommended = data.get("recommended_objective")
        if verdict != "adjust":
            recommended = None

        return StrategicAssessment(
            verdict=verdict,  # type: ignore[arg-type]
            recommendation=str(data.get("recommendation") or "A ideia é executável."),
            reasons=[str(x) for x in (data.get("reasons") or [])][:3],
            alternatives=[str(x) for x in (data.get("alternatives") or [])][:3],
            recommended_objective=str(recommended) if recommended else None,
            confidence=confidence,
            assumptions=[str(x) for x in (data.get("assumptions") or [])][:5],
        )
