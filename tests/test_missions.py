from jarvis.config import settings
from jarvis.missions import MissionEnvelope, MissionStatus, mission_store
from jarvis.permissions import standing_permissions
from jarvis.tools.registry import ToolRegistry


def _isolate(monkeypatch, tmp_path):
    monkeypatch.setattr(settings, "secrets_path", str(tmp_path / "secrets.json"))


def test_mission_approval_authorizes_publish_tool(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    mission = mission_store.create(
        title="UGC campaign",
        objective="Run a UGC campaign",
        envelope=MissionEnvelope(
            objective="Run a UGC campaign",
            channels=["instagram"],
            allow_publish=True,
        ),
        plan=[{"id": "m1", "phase": "execute", "action": "publish"}],
    )
    mission_store.approve(mission.id)
    registry = ToolRegistry()
    names = {spec["name"] for spec in registry.mission_specs(mission.id)}
    assert "instagram.publish_photo" in names
    assert mission_store.get(mission.id).status == MissionStatus.APPROVED.value


def test_mission_spend_ceiling_is_enforced(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    mission = mission_store.create(
        title="Ads",
        objective="Run Google Ads",
        envelope=MissionEnvelope(
            objective="Run Google Ads",
            channels=["google_ads"],
            daily_budget_limit=50.0,
            total_budget_limit=500.0,
            allow_spend=True,
        ),
        plan=[],
    )
    mission_store.approve(mission.id)
    registry = ToolRegistry()
    tool = registry.tools["google_ads.create_search_campaign"]
    allowed, _ = registry._mission_authority(
        tool, mission.id, {"daily_budget_brl": 40.0}
    )
    denied, reason = registry._mission_authority(
        tool, mission.id, {"daily_budget_brl": 60.0}
    )
    assert allowed is True
    assert denied is False
    assert "exceeds" in reason


def test_standing_permission_can_supply_marketing_limits(monkeypatch, tmp_path):
    _isolate(monkeypatch, tmp_path)
    standing_permissions.create(
        name="Fuel marketing",
        channels=["instagram", "google_ads"],
        allow_publish=True,
        allow_spend=True,
        max_daily_spend=75.0,
        max_total_spend=1000.0,
    )
    effective = standing_permissions.effective(["google_ads"])
    assert effective["allow_publish"] is True
    assert effective["allow_spend"] is True
    assert effective["max_daily_spend"] == 75.0
