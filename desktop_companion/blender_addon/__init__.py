from __future__ import annotations

bl_info = {
    "name": "JARVIS Desktop Bridge",
    "author": "JARVIS AI OS",
    "version": (0, 1, 0),
    "blender": (4, 0, 0),
    "location": "Preferences > Add-ons",
    "description": "Expose bounded Blender scene state and execute allow-listed JARVIS actions",
    "category": "System",
}

import json
import math
import os
import time
from pathlib import Path
from typing import Any

import bpy


BASE_DIR = Path("~/.config/jarvis/blender").expanduser().resolve()
COMMANDS_PATH = BASE_DIR / "commands.jsonl"
RESULTS_PATH = BASE_DIR / "results.jsonl"
STATE_PATH = BASE_DIR / "state.json"
_cursor = 0
_running = False


def _ensure_dir() -> None:
    BASE_DIR.mkdir(parents=True, exist_ok=True)
    try:
        os.chmod(BASE_DIR, 0o700)
    except OSError:
        pass


def _vec(value) -> list[float]:
    return [round(float(value[0]), 6), round(float(value[1]), 6), round(float(value[2]), 6)]


def _object_summary(obj: bpy.types.Object) -> dict[str, Any]:
    return {
        "name": obj.name,
        "type": obj.type,
        "location": _vec(obj.location),
        "rotation_euler": _vec(obj.rotation_euler),
        "scale": _vec(obj.scale),
        "visible": bool(obj.visible_get()),
        "selected": bool(obj.select_get()),
    }


def scene_state() -> dict[str, Any]:
    scene = bpy.context.scene
    active = bpy.context.view_layer.objects.active
    camera = scene.camera
    objects = [_object_summary(obj) for obj in list(scene.objects)[:150]]
    return {
        "available": True,
        "is_active": True,
        "project": bpy.data.filepath or "Untitled",
        "scene": scene.name,
        "active_object": active.name if active else None,
        "camera": {
            "name": camera.name,
            "location": _vec(camera.location),
            "rotation_euler": _vec(camera.rotation_euler),
            "lens_mm": round(float(camera.data.lens), 4) if camera.type == "CAMERA" else None,
        } if camera else None,
        "objects": objects,
        "object_count": len(scene.objects),
        "render": {
            "engine": scene.render.engine,
            "resolution_x": scene.render.resolution_x,
            "resolution_y": scene.render.resolution_y,
            "resolution_percentage": scene.render.resolution_percentage,
            "frame_current": scene.frame_current,
        },
        "updated_at": time.time(),
    }


def _atomic_write_json(path: Path, payload: dict[str, Any]) -> None:
    _ensure_dir()
    tmp = path.with_suffix(path.suffix + ".tmp")
    tmp.write_text(json.dumps(payload, ensure_ascii=False, indent=2), encoding="utf-8")
    try:
        os.chmod(tmp, 0o600)
    except OSError:
        pass
    os.replace(tmp, path)


def publish_state() -> dict[str, Any]:
    state = scene_state()
    _atomic_write_json(STATE_PATH, state)
    return state


def _object(name: str) -> bpy.types.Object:
    obj = bpy.data.objects.get(name)
    if obj is None:
        raise ValueError(f"Object not found: {name}")
    return obj


def _as_vec3(value: Any, name: str) -> tuple[float, float, float]:
    if not isinstance(value, list) or len(value) != 3:
        raise ValueError(f"{name} must be a 3-number vector")
    vals = tuple(float(x) for x in value)
    if not all(math.isfinite(x) for x in vals):
        raise ValueError(f"{name} must contain finite values")
    return vals


def execute_action(action: str, args: dict[str, Any]) -> dict[str, Any]:
    if action == "inspect_scene":
        return {"ok": True, "state": scene_state()}

    if action == "select_object":
        obj = _object(str(args["name"]))
        for other in bpy.context.selected_objects:
            other.select_set(False)
        obj.select_set(True)
        bpy.context.view_layer.objects.active = obj

    elif action == "set_transform":
        obj = _object(str(args["name"]))
        if "location" in args:
            obj.location = _as_vec3(args["location"], "location")
        if "rotation_euler" in args:
            obj.rotation_euler = _as_vec3(args["rotation_euler"], "rotation_euler")
        if "scale" in args:
            obj.scale = _as_vec3(args["scale"], "scale")

    elif action == "nudge_object":
        obj = _object(str(args["name"]))
        if "location_delta" in args:
            delta = _as_vec3(args["location_delta"], "location_delta")
            obj.location.x += delta[0]
            obj.location.y += delta[1]
            obj.location.z += delta[2]
        if "rotation_delta" in args:
            delta = _as_vec3(args["rotation_delta"], "rotation_delta")
            obj.rotation_euler.x += delta[0]
            obj.rotation_euler.y += delta[1]
            obj.rotation_euler.z += delta[2]
        if "scale_factor" in args:
            factor = float(args["scale_factor"])
            obj.scale *= factor

    elif action == "set_camera_lens":
        name = str(args.get("name") or "")
        obj = _object(name) if name else bpy.context.scene.camera
        if obj is None or obj.type != "CAMERA":
            raise ValueError("No valid camera is available")
        obj.data.lens = float(args["lens_mm"])

    elif action == "add_primitive":
        primitive = str(args["primitive"]).lower()
        location = _as_vec3(args.get("location", [0, 0, 0]), "location")
        operators = {
            "cube": bpy.ops.mesh.primitive_cube_add,
            "sphere": bpy.ops.mesh.primitive_uv_sphere_add,
            "cylinder": bpy.ops.mesh.primitive_cylinder_add,
            "plane": bpy.ops.mesh.primitive_plane_add,
            "cone": bpy.ops.mesh.primitive_cone_add,
            "torus": bpy.ops.mesh.primitive_torus_add,
        }
        op = operators.get(primitive)
        if op is None:
            raise ValueError(f"Unsupported primitive: {primitive}")
        op(location=location)
        obj = bpy.context.active_object
        if obj and args.get("name"):
            obj.name = str(args["name"])[:200]
        if obj and "scale" in args:
            obj.scale = _as_vec3(args["scale"], "scale")

    elif action == "set_render_resolution":
        scene = bpy.context.scene
        scene.render.resolution_x = int(args["x"])
        scene.render.resolution_y = int(args["y"])
        scene.render.resolution_percentage = int(args.get("percentage", 100))

    elif action == "render_preview":
        bpy.ops.render.render(write_still=False)

    elif action == "save_project":
        if not bpy.data.filepath:
            raise ValueError("Project is Untitled. Save it manually once before JARVIS can overwrite it.")
        bpy.ops.wm.save_as_mainfile(filepath=bpy.data.filepath)

    elif action == "undo":
        bpy.ops.ed.undo()

    else:
        raise ValueError(f"Action is not allow-listed: {action}")

    return {"ok": True, "state": scene_state()}


def _append_result(payload: dict[str, Any]) -> None:
    _ensure_dir()
    with RESULTS_PATH.open("a", encoding="utf-8") as f:
        f.write(json.dumps(payload, ensure_ascii=False) + "\n")
    try:
        os.chmod(RESULTS_PATH, 0o600)
    except OSError:
        pass


def _read_new_commands() -> list[dict[str, Any]]:
    global _cursor
    if not COMMANDS_PATH.exists():
        return []
    lines = COMMANDS_PATH.read_text(encoding="utf-8").splitlines()
    new = lines[_cursor:]
    _cursor = len(lines)
    rows = []
    for line in new:
        try:
            row = json.loads(line)
        except json.JSONDecodeError:
            continue
        if isinstance(row, dict):
            rows.append(row)
    return rows


def _timer():
    if not _running:
        return None
    for command in _read_new_commands():
        command_id = str(command.get("command_id") or "")
        action = str(command.get("action") or "")
        args = command.get("arguments") if isinstance(command.get("arguments"), dict) else {}
        try:
            result = execute_action(action, args)
            payload = {"command_id": command_id, "action": action, **result, "finished_at": time.time()}
        except Exception as exc:
            payload = {
                "command_id": command_id,
                "action": action,
                "ok": False,
                "error": str(exc),
                "state": scene_state(),
                "finished_at": time.time(),
            }
        _append_result(payload)
    try:
        publish_state()
    except Exception:
        pass
    return 0.75


class JARVIS_PT_bridge_panel(bpy.types.Panel):
    bl_label = "JARVIS Bridge"
    bl_idname = "JARVIS_PT_bridge_panel"
    bl_space_type = "VIEW_3D"
    bl_region_type = "UI"
    bl_category = "JARVIS"

    def draw(self, context):
        layout = self.layout
        layout.label(text="Desktop Bridge: active" if _running else "Desktop Bridge: stopped")
        layout.label(text=str(BASE_DIR))


def register():
    global _running, _cursor
    _ensure_dir()
    if COMMANDS_PATH.exists():
        try:
            _cursor = len(COMMANDS_PATH.read_text(encoding="utf-8").splitlines())
        except Exception:
            _cursor = 0
    bpy.utils.register_class(JARVIS_PT_bridge_panel)
    _running = True
    publish_state()
    if not bpy.app.timers.is_registered(_timer):
        bpy.app.timers.register(_timer, first_interval=0.5, persistent=True)


def unregister():
    global _running
    _running = False
    if bpy.app.timers.is_registered(_timer):
        bpy.app.timers.unregister(_timer)
    try:
        bpy.utils.unregister_class(JARVIS_PT_bridge_panel)
    except Exception:
        pass


if __name__ == "__main__":
    register()
