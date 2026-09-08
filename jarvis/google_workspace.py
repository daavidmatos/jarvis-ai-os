from __future__ import annotations

import base64
import json
import os
import secrets
import time
from datetime import datetime, timedelta, timezone
from email.message import EmailMessage
from pathlib import Path
from urllib.parse import urlencode
from uuid import uuid4

import httpx

from jarvis.config import settings


GMAIL_BASE = "https://gmail.googleapis.com/gmail/v1"
CALENDAR_BASE = "https://www.googleapis.com/calendar/v3"
GOOGLE_TOKEN_URL = "https://oauth2.googleapis.com/token"
GOOGLE_AUTH_URL = "https://accounts.google.com/o/oauth2/v2/auth"

# Gmail + Calendar only for this phase. Drive/Contacts can be added incrementally.
GOOGLE_WORKSPACE_SCOPES = [
    "https://www.googleapis.com/auth/gmail.modify",
    "https://www.googleapis.com/auth/gmail.send",
    "https://www.googleapis.com/auth/calendar",
]


class GoogleWorkspaceError(RuntimeError):
    pass


class GoogleWorkspaceAuth:
    def __init__(self):
        self._states: dict[str, float] = {}

    @property
    def token_path(self) -> Path:
        return Path(settings.google_oauth_token_path).expanduser().resolve()

    @property
    def monitor_path(self) -> Path:
        return Path(settings.google_monitor_state_path).expanduser().resolve()

    @property
    def callback_url(self) -> str:
        base = settings.public_base_url.rstrip("/")
        return f"{base}/v1/integrations/google/callback"

    def _read_json(self, path: Path) -> dict:
        if not path.exists():
            return {}
        try:
            value = json.loads(path.read_text(encoding="utf-8"))
            return value if isinstance(value, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_json(self, path: Path, data: dict) -> None:
        path.parent.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(path.parent, 0o700)
        except OSError:
            pass
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

    def _credentials_ready(self) -> bool:
        return bool(settings.google_oauth_client_id and settings.google_oauth_client_secret)

    def status(self) -> dict:
        token = self._read_json(self.token_path)
        return {
            "configured": self._credentials_ready(),
            "connected": bool(token.get("refresh_token") or token.get("access_token")),
            "scopes": token.get("scope", "").split() if token.get("scope") else [],
            "public_base_url": settings.public_base_url,
            "gmail_monitoring_available": bool(settings.gmail_pubsub_topic),
            "calendar_monitoring_available": settings.public_base_url.startswith("https://"),
        }

    def authorization_url(self) -> str:
        if not self._credentials_ready():
            raise GoogleWorkspaceError(
                "Google OAuth is not configured. Set GOOGLE_OAUTH_CLIENT_ID and GOOGLE_OAUTH_CLIENT_SECRET on the server."
            )
        if not settings.public_base_url:
            raise GoogleWorkspaceError("PUBLIC_BASE_URL is required for Google OAuth.")
        state = secrets.token_urlsafe(32)
        self._states[state] = time.time()
        params = {
            "client_id": settings.google_oauth_client_id,
            "redirect_uri": self.callback_url,
            "response_type": "code",
            "scope": " ".join(GOOGLE_WORKSPACE_SCOPES),
            "access_type": "offline",
            "include_granted_scopes": "true",
            "prompt": "consent",
            "state": state,
        }
        return f"{GOOGLE_AUTH_URL}?{urlencode(params)}"

    async def exchange_code(self, code: str, state: str) -> dict:
        created = self._states.pop(state, None)
        if not created or time.time() - created > 600:
            raise GoogleWorkspaceError("Invalid or expired Google OAuth state.")
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "code": code,
                    "client_id": settings.google_oauth_client_id,
                    "client_secret": settings.google_oauth_client_secret,
                    "redirect_uri": self.callback_url,
                    "grant_type": "authorization_code",
                },
            )
        if response.status_code >= 400:
            raise GoogleWorkspaceError(f"Google OAuth exchange failed: HTTP {response.status_code}")
        payload = response.json()
        previous = self._read_json(self.token_path)
        if not payload.get("refresh_token") and previous.get("refresh_token"):
            payload["refresh_token"] = previous["refresh_token"]
        payload["expires_at"] = int(time.time()) + int(payload.get("expires_in", 3600)) - 60
        self._write_json(self.token_path, payload)
        return self.status()

    def disconnect(self) -> bool:
        existed = self.token_path.exists()
        if existed:
            self.token_path.unlink()
        return existed

    async def access_token(self) -> str:
        token = self._read_json(self.token_path)
        if token.get("access_token") and int(token.get("expires_at", 0)) > int(time.time()):
            return str(token["access_token"])
        refresh = token.get("refresh_token")
        if not refresh:
            raise GoogleWorkspaceError("Google Workspace is not connected.")
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(
                GOOGLE_TOKEN_URL,
                data={
                    "client_id": settings.google_oauth_client_id,
                    "client_secret": settings.google_oauth_client_secret,
                    "refresh_token": refresh,
                    "grant_type": "refresh_token",
                },
            )
        if response.status_code >= 400:
            raise GoogleWorkspaceError(f"Google token refresh failed: HTTP {response.status_code}")
        updated = response.json()
        token.update(updated)
        token["refresh_token"] = refresh
        token["expires_at"] = int(time.time()) + int(updated.get("expires_in", 3600)) - 60
        self._write_json(self.token_path, token)
        return str(token["access_token"])

    async def request(self, method: str, url: str, **kwargs) -> dict:
        token = await self.access_token()
        headers = dict(kwargs.pop("headers", {}))
        headers["Authorization"] = f"Bearer {token}"
        async with httpx.AsyncClient(timeout=45) as client:
            response = await client.request(method, url, headers=headers, **kwargs)
        if response.status_code >= 400:
            detail = response.text[:1000]
            raise GoogleWorkspaceError(f"Google API HTTP {response.status_code}: {detail}")
        if response.status_code == 204 or not response.content:
            return {}
        return response.json()

    async def gmail_profile(self) -> dict:
        return await self.request("GET", f"{GMAIL_BASE}/users/me/profile")

    async def gmail_search(self, query: str = "in:inbox", max_results: int = 10) -> list[dict]:
        max_results = min(max(int(max_results), 1), 25)
        data = await self.request(
            "GET",
            f"{GMAIL_BASE}/users/me/messages",
            params={"q": query, "maxResults": max_results},
        )
        rows = []
        for item in data.get("messages", []):
            rows.append(await self.gmail_message(item["id"], metadata_only=True))
        return rows

    async def gmail_message(self, message_id: str, metadata_only: bool = False) -> dict:
        params = {"format": "metadata" if metadata_only else "full"}
        if metadata_only:
            params["metadataHeaders"] = ["From", "To", "Subject", "Date"]
        data = await self.request(
            "GET", f"{GMAIL_BASE}/users/me/messages/{message_id}", params=params
        )
        payload = data.get("payload", {})
        headers = {h.get("name", "").lower(): h.get("value", "") for h in payload.get("headers", [])}
        body = ""
        if not metadata_only:
            body = self._extract_body(payload)
        return {
            "id": data.get("id"),
            "thread_id": data.get("threadId"),
            "from": headers.get("from"),
            "to": headers.get("to"),
            "subject": headers.get("subject"),
            "date": headers.get("date"),
            "snippet": data.get("snippet", ""),
            "body": body[:20000],
            "label_ids": data.get("labelIds", []),
        }

    def _extract_body(self, payload: dict) -> str:
        def decode(value: str) -> str:
            try:
                padding = "=" * (-len(value) % 4)
                return base64.urlsafe_b64decode(value + padding).decode("utf-8", errors="replace")
            except Exception:
                return ""

        mime = payload.get("mimeType", "")
        data = payload.get("body", {}).get("data")
        if data and mime in {"text/plain", "text/html", ""}:
            return decode(data)
        plain = []
        html = []
        for part in payload.get("parts", []) or []:
            text = self._extract_body(part)
            if not text:
                continue
            if part.get("mimeType") == "text/plain":
                plain.append(text)
            else:
                html.append(text)
        return "\n".join(plain or html)

    async def gmail_send(self, to: str, subject: str, body: str) -> dict:
        msg = EmailMessage()
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
        return await self.request(
            "POST", f"{GMAIL_BASE}/users/me/messages/send", json={"raw": raw}
        )

    async def gmail_draft(self, to: str, subject: str, body: str) -> dict:
        msg = EmailMessage()
        msg["To"] = to
        msg["Subject"] = subject
        msg.set_content(body)
        raw = base64.urlsafe_b64encode(msg.as_bytes()).decode("ascii")
        return await self.request(
            "POST", f"{GMAIL_BASE}/users/me/drafts", json={"message": {"raw": raw}}
        )

    async def gmail_watch(self) -> dict:
        if not settings.gmail_pubsub_topic:
            raise GoogleWorkspaceError("GMAIL_PUBSUB_TOPIC is not configured.")
        result = await self.request(
            "POST",
            f"{GMAIL_BASE}/users/me/watch",
            json={
                "topicName": settings.gmail_pubsub_topic,
                "labelIds": ["INBOX"],
                "labelFilterBehavior": "INCLUDE",
            },
        )
        state = self._read_json(self.monitor_path)
        state["gmail"] = {
            "history_id": result.get("historyId"),
            "expiration": result.get("expiration"),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._write_json(self.monitor_path, state)
        return result

    async def calendar_upcoming(self, hours: int = 168, max_results: int = 20) -> list[dict]:
        start = datetime.now(timezone.utc)
        end = start + timedelta(hours=min(max(hours, 1), 24 * 90))
        data = await self.request(
            "GET",
            f"{CALENDAR_BASE}/calendars/primary/events",
            params={
                "timeMin": start.isoformat().replace("+00:00", "Z"),
                "timeMax": end.isoformat().replace("+00:00", "Z"),
                "singleEvents": "true",
                "orderBy": "startTime",
                "maxResults": min(max(int(max_results), 1), 50),
            },
        )
        return [
            {
                "id": e.get("id"),
                "summary": e.get("summary"),
                "start": e.get("start"),
                "end": e.get("end"),
                "location": e.get("location"),
                "attendees": e.get("attendees", []),
                "htmlLink": e.get("htmlLink"),
            }
            for e in data.get("items", [])
        ]

    async def calendar_create(
        self,
        summary: str,
        start: str,
        end: str,
        timezone_name: str = "America/Sao_Paulo",
        description: str = "",
        attendees: list[str] | None = None,
    ) -> dict:
        body = {
            "summary": summary,
            "description": description,
            "start": {"dateTime": start, "timeZone": timezone_name},
            "end": {"dateTime": end, "timeZone": timezone_name},
        }
        if attendees:
            body["attendees"] = [{"email": email} for email in attendees]
        return await self.request(
            "POST",
            f"{CALENDAR_BASE}/calendars/primary/events",
            params={"sendUpdates": "all" if attendees else "none"},
            json=body,
        )

    async def calendar_watch(self) -> dict:
        if not settings.public_base_url.startswith("https://"):
            raise GoogleWorkspaceError("Calendar push monitoring requires an HTTPS PUBLIC_BASE_URL.")
        state = self._read_json(self.monitor_path)
        channel_id = str(uuid4())
        channel_token = secrets.token_urlsafe(24)
        result = await self.request(
            "POST",
            f"{CALENDAR_BASE}/calendars/primary/events/watch",
            json={
                "id": channel_id,
                "type": "web_hook",
                "address": f"{settings.public_base_url.rstrip('/')}/v1/webhooks/google/calendar",
                "token": channel_token,
            },
        )
        state["calendar"] = {
            "channel_id": channel_id,
            "channel_token": channel_token,
            "resource_id": result.get("resourceId"),
            "expiration": result.get("expiration"),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        self._write_json(self.monitor_path, state)
        return {k: v for k, v in result.items() if k != "token"}

    def validate_calendar_webhook(self, channel_id: str | None, channel_token: str | None) -> bool:
        state = self._read_json(self.monitor_path).get("calendar", {})
        return bool(
            channel_id
            and channel_token
            and channel_id == state.get("channel_id")
            and secrets.compare_digest(channel_token, str(state.get("channel_token", "")))
        )


google_workspace = GoogleWorkspaceAuth()
