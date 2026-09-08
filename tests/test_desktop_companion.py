from __future__ import annotations

import ast
import base64
from pathlib import Path

import pytest

from desktop_companion.blender_ipc import BlenderIPC
from desktop_companion.config import CompanionConfig
from desktop_companion.detect import canonical_apps
from desktop_companion.service import service_text
from jarvis.config import settings
from jarvis.desktop_actions import DesktopActionError, DesktopActionPlanner
from jarvis.desktop_bridge import DesktopBridge


def test_companion_websocket_url_local_and_secure_remote():
    cfg = CompanionConfig(server_url="http://localhost:8000", token="abc")
    assert cfg.websocket_url() == "ws://localhost:8000/ws/desktop-bridge?token=abc"
    cfg.server_url = "https://jarvis.example.com"
    assert cfg.websocket_url().startswith("wss://jarvis.example.com/ws/desktop-bridge?")
    cfg.server_url = "http://jarvis.example.com"
    with pytest.raises(ValueError):
        cfg.websocket_url()


def test_canonical_app_detection():
    apps = canonical_apps(["blender", "Adobe Premiere Pro.exe", "something-else"])
    assert "blender" in apps
    assert "premiere" in apps


def test_blender_action_validation_is_allowlisted():
    plan = DesktopActionPlanner.validate_blender(
        "nudge_object",
        {"name": "Camera", "location_delta": [0, 0, 0.5]},
    )
    assert plan.action == "nudge_object"
    assert plan.arguments["name"] == "Camera"
    with pytest.raises(DesktopActionError):
        DesktopActionPlanner.validate_blender("execute_python", {"code": "print(1)"})
    with pytest.raises(DesktopActionError):
        DesktopActionPlanner.validate_blender(
            "nudge_object", {"name": "Camera", "location_delta": [99, 0, 0]}
        )


def test_blender_ipc_round_trip_files(tmp_path: Path):
    ipc = BlenderIPC(tmp_path)
    ipc.queue_action("cmd-1", "select_object", {"name": "Cube"})
    line = ipc.commands_path.read_text(encoding="utf-8")
    assert '"command_id": "cmd-1"' in line
    ipc.results_path.write_text(
        '{"command_id":"cmd-1","ok":true,"result":"done"}\n', encoding="utf-8"
    )
    result = ipc.result("cmd-1")
    assert result and result["ok"] is True


def test_blender_addon_source_parses_without_importing_bpy():
    path = Path(__file__).resolve().parents[1] / "desktop_companion" / "blender_addon" / "__init__.py"
    ast.parse(path.read_text(encoding="utf-8"))


def test_linux_service_uses_current_python_module():
    text = service_text()
    assert "-m desktop_companion run" in text
    assert "Restart=always" in text


def test_desktop_bridge_stores_private_bounded_frame(monkeypatch, tmp_path: Path):
    monkeypatch.setattr(settings, "workspace_dir", str(tmp_path))
    bridge = DesktopBridge()
    bridge.register("client-a", "Linux", apps=["blender"], active_app="blender")
    bridge.update_frame(
        "client-a",
        {
            "frame_id": "frame-1",
            "mime_type": "image/jpeg",
            "width": 1,
            "height": 1,
            "data_b64": base64.b64encode(b"fake-jpeg").decode("ascii"),
        },
    )
    snapshot = bridge.snapshot_for_app("blender")
    assert snapshot is not None
    assert snapshot["frame"]["storage_key"]
    assert "data_b64" not in snapshot["frame"]


@pytest.mark.asyncio
async def test_desktop_bridge_command_contains_structured_plan():
    bridge = DesktopBridge()
    bridge.register("client-a", "Linux", apps=["blender"])
    command = await bridge.queue_command(
        "client-a",
        "blender",
        "mova a câmera",
        plan={"action": "nudge_object", "arguments": {"name": "Camera", "location_delta": [0, 0, 0.5]}},
    )
    queued = await bridge.next_command("client-a", timeout=0.1)
    assert queued is not None
    assert queued["command_id"] == command["command_id"]
    assert queued["plan"]["action"] == "nudge_object"


def test_result_is_attached_to_live_client():
    bridge = DesktopBridge()
    bridge.register("client-a", "Linux", apps=["blender"])
    bridge.update_state(
        "client-a",
        {
            "type": "result",
            "command_id": "cmd-1",
            "ok": True,
            "result": {"state": {"scene": "Scene"}},
            "state": {"blender": {"available": True}},
        },
    )
    snap = bridge.snapshot_for_app("blender")
    assert snap and snap["last_result"]["command_id"] == "cmd-1"
    assert snap["last_result"]["ok"] is True
