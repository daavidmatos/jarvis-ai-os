import pytest

from jarvis.config import settings
from jarvis.credentials import credential_store
from jarvis.router import ModelRouter, PrimaryAIUnavailable


def test_primary_requires_openai(tmp_path, monkeypatch):
    monkeypatch.setattr(settings, "secrets_path", str(tmp_path / "secrets.json"))
    monkeypatch.setattr(settings, "openai_api_key", None)
    monkeypatch.setattr(settings, "allow_local_fallback", False)

    router = ModelRouter()
    assert credential_store.get("openai") is None
    with pytest.raises(PrimaryAIUnavailable):
        router.primary()
