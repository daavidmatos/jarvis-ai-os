from jarvis.policy import PolicyEngine
from jarvis.schemas import RiskLevel

def test_policy():
    p=PolicyEngine()
    assert p.can_execute(RiskLevel.LOW)
    assert not p.can_execute(RiskLevel.HIGH)
    assert p.can_execute(RiskLevel.HIGH,approved=True)
    assert not p.can_execute(RiskLevel.CRITICAL,approved=True)
