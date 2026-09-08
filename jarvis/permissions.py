from __future__ import annotations

from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from uuid import uuid4
import json
import os

from jarvis.config import settings


@dataclass
class StandingPermission:
    id: str
    name: str
    channels: list[str]
    allow_publish: bool = False
    allow_external_messages: bool = False
    allow_spend: bool = False
    allow_commerce: bool = False
    allow_workspace_edits: bool = False
    allow_computer_control: bool = False
    max_daily_spend: float | None = None
    max_total_spend: float | None = None
    currency: str = "BRL"
    active: bool = True
    created_at: str = ""


class StandingPermissionStore:
    @property
    def path(self) -> Path:
        return settings.secrets_file.parent / "standing_permissions.json"

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
    def _hydrate(row: dict[str, Any]) -> StandingPermission:
        defaults = {
            "allow_workspace_edits": False,
            "allow_computer_control": False,
        }
        return StandingPermission(**{**defaults, **row})

    def create(
        self,
        name: str,
        channels: list[str],
        allow_publish: bool = False,
        allow_external_messages: bool = False,
        allow_spend: bool = False,
        allow_commerce: bool = False,
        allow_workspace_edits: bool = False,
        allow_computer_control: bool = False,
        max_daily_spend: float | None = None,
        max_total_spend: float | None = None,
        currency: str = "BRL",
    ) -> StandingPermission:
        permission = StandingPermission(
            id=str(uuid4()),
            name=name,
            channels=[x.lower() for x in channels],
            allow_publish=allow_publish,
            allow_external_messages=allow_external_messages,
            allow_spend=allow_spend,
            allow_commerce=allow_commerce,
            allow_workspace_edits=allow_workspace_edits,
            allow_computer_control=allow_computer_control,
            max_daily_spend=max_daily_spend,
            max_total_spend=max_total_spend,
            currency=currency,
            created_at=datetime.now(timezone.utc).isoformat(),
        )
        data = self._read()
        data[permission.id] = asdict(permission)
        self._write(data)
        return permission

    def list(self, active_only: bool = False) -> list[StandingPermission]:
        rows = [self._hydrate(row) for row in self._read().values()]
        if active_only:
            rows = [row for row in rows if row.active]
        return sorted(rows, key=lambda x: x.created_at, reverse=True)

    def delete(self, permission_id: str) -> bool:
        data = self._read()
        existed = permission_id in data
        data.pop(permission_id, None)
        self._write(data)
        return existed

    def effective(self, channels: list[str]) -> dict[str, Any]:
        wanted = {x.lower() for x in channels}
        matches = [
            p for p in self.list(active_only=True)
            if not p.channels or "*" in p.channels or wanted.intersection(p.channels)
        ]
        daily = [p.max_daily_spend for p in matches if p.max_daily_spend is not None]
        total = [p.max_total_spend for p in matches if p.max_total_spend is not None]
        return {
            "allow_publish": any(p.allow_publish for p in matches),
            "allow_external_messages": any(p.allow_external_messages for p in matches),
            "allow_spend": any(p.allow_spend for p in matches),
            "allow_commerce": any(p.allow_commerce for p in matches),
            "allow_workspace_edits": any(p.allow_workspace_edits for p in matches),
            "allow_computer_control": any(p.allow_computer_control for p in matches),
            "max_daily_spend": max(daily) if daily else None,
            "max_total_spend": max(total) if total else None,
            "permission_ids": [p.id for p in matches],
        }

    def context_text(self) -> str:
        rows = self.list(active_only=True)
        if not rows:
            return "No standing permissions."
        return "\n".join(
            f"- {p.name}: channels={','.join(p.channels) or '*'}, publish={p.allow_publish}, "
            f"messages={p.allow_external_messages}, spend={p.allow_spend}, commerce={p.allow_commerce}, "
            f"workspace_edits={p.allow_workspace_edits}, computer_control={p.allow_computer_control}, "
            f"daily_limit={p.max_daily_spend}, total_limit={p.max_total_spend} {p.currency}"
            for p in rows
        )


standing_permissions = StandingPermissionStore()
