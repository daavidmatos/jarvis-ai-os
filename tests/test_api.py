from fastapi.testclient import TestClient

from jarvis.api import app


def test_health():
    c = TestClient(app)
    r = c.get("/health")
    assert r.status_code == 200
    assert r.json()["status"] == "ok"
    assert r.json()["primary_provider"] == "openai"


def test_setup_status_does_not_expose_secrets():
    c = TestClient(app)
    r = c.get("/v1/setup/status")
    assert r.status_code == 200
    payload = r.json()
    assert "ready" in payload
    assert payload["primary"]["provider"] == "openai"
    assert "api_key" not in str(payload).lower()
