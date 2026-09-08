import json
import os
from pathlib import Path

from jarvis.config import settings


_PROVIDER_FIELDS = {
    "openai": "openai_api_key",
    "anthropic": "anthropic_api_key",
    "google": "google_api_key",
}


class CredentialStore:
    """Small local credential store for the single-user MVP.

    Environment variables win over this file. The file is created with mode 0600
    inside a 0700 directory and must never be committed to Git.
    """

    @property
    def path(self) -> Path:
        return settings.secrets_file

    def _read(self) -> dict[str, str]:
        path = self.path
        if not path.exists():
            return {}
        try:
            data = json.loads(path.read_text(encoding="utf-8"))
        except (json.JSONDecodeError, OSError):
            return {}
        return {str(k): str(v) for k, v in data.items() if isinstance(v, str)}

    def get(self, provider: str) -> str | None:
        field = _PROVIDER_FIELDS.get(provider)
        if not field:
            return None
        configured = getattr(settings, field, None)
        if configured:
            return str(configured).strip() or None
        return self._read().get(provider)

    def set(self, provider: str, api_key: str) -> None:
        if provider not in _PROVIDER_FIELDS:
            raise ValueError(f"Unsupported provider: {provider}")
        key = api_key.strip()
        if len(key) < 20:
            raise ValueError("API key is too short")

        path = self.path
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(path.parent, 0o700)
        except OSError:
            pass

        data = self._read()
        data[provider] = key
        tmp = path.with_suffix(path.suffix + ".tmp")
        tmp.write_text(json.dumps(data, indent=2), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, path)
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass

    def delete(self, provider: str) -> bool:
        if provider not in _PROVIDER_FIELDS:
            raise ValueError(f"Unsupported provider: {provider}")
        data = self._read()
        existed = provider in data
        data.pop(provider, None)
        path = self.path
        if not data:
            if path.exists():
                path.unlink()
            return existed
        path.write_text(json.dumps(data, indent=2), encoding="utf-8")
        try:
            os.chmod(path, 0o600)
        except OSError:
            pass
        return existed

    def configured(self, provider: str) -> bool:
        return bool(self.get(provider))


credential_store = CredentialStore()
