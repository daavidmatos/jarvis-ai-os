from fastapi.testclient import TestClient

from jarvis.api import app
from jarvis.auth import OwnerAuth
from jarvis.config import settings


def test_signed_owner_session(monkeypatch):
    monkeypatch.setattr(settings, "jarvis_access_password", "a-strong-test-password")
    monkeypatch.setattr(settings, "jarvis_session_secret", "test-session-secret")
    monkeypatch.setattr(settings, "jarvis_session_days", 1)
    auth = OwnerAuth()
    token = auth.issue_session(now=1_000)
    assert auth.verify_session(token, now=1_100)
    assert not auth.verify_session(token + "x", now=1_100)
    assert not auth.verify_session(token, now=1_000 + 24 * 3600 + 1)


def test_hosted_instance_fails_closed_without_password(monkeypatch):
    monkeypatch.setattr(settings, "app_env", "production")
    monkeypatch.setattr(settings, "jarvis_access_password", None)
    c = TestClient(app)
    assert c.get("/health").status_code == 200
    r = c.get("/v1/setup/status")
    assert r.status_code == 503
    assert r.json()["detail"] == "owner_auth_not_configured"


def test_owner_login_unlocks_private_api(monkeypatch):
    # Development mode keeps the test cookie non-Secure while a configured
    # password still turns the access gate on.
    monkeypatch.setattr(settings, "app_env", "development")
    monkeypatch.setattr(settings, "jarvis_access_password", "correct-horse-battery-staple")
    monkeypatch.setattr(settings, "jarvis_session_secret", "test-secret")
    c = TestClient(app)

    blocked = c.get("/v1/setup/status")
    assert blocked.status_code == 401

    wrong = c.post(
        "/login",
        data={"password": "wrong", "next": "/"},
        follow_redirects=False,
    )
    assert wrong.status_code == 401

    login = c.post(
        "/login",
        data={"password": "correct-horse-battery-staple", "next": "/"},
        follow_redirects=False,
    )
    assert login.status_code == 303
    assert login.headers["location"] == "/"

    unlocked = c.get("/v1/setup/status")
    assert unlocked.status_code == 200
