from __future__ import annotations

from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from enum import Enum
from pathlib import Path
from typing import Any
from uuid import uuid4
import json
import os

from jarvis.config import settings


class MissionStatus(str, Enum):
    PROPOSED = "proposed"
    BLOCKED = "blocked"
    APPROVAL_REQUIRED = "approval_required"
    APPROVED = "approved"
    RUNNING = "running"
    MONITORING = "monitoring"
    COMPLETED = "completed"
    FAILED = "failed"
    CANCELLED = "cancelled"


@dataclass
class MissionEnvelope:
    objective: str
    channels: list[str]
    daily_budget_limit: float | None = None
    total_budget_limit: float | None = None
    currency: str = "BRL"
    allow_reversible_changes: bool = True
    allow_publish: bool = False
    allow_external_messages: bool = False
    allow_spend: bool = False


@dataclass
class Mission:
    id: str
    title: str
    objective: str
    status: str
    blockers: list[str]
    envelope: dict[str, Any]
    plan: list[dict[str, Any]]
    created_at: str
    updated_at: str
    approved_at: str | None = None


class MissionStore:
    """Persistent single-user mission store for the current MVP.

    Production deployment should move this into Postgres. The JSON store keeps the
    mission model usable locally and in a persistent mounted volume today.
    """

    @property
    def path(self) -> Path:
        base = settings.secrets_file.parent
        return base / "missions.json"

    def _read(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write(self, data: dict[str, dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, self.path)

    def create(
        self,
        title: str,
        objective: str,
        envelope: MissionEnvelope,
        plan: list[dict[str, Any]],
        blockers: list[str] | None = None,
    ) -> Mission:
        now = datetime.now(timezone.utc).isoformat()
        blockers = blockers or []
        status = MissionStatus.BLOCKED.value if blockers else MissionStatus.APPROVAL_REQUIRED.value
        mission = Mission(
            id=str(uuid4()),
            title=title,
            objective=objective,
            status=status,
            blockers=blockers,
            envelope=asdict(envelope),
            plan=plan,
            created_at=now,
            updated_at=now,
        )
        data = self._read()
        data[mission.id] = asdict(mission)
        self._write(data)
        return mission

    def get(self, mission_id: str) -> Mission | None:
        raw = self._read().get(mission_id)
        return Mission(**raw) if raw else None

    def list(self) -> list[Mission]:
        rows = [Mission(**x) for x in self._read().values()]
        return sorted(rows, key=lambda x: x.created_at, reverse=True)

    def approve(self, mission_id: str) -> Mission:
        data = self._read()
        raw = data.get(mission_id)
        if not raw:
            raise KeyError("Mission not found")
        if raw.get("blockers"):
            raise ValueError("Mission still has blockers")
        now = datetime.now(timezone.utc).isoformat()
        raw["status"] = MissionStatus.APPROVED.value
        raw["approved_at"] = now
        raw["updated_at"] = now
        data[mission_id] = raw
        self._write(data)
        return Mission(**raw)

    def update_status(self, mission_id: str, status: MissionStatus) -> Mission:
        data = self._read()
        raw = data.get(mission_id)
        if not raw:
            raise KeyError("Mission not found")
        raw["status"] = status.value
        raw["updated_at"] = datetime.now(timezone.utc).isoformat()
        data[mission_id] = raw
        self._write(data)
        return Mission(**raw)


mission_store = MissionStore()
