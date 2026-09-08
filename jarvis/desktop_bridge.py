from __future__ import annotations

import asyncio
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from typing import Any
from uuid import uuid4

from jarvis.desktop_frames import desktop_frames


@dataclass
class DesktopClient:
    client_id: str
    platform: str
    apps: list[str] = field(default_factory=list)
    active_app: str | None = None
    active_document: str | None = None
    state: dict[str, Any] = field(default_factory=dict)
    last_frame: dict[str, Any] | None = None
    last_result: dict[str, Any] | None = None
    connected: bool = True
    last_seen: str = ""


class DesktopBridge:
    """Server-side half of the JARVIS Desktop Bridge.

    The cloud JARVIS cannot inspect/control local desktop applications by itself.
    An authenticated local companion reports state/private screen frames and receives
    semantic commands. Structured action planning and local adapters enforce a second
    boundary before an edit reaches an application such as Blender.
    """

    def __init__(self):
        self.clients: dict[str, DesktopClient] = {}
        self._queues: dict[str, asyncio.Queue] = {}
        self._results: dict[str, dict[str, Any]] = {}

    @staticmethod
    def _now() -> str:
        return datetime.now(timezone.utc).isoformat()

    @staticmethod
    def _norm(value: str) -> str:
        return value.strip().lower().replace(" ", "_")

    def register(
        self,
        client_id: str,
        platform: str,
        apps: list[str] | None = None,
        active_app: str | None = None,
        active_document: str | None = None,
        state: dict[str, Any] | None = None,
    ) -> DesktopClient:
        previous = self.clients.get(client_id)
        client = DesktopClient(
            client_id=client_id,
            platform=platform,
            apps=[self._norm(x) for x in (apps or [])],
            active_app=self._norm(active_app) if active_app else None,
            active_document=active_document,
            state=state or {},
            last_frame=previous.last_frame if previous else None,
            last_result=previous.last_result if previous else None,
            connected=True,
            last_seen=self._now(),
        )
        self.clients[client_id] = client
        self._queues.setdefault(client_id, asyncio.Queue())
        return client

    def disconnect(self, client_id: str) -> None:
        client = self.clients.get(client_id)
        if client:
            client.connected = False
            client.last_seen = self._now()

    def update_state(self, client_id: str, payload: dict[str, Any]) -> DesktopClient:
        client = self.clients.get(client_id)
        if not client:
            client = self.register(client_id, str(payload.get("platform") or "unknown"))
        if isinstance(payload.get("apps"), list):
            client.apps = [self._norm(str(x)) for x in payload["apps"]]
        if payload.get("active_app") is not None:
            value = str(payload.get("active_app") or "").strip()
            client.active_app = self._norm(value) if value else None
        if payload.get("active_document") is not None:
            client.active_document = str(payload.get("active_document") or "") or None
        if isinstance(payload.get("state"), dict):
            client.state = payload["state"]
        client.connected = True
        client.last_seen = self._now()
        if str(payload.get("type") or "") == "result" and payload.get("command_id"):
            self.record_result(client_id, payload)
        return client

    def update_frame(self, client_id: str, payload: dict[str, Any]) -> DesktopClient:
        client = self.clients.get(client_id)
        if not client:
            client = self.register(client_id, str(payload.get("platform") or "unknown"))
        frame_id = str(payload.get("frame_id") or uuid4())
        mime_type = str(payload.get("mime_type") or "")
        stored: dict[str, Any] = {}
        if payload.get("data_b64"):
            stored = desktop_frames.store(
                client_id,
                frame_id,
                mime_type,
                str(payload.get("data_b64")),
            )
        client.last_frame = {
            "frame_id": frame_id,
            "mime_type": mime_type,
            "width": payload.get("width"),
            "height": payload.get("height"),
            "storage_key": stored.get("storage_key") or payload.get("storage_key"),
            "bytes": stored.get("bytes") or payload.get("bytes"),
            "captured_at": payload.get("captured_at") or self._now(),
        }
        client.connected = True
        client.last_seen = self._now()
        return client

    def record_result(self, client_id: str, payload: dict[str, Any]) -> dict[str, Any]:
        command_id = str(payload.get("command_id") or "")
        result = {
            "command_id": command_id,
            "ok": bool(payload.get("ok")),
            "result": payload.get("result") if isinstance(payload.get("result"), dict) else {},
            "error": payload.get("error"),
            "finished_at": self._now(),
        }
        if command_id:
            self._results[command_id] = result
            while len(self._results) > 500:
                oldest = next(iter(self._results))
                self._results.pop(oldest, None)
        client = self.clients.get(client_id)
        if client:
            client.last_result = result
            client.last_seen = self._now()
        return result

    def command_result(self, command_id: str) -> dict[str, Any] | None:
        return self._results.get(str(command_id))

    def status(self) -> dict[str, Any]:
        connected = [c for c in self.clients.values() if c.connected]
        return {
            "connected": bool(connected),
            "clients": [asdict(c) for c in connected],
            "requires_local_companion": not bool(connected),
        }

    def find_app(self, app: str) -> DesktopClient | None:
        wanted = self._norm(app)
        aliases = {
            "photoshop": {"photoshop", "adobe_photoshop"},
            "illustrator": {"illustrator", "adobe_illustrator"},
            "premiere": {"premiere", "premiere_pro", "adobe_premiere_pro"},
            "after_effects": {"after_effects", "adobe_after_effects"},
            "blender": {"blender"},
            "figma": {"figma"},
            "trello": {"trello"},
        }
        wanted_set = aliases.get(wanted, {wanted})
        for client in self.clients.values():
            if not client.connected:
                continue
            available = set(client.apps)
            if client.active_app:
                available.add(client.active_app)
            if available.intersection(wanted_set):
                return client
        return None

    def snapshot_for_app(self, app: str) -> dict[str, Any] | None:
        client = self.find_app(app)
        if not client:
            return None
        return {
            "client_id": client.client_id,
            "platform": client.platform,
            "active_app": client.active_app,
            "active_document": client.active_document,
            "state": client.state,
            "frame": client.last_frame,
            "last_result": client.last_result,
            "last_seen": client.last_seen,
        }

    async def queue_command(
        self,
        client_id: str,
        app: str,
        instruction: str,
        *,
        mode: str = "collaborative",
        approval_scope: str = "single_command",
        plan: dict[str, Any] | None = None,
    ) -> dict[str, Any]:
        client = self.clients.get(client_id)
        if not client or not client.connected:
            raise RuntimeError("Desktop Bridge client is not connected.")
        command = {
            "type": "command",
            "command_id": str(uuid4()),
            "app": self._norm(app),
            "instruction": instruction,
            "mode": mode,
            "approval_scope": approval_scope,
            "plan": plan,
            "created_at": self._now(),
        }
        queue = self._queues.setdefault(client_id, asyncio.Queue())
        await queue.put(command)
        return command

    async def next_command(self, client_id: str, timeout: float = 25.0) -> dict[str, Any] | None:
        queue = self._queues.setdefault(client_id, asyncio.Queue())
        try:
            return await asyncio.wait_for(queue.get(), timeout=timeout)
        except TimeoutError:
            return None


desktop_bridge = DesktopBridge()
