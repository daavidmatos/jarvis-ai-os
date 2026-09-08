from jarvis.config import settings
from jarvis.schemas import RiskLevel

class PolicyEngine:
    def can_execute(self, risk: RiskLevel, approved: bool=False) -> bool:
        if risk == RiskLevel.CRITICAL:
            return False
        if risk == RiskLevel.HIGH:
            return approved
        if risk == RiskLevel.MEDIUM:
            return settings.allow_medium_risk_tools
        return True
