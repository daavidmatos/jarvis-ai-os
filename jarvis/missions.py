from __future__ import annotations

from dataclasses import asdict, dataclass, field
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
    allow_commerce: bool = False


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
    session_id: str | None = None
    current_step: int = 0
    execution_log: list[dict[str, Any]] = field(default_factory=list)
    outputs: list[dict[str, Any]] = field(default_factory=list)


class MissionStore:
    """Persistent single-user mission store.

    The MVP keeps mission state in a private JSON file so an approved mission can
    survive process restarts. Hosted production should move this state to Postgres.
    """

    @property
    def path(self) -> Path:
        return settings.secrets_file.parent / "missions.json"

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
            os.chmod(self.path.parent, 0o700)
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, self.path)

    @staticmethod
    def _hydrate(raw: dict[str, Any]) -> Mission:
        defaults = {
            "approved_at": None,
            "session_id": None,
            "current_step": 0,
            "execution_log": [],
            "outputs": [],
        }
        return Mission(**{**defaults, **raw})

    def create(
        self,
        title: str,
        objective: str,
        envelope: MissionEnvelope,
        plan: list[dict[str, Any]],
        blockers: list[str] | None = None,
        session_id: str | None = None,
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
            session_id=session_id,
        )
        data = self._read()
        data[mission.id] = asdict(mission)
        self._write(data)
        return mission

    def get(self, mission_id: str) -> Mission | None:
        raw = self._read().get(mission_id)
        return self._hydrate(raw) if raw else None

    def list(self) -> list[Mission]:
        rows = [self._hydrate(x) for x in self._read().values()]
        return sorted(rows, key=lambda x: x.created_at, reverse=True)

    def latest_for_session(self, session_id: str, active_only: bool = True) -> Mission | None:
        statuses = {
            MissionStatus.BLOCKED.value,
            MissionStatus.APPROVAL_REQUIRED.value,
            MissionStatus.APPROVED.value,
            MissionStatus.RUNNING.value,
            MissionStatus.MONITORING.value,
        }
        rows = [m for m in self.list() if m.session_id == session_id]
        if active_only:
            rows = [m for m in rows if m.status in statuses]
        return rows[0] if rows else None

    def save(self, mission: Mission) -> Mission:
        mission.updated_at = datetime.now(timezone.utc).isoformat()
        data = self._read()
        data[mission.id] = asdict(mission)
        self._write(data)
        return mission

    def approve(self, mission_id: str) -> Mission:
        mission = self.get(mission_id)
        if not mission:
            raise KeyError("Mission not found")
        if mission.blockers:
            raise ValueError("Mission still has blockers")
        now = datetime.now(timezone.utc).isoformat()
        mission.status = MissionStatus.APPROVED.value
        mission.approved_at = now
        mission.updated_at = now
        return self.save(mission)

    def update_status(self, mission_id: str, status: MissionStatus) -> Mission:
        mission = self.get(mission_id)
        if not mission:
            raise KeyError("Mission not found")
        mission.status = status.value
        return self.save(mission)

    def update_envelope(self, mission_id: str, **changes: Any) -> Mission:
        mission = self.get(mission_id)
        if not mission:
            raise KeyError("Mission not found")
        mission.envelope.update({k: v for k, v in changes.items() if v is not None})
        return self.save(mission)

    def replace_blockers(self, mission_id: str, blockers: list[str]) -> Mission:
        mission = self.get(mission_id)
        if not mission:
            raise KeyError("Mission not found")
        mission.blockers = blockers
        mission.status = (
            MissionStatus.BLOCKED.value if blockers else MissionStatus.APPROVAL_REQUIRED.value
        )
        return self.save(mission)

    def add_blocker(self, mission_id: str, blocker: str) -> Mission:
        mission = self.get(mission_id)
        if not mission:
            raise KeyError("Mission not found")
        if blocker not in mission.blockers:
            mission.blockers.append(blocker)
        mission.status = MissionStatus.BLOCKED.value
        return self.save(mission)

    def set_current_step(self, mission_id: str, index: int) -> Mission:
        mission = self.get(mission_id)
        if not mission:
            raise KeyError("Mission not found")
        mission.current_step = max(0, index)
        return self.save(mission)

    def append_log(self, mission_id: str, event: str, payload: dict[str, Any] | None = None) -> Mission:
        mission = self.get(mission_id)
        if not mission:
            raise KeyError("Mission not found")
        mission.execution_log.append(
            {
                "at": datetime.now(timezone.utc).isoformat(),
                "event": event,
                "payload": payload or {},
            }
        )
        mission.execution_log = mission.execution_log[-300:]
        return self.save(mission)

    def append_output(self, mission_id: str, output: dict[str, Any]) -> Mission:
        mission = self.get(mission_id)
        if not mission:
            raise KeyError("Mission not found")
        mission.outputs.append(output)
        mission.outputs = mission.outputs[-100:]
        return self.save(mission)


mission_store = MissionStore()
