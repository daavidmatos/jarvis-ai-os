import stat

from jarvis.config import settings
from jarvis.credentials import credential_store


def test_credential_store_roundtrip(tmp_path, monkeypatch):
    path = tmp_path / "jarvis" / "secrets.json"
    monkeypatch.setattr(settings, "secrets_path", str(path))
    monkeypatch.setattr(settings, "openai_api_key", None)

    credential_store.set("openai", "sk-test-" + ("x" * 40))
    assert credential_store.get("openai").startswith("sk-test-")
    assert stat.S_IMODE(path.stat().st_mode) == 0o600

    assert credential_store.delete("openai") is True
    assert credential_store.get("openai") is None
