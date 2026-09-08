from fastapi.testclient import TestClient

from jarvis.api import app, jarvis
from jarvis.config import settings


def test_marketing_tools_are_registered():
    names = set(jarvis.tools.tools)
    expected = {
        "instagram.status",
        "instagram.tagged_media",
        "instagram.publish_photo",
        "google_ads.status",
        "google_ads.performance",
        "google_ads.create_search_campaign",
        "google_ads.set_campaign_status",
        "creative.generate_image",
        "fuel.status",
        "fuel.recent_orders",
        "fuel.sales_summary",
        "fuel.create_coupon",
    }
    assert expected.issubset(names)


def test_high_risk_marketing_tools_not_globally_autonomous():
    autonomous = {item["name"] for item in jarvis.tools.autonomous_specs()}
    assert "instagram.publish_photo" not in autonomous
    assert "google_ads.create_search_campaign" not in autonomous
    assert "fuel.create_coupon" not in autonomous
    assert "instagram.tagged_media" in autonomous
    assert "google_ads.performance" in autonomous


def test_integration_status_endpoint():
    client = TestClient(app)
    response = client.get("/v1/integrations/status")
    assert response.status_code == 200
    data = response.json()
    expected = {"google_workspace", "places", "google_ads", "instagram", "fuel", "desktop_bridge"}
    assert expected.issubset(set(data))
    assert "configured" in data["places"]
    assert "connected" in data["desktop_bridge"]


def test_meta_webhook_ingests_event_without_signature_when_secret_unset(monkeypatch):
    monkeypatch.setattr(settings, "meta_app_secret", None)
    client = TestClient(app)
    response = client.post(
        "/v1/webhooks/meta/instagram",
        json={"object": "instagram", "entry": [{"id": "123", "changes": []}]},
    )
    assert response.status_code == 200
    assert response.json()["ok"] is True
