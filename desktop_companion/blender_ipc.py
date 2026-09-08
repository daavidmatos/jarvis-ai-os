from __future__ import annotations

import json
import os
import time
from pathlib import Path
from typing import Any


class BlenderIPC:
    """File-based IPC between the desktop companion and the Blender add-on.

    This avoids opening another network listener on the user's machine. The add-on
    polls commands.jsonl and publishes state/results under a private config folder.
    """

    def __init__(self, base_dir: Path | None = None):
        self.base_dir = (base_dir or Path("~/.config/jarvis/blender").expanduser()).resolve()
        self.base_dir.mkdir(parents=True, exist_ok=True)
        try:
            os.chmod(self.base_dir, 0o700)
        except OSError:
            pass
        self.commands_path = self.base_dir / "commands.jsonl"
        self.results_path = self.base_dir / "results.jsonl"
        self.state_path = self.base_dir / "state.json"
        self._result_offset = 0
        self._results: dict[str, dict[str, Any]] = {}

    def state(self, stale_after: float = 8.0) -> dict[str, Any]:
        if not self.state_path.exists():
            return {"available": False, "reason": "Blender add-on has not published state yet."}
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
        except Exception:
            return {"available": False, "reason": "Blender state file is unreadable."}
        age = max(0.0, time.time() - self.state_path.stat().st_mtime)
        raw["available"] = age <= stale_after
        raw["state_age_seconds"] = round(age, 2)
        if age > stale_after:
            raw["reason"] = "Blender add-on state is stale; open Blender or enable the JARVIS add-on."
        return raw

    def queue_action(self, command_id: str, action: str, arguments: dict[str, Any] | None = None) -> None:
        record = {
            "command_id": str(command_id),
            "action": str(action),
            "arguments": dict(arguments or {}),
            "created_at": time.time(),
        }
        with self.commands_path.open("a", encoding="utf-8") as f:
            f.write(json.dumps(record, ensure_ascii=False) + "\n")
        try:
            os.chmod(self.commands_path, 0o600)
        except OSError:
            pass

    def _refresh_results(self) -> None:
        if not self.results_path.exists():
            return
        with self.results_path.open("r", encoding="utf-8") as f:
            f.seek(self._result_offset)
            for line in f:
                try:
                    row = json.loads(line)
                except json.JSONDecodeError:
                    continue
                cid = str(row.get("command_id") or "")
                if cid:
                    self._results[cid] = row
            self._result_offset = f.tell()

    def result(self, command_id: str) -> dict[str, Any] | None:
        self._refresh_results()
        return self._results.get(str(command_id))

    def wait_result(self, command_id: str, timeout: float = 45.0) -> dict[str, Any]:
        deadline = time.time() + max(1.0, timeout)
        while time.time() < deadline:
            result = self.result(command_id)
            if result is not None:
                return result
            time.sleep(0.25)
        return {
            "command_id": str(command_id),
            "ok": False,
            "error": "Timed out waiting for Blender add-on result.",
        }
