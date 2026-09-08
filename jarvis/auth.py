from __future__ import annotations

import base64
import hashlib
import hmac
import os
import secrets
import time
from collections import defaultdict, deque

from jarvis.config import settings


COOKIE_NAME = "jarvis_owner"


class OwnerAuth:
    """Single-owner authentication for the personal JARVIS deployment.

    The owner password stays in the deployment environment. Browser sessions use a
    signed, HttpOnly cookie; the password itself is never written to a cookie or
    persisted by JARVIS.
    """

    def __init__(self) -> None:
        self._attempts: dict[str, deque[float]] = defaultdict(deque)

    @property
    def configured(self) -> bool:
        return bool((settings.jarvis_access_password or "").strip())

    @property
    def hosted(self) -> bool:
        # Render exposes one or both of these variables. APP_ENV=production is the
        # explicit portable switch for any other host.
        return (
            settings.app_env.lower() != "development"
            or bool(os.getenv("RENDER"))
            or bool(os.getenv("RENDER_SERVICE_ID"))
            or bool(os.getenv("RENDER_EXTERNAL_URL"))
        )

    @property
    def required(self) -> bool:
        # If a password is configured locally, honor it there too. Hosted instances
        # fail closed even before the password is configured.
        return self.configured or self.hosted

    def _key(self) -> bytes:
        material = (settings.jarvis_session_secret or settings.jarvis_access_password or "").strip()
        return hashlib.sha256(material.encode("utf-8")).digest()

    def check_password(self, candidate: str) -> bool:
        expected = (settings.jarvis_access_password or "").strip()
        if not expected:
            return False
        return secrets.compare_digest(candidate, expected)

    def can_attempt(self, client_id: str, now: float | None = None) -> bool:
        now = now or time.time()
        q = self._attempts[client_id]
        cutoff = now - settings.jarvis_login_window_seconds
        while q and q[0] < cutoff:
            q.popleft()
        return len(q) < settings.jarvis_login_max_attempts

    def record_failed_attempt(self, client_id: str, now: float | None = None) -> None:
        self._attempts[client_id].append(now or time.time())

    def clear_attempts(self, client_id: str) -> None:
        self._attempts.pop(client_id, None)

    def issue_session(self, now: int | None = None) -> str:
        if not self.configured:
            raise RuntimeError("Owner authentication is not configured")
        now = int(now or time.time())
        expires = now + settings.jarvis_session_days * 24 * 3600
        payload = f"v1.{expires}".encode("utf-8")
        sig = hmac.new(self._key(), payload, hashlib.sha256).digest()
        raw = payload + b"." + sig
        return base64.urlsafe_b64encode(raw).decode("ascii").rstrip("=")

    def verify_session(self, token: str | None, now: int | None = None) -> bool:
        if not token or not self.configured:
            return False
        try:
            padding = "=" * (-len(token) % 4)
            raw = base64.urlsafe_b64decode(token + padding)
            payload, supplied_sig = raw.rsplit(b".", 1)
            version, expires_text = payload.decode("utf-8").split(".", 1)
            if version != "v1":
                return False
            expires = int(expires_text)
        except (ValueError, UnicodeDecodeError):
            return False
        expected_sig = hmac.new(self._key(), payload, hashlib.sha256).digest()
        if not hmac.compare_digest(supplied_sig, expected_sig):
            return False
        return expires >= int(now or time.time())

    @staticmethod
    def safe_next(value: str | None) -> str:
        if not value or not value.startswith("/") or value.startswith("//"):
            return "/"
        return value


owner_auth = OwnerAuth()
