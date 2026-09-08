import pytest
from fastapi.testclient import TestClient

from jarvis.api import app, jarvis
from jarvis.desktop_bridge import DesktopBridge
from jarvis.universal_collaboration import UniversalCollaborationHub


def test_collaboration_intent_is_distinct_from_autonomous_mission():
    assert UniversalCollaborationHub.looks_like_start("Jarvis, vamos editar uma planilha juntos")
    assert UniversalCollaborationHub.looks_like_start("vamos trabalhar nesse projeto no Blender")
    assert UniversalCollaborationHub.looks_like_start("vamos organizar esse Trello")
    assert not UniversalCollaborationHub.looks_like_start("faça sozinho uma edição no Blender")


def test_visual_targets_are_detected():
    blender = UniversalCollaborationHub.detect_target("vamos trabalhar nesse projeto 3D no Blender")
    photoshop = UniversalCollaborationHub.detect_target("vamos editar essa arte no Photoshop")
    docs = UniversalCollaborationHub.detect_target("vamos revisar este Google Docs")
    assert blender and blender["kind"] == "3d_scene" and blender["target"] == "blender"
    assert photoshop and photoshop["kind"] == "design" and photoshop["target"] == "photoshop"
    assert docs and docs["kind"] == "document"


@pytest.mark.asyncio
async def test_desktop_bridge_registers_state_and_queues_single_command():
    bridge = DesktopBridge()
    client = bridge.register(
        "laptop-1",
        "linux",
        apps=["Blender", "Adobe Photoshop"],
        active_app="Blender",
        active_document="scene.blend",
        state={"objects": 12},
    )
    assert bridge.status()["connected"] is True
    assert bridge.find_app("blender") == client
    snapshot = bridge.snapshot_for_app("blender")
    assert snapshot and snapshot["active_document"] == "scene.blend"

    queued = await bridge.queue_command(
        client.client_id,
        "blender",
        "mova a câmera 20 cm para trás",
        mode="collaborative",
        approval_scope="single_command",
    )
    command = await bridge.next_command(client.client_id, timeout=0.1)
    assert command and command["command_id"] == queued["command_id"]
    assert command["approval_scope"] == "single_command"


def test_workspace_tools_are_registered_and_mutations_are_not_global_autonomy():
    names = set(jarvis.tools.tools)
    expected = {
        "google_docs.recent",
        "google_docs.read",
        "google_docs.append",
        "google_docs.replace",
        "google_sheets.recent",
        "google_sheets.read",
        "google_sheets.update",
        "google_sheets.append",
        "trello.boards",
        "trello.board",
        "trello.create_card",
        "trello.move_card",
        "desktop.status",
        "desktop.inspect",
        "desktop.command",
    }
    assert expected.issubset(names)
    autonomous = {item["name"] for item in jarvis.tools.autonomous_specs()}
    assert "google_docs.read" in autonomous
    assert "google_sheets.read" in autonomous
    assert "trello.board" in autonomous
    assert "desktop.inspect" in autonomous
    assert "google_docs.append" not in autonomous
    assert "google_sheets.update" not in autonomous
    assert "trello.move_card" not in autonomous
    assert "desktop.command" not in autonomous


def test_workspace_and_desktop_status_endpoints():
    client = TestClient(app)
    desktop = client.get("/v1/desktop/status")
    assert desktop.status_code == 200
    assert "connected" in desktop.json()
    workspaces = client.get("/v1/workspaces")
    assert workspaces.status_code == 200
    assert "catalog" in workspaces.json()
