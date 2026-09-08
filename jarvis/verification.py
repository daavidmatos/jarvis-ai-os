from jarvis.schemas import AgentResult

class VerificationEngine:
    def verify(self, result: AgentResult) -> tuple[bool,str]:
        if not result.ok: return False,"agent reported failure"
        if not result.summary.strip(): return False,"empty result"
        return True,"ok"
