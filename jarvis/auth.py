from __future__ import annotations

import base64
import hashlib
import hmac
import html
import os
import secrets
import time
from collections import defaultdict, deque
from urllib.parse import parse_qs, quote

from fastapi.responses import HTMLResponse, JSONResponse, RedirectResponse
from starlette.requests import Request
from starlette.websockets import WebSocket

from jarvis.config import settings


COOKIE_NAME = "jarvis_owner"


class OwnerAuth:
    """Single-owner authentication for the personal JARVIS deployment.

    The owner password stays in deployment environment variables. Browser sessions
    use a signed, HttpOnly cookie; the password itself is never written to a cookie
    or persisted by JARVIS.
    """

    def __init__(self) -> None:
        self._attempts: dict[str, deque[float]] = defaultdict(deque)

    @property
    def configured(self) -> bool:
        return bool((settings.jarvis_access_password or "").strip())

    @property
    def hosted(self) -> bool:
        # Render exposes at least one of these variables. APP_ENV=production is the
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

    @staticmethod
    def public_path(path: str) -> bool:
        return (
            path == "/health"
            or path == "/favicon.ico"
            or path.startswith("/static/")
            or path.startswith("/v1/webhooks/")
            or path == "/v1/integrations/google/callback"
            or path.startswith("/v1/assets/")
        )


owner_auth = OwnerAuth()


def _login_page(error: str = "", next_path: str = "/", status_code: int = 200) -> HTMLResponse:
    safe_next = owner_auth.safe_next(next_path)
    error_html = f'<div class="error">{html.escape(error)}</div>' if error else ""
    body = f"""<!doctype html>
<html lang="pt-BR"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1,viewport-fit=cover">
<meta name="theme-color" content="#060b12"><title>JARVIS · Acesso</title>
<style>
:root{{font-family:Inter,system-ui,-apple-system,BlinkMacSystemFont,"Segoe UI",sans-serif;color:#eaf2ff;background:#060b12}}*{{box-sizing:border-box}}body{{margin:0;min-height:100dvh;display:grid;place-items:center;padding:20px;background:radial-gradient(circle at 50% -20%,#193b5a 0,#0a111a 35%,#05080d 70%)}}.card{{width:min(520px,100%);padding:28px;border-radius:24px;background:rgba(9,18,29,.9);border:1px solid rgba(126,232,255,.22);box-shadow:0 30px 100px #000}}.pill{{display:inline-block;border:1px solid rgba(126,232,255,.22);border-radius:20px;padding:5px 9px;font-size:10px;letter-spacing:.08em;opacity:.72}}h1{{margin:14px 0 9px;font-size:34px}}p{{color:#a9b7c9;line-height:1.5}}input{{width:100%;margin-top:16px;background:#08121d;border:1px solid rgba(126,232,255,.22);border-radius:14px;color:white;padding:15px;font:inherit;font-size:16px;outline:none}}button{{width:100%;margin-top:12px;border:0;border-radius:14px;background:#d8f7ff;color:#061019;font-weight:800;padding:14px;font-size:13px}}.error{{margin-top:14px;color:#ff9d9d;font-size:13px}}.small{{font-size:11px;opacity:.65;margin-top:18px}}</style></head>
<body><main class="card"><span class="pill">ACESSO DO PROPRIETÁRIO</span><h1>JARVIS</h1><p>Entre para acessar seu assistente, integrações, missões e ferramentas.</p>{error_html}
<form method="post" action="/login"><input type="hidden" name="next" value="{html.escape(safe_next, quote=True)}"><input name="password" type="password" autocomplete="current-password" placeholder="Senha do JARVIS" autofocus required><button type="submit">ENTRAR</button></form><p class="small">A sessão usa cookie seguro e HttpOnly. Sua senha não é salva no navegador pelo JARVIS.</p></main></body></html>"""
    return HTMLResponse(body, status_code=status_code, headers={"Cache-Control": "no-store"})


def _not_configured(path: str):
    if path.startswith("/v1/"):
        return JSONResponse(
            {"detail": "owner_auth_not_configured", "message": "Configure JARVIS_ACCESS_PASSWORD on the server."},
            status_code=503,
        )
    return HTMLResponse(
        """<!doctype html><html lang='pt-BR'><meta name='viewport' content='width=device-width,initial-scale=1'><body style='font-family:system-ui;background:#061019;color:#eaf2ff;padding:30px'><h2>JARVIS protegido</h2><p>O servidor está online, mas o acesso do proprietário ainda não foi configurado.</p><p>Defina <code>JARVIS_ACCESS_PASSWORD</code> nas variáveis de ambiente do servidor e faça o redeploy.</p></body></html>""",
        status_code=503,
        headers={"Cache-Control": "no-store"},
    )


class OwnerAccessMiddleware:
    """ASGI access gate for browser/API access while preserving signed webhooks."""

    def __init__(self, app):
        self.app = app

    async def __call__(self, scope, receive, send):
        scope_type = scope.get("type")
        path = scope.get("path", "")

        if scope_type == "websocket":
            # Desktop Bridge has its own independent token. Protect interactive chat
            # WebSocket with the owner browser session.
            if path == "/ws/desktop-bridge" or not owner_auth.required:
                await self.app(scope, receive, send)
                return
            ws = WebSocket(scope, receive=receive, send=send)
            if owner_auth.configured and owner_auth.verify_session(ws.cookies.get(COOKIE_NAME)):
                await self.app(scope, receive, send)
                return
            await ws.close(code=4401)
            return

        if scope_type != "http":
            await self.app(scope, receive, send)
            return

        request = Request(scope, receive=receive)

        if path == "/login":
            if request.method == "GET":
                if owner_auth.configured and owner_auth.verify_session(request.cookies.get(COOKIE_NAME)):
                    response = RedirectResponse("/", status_code=303)
                elif owner_auth.required and not owner_auth.configured:
                    response = _not_configured(path)
                else:
                    response = _login_page(next_path=request.query_params.get("next") or "/")
                await response(scope, receive, send)
                return

            if request.method == "POST":
                if owner_auth.required and not owner_auth.configured:
                    response = _not_configured(path)
                    await response(scope, receive, send)
                    return
                client_id = request.client.host if request.client else "unknown"
                if not owner_auth.can_attempt(client_id):
                    response = _login_page("Muitas tentativas. Aguarde alguns minutos e tente novamente.", status_code=429)
                    await response(scope, receive, send)
                    return
                form = parse_qs((await request.body()).decode("utf-8", errors="ignore"))
                password = (form.get("password") or [""])[0]
                next_path = owner_auth.safe_next((form.get("next") or ["/"])[0])
                if not owner_auth.check_password(password):
                    owner_auth.record_failed_attempt(client_id)
                    response = _login_page("Senha incorreta.", next_path=next_path, status_code=401)
                    await response(scope, receive, send)
                    return
                owner_auth.clear_attempts(client_id)
                response = RedirectResponse(next_path, status_code=303)
                response.set_cookie(
                    COOKIE_NAME,
                    owner_auth.issue_session(),
                    max_age=settings.jarvis_session_days * 24 * 3600,
                    httponly=True,
                    secure=owner_auth.hosted,
                    samesite="lax",
                    path="/",
                )
                response.headers["Cache-Control"] = "no-store"
                await response(scope, receive, send)
                return

        if path == "/logout":
            response = RedirectResponse("/login", status_code=303)
            response.delete_cookie(COOKIE_NAME, path="/")
            response.headers["Cache-Control"] = "no-store"
            await response(scope, receive, send)
            return

        if owner_auth.public_path(path) or not owner_auth.required:
            await self.app(scope, receive, send)
            return

        if not owner_auth.configured:
            response = _not_configured(path)
            await response(scope, receive, send)
            return

        if owner_auth.verify_session(request.cookies.get(COOKIE_NAME)):
            await self.app(scope, receive, send)
            return

        if path.startswith("/v1/"):
            response = JSONResponse(
                {"detail": "owner_auth_required", "message": "Authenticate as the JARVIS owner."},
                status_code=401,
                headers={"Cache-Control": "no-store"},
            )
        else:
            target = "/login?next=" + quote(owner_auth.safe_next(path), safe="/")
            response = RedirectResponse(target, status_code=303)
        await response(scope, receive, send)
