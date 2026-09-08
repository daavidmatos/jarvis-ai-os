from __future__ import annotations

import json
import math
import re
from dataclasses import dataclass
from typing import Any

from jarvis.router import ModelRouter


BLENDER_ACTIONS: dict[str, dict[str, Any]] = {
    "inspect_scene": {},
    "select_object": {"name": "string"},
    "set_transform": {
        "name": "string",
        "location": "vec3_optional",
        "rotation_euler": "vec3_optional",
        "scale": "vec3_optional",
    },
    "nudge_object": {
        "name": "string",
        "location_delta": "vec3_optional",
        "rotation_delta": "vec3_optional",
        "scale_factor": "number_optional",
    },
    "set_camera_lens": {"name": "string_optional", "lens_mm": "number"},
    "add_primitive": {
        "primitive": "cube|sphere|cylinder|plane|cone|torus",
        "name": "string_optional",
        "location": "vec3_optional",
        "scale": "vec3_optional",
    },
    "set_render_resolution": {"x": "integer", "y": "integer", "percentage": "integer_optional"},
    "render_preview": {},
    "save_project": {},
    "undo": {},
}


PLANNER_SYSTEM = """You are the JARVIS Desktop Action Planner.
Translate ONE already-authorized collaborative/autonomous desktop instruction into ONE safe structured action.
You are NOT allowed to execute shell commands, arbitrary code, scripts, file deletion, credential access, network requests, or unlisted actions.
Return ONLY valid JSON:
{
  "action":"one allowed action or unsupported",
  "arguments":{},
  "reason":"very short explanation"
}

For Blender, allowed actions are:
- inspect_scene
- select_object(name)
- set_transform(name, location?, rotation_euler?, scale?)
- nudge_object(name, location_delta?, rotation_delta?, scale_factor?)
- set_camera_lens(name?, lens_mm)
- add_primitive(primitive, name?, location?, scale?)
- set_render_resolution(x, y, percentage?)
- render_preview
- save_project
- undo

Rules:
- Use current reported scene state to resolve references such as "a câmera" or "o objeto selecionado".
- If the instruction is ambiguous enough that choosing an object/action would be unsafe, return unsupported and explain the missing detail.
- A vague relative phrase such as "afasta um pouco" may use a conservative nudge only when the active object or camera is unambiguous in state.
- Never invent an object name that is not present in reported state unless the action is add_primitive.
- Never return arbitrary Python or shell commands.
- For applications without a structured adapter, return unsupported.
"""


class DesktopActionError(RuntimeError):
    pass


@dataclass
class DesktopActionPlan:
    action: str
    arguments: dict[str, Any]
    reason: str = ""

    def to_dict(self) -> dict[str, Any]:
        return {"action": self.action, "arguments": self.arguments, "reason": self.reason}


class DesktopActionPlanner:
    def __init__(self, router: ModelRouter):
        self.router = router

    @staticmethod
    def _vec3(value: Any, *, max_abs: float | None = None) -> list[float] | None:
        if value is None:
            return None
        if not isinstance(value, list) or len(value) != 3:
            raise DesktopActionError("Expected a 3-number vector")
        out = [float(x) for x in value]
        if not all(math.isfinite(x) for x in out):
            raise DesktopActionError("Vector values must be finite")
        if max_abs is not None and any(abs(x) > max_abs for x in out):
            raise DesktopActionError(f"Vector delta exceeds safe limit {max_abs}")
        return out

    @classmethod
    def validate_blender(cls, action: str, arguments: dict[str, Any]) -> DesktopActionPlan:
        action = str(action or "").strip()
        args = dict(arguments or {})
        if action == "unsupported":
            return DesktopActionPlan("unsupported", {}, "Unsupported or ambiguous instruction")
        if action not in BLENDER_ACTIONS:
            raise DesktopActionError(f"Blender action is not allowed: {action}")

        if action in {"select_object", "set_transform", "nudge_object"}:
            name = str(args.get("name") or "").strip()
            if not name:
                raise DesktopActionError(f"{action} requires an object name")
            args["name"] = name[:200]

        if action == "set_transform":
            for key in ("location", "rotation_euler", "scale"):
                value = cls._vec3(args.get(key))
                if value is not None:
                    args[key] = value
                else:
                    args.pop(key, None)
            if not any(k in args for k in ("location", "rotation_euler", "scale")):
                raise DesktopActionError("set_transform requires at least one transform")

        elif action == "nudge_object":
            location = cls._vec3(args.get("location_delta"), max_abs=10.0)
            rotation = cls._vec3(args.get("rotation_delta"), max_abs=math.tau)
            if location is not None:
                args["location_delta"] = location
            else:
                args.pop("location_delta", None)
            if rotation is not None:
                args["rotation_delta"] = rotation
            else:
                args.pop("rotation_delta", None)
            if args.get("scale_factor") is not None:
                scale = float(args["scale_factor"])
                if not math.isfinite(scale) or not 0.05 <= scale <= 20.0:
                    raise DesktopActionError("scale_factor must be between 0.05 and 20")
                args["scale_factor"] = scale
            if not any(k in args for k in ("location_delta", "rotation_delta", "scale_factor")):
                raise DesktopActionError("nudge_object requires a delta")

        elif action == "set_camera_lens":
            name = str(args.get("name") or "").strip()
            if name:
                args["name"] = name[:200]
            else:
                args.pop("name", None)
            lens = float(args.get("lens_mm"))
            if not math.isfinite(lens) or not 1.0 <= lens <= 300.0:
                raise DesktopActionError("lens_mm must be between 1 and 300")
            args["lens_mm"] = lens

        elif action == "add_primitive":
            primitive = str(args.get("primitive") or "").strip().lower()
            if primitive not in {"cube", "sphere", "cylinder", "plane", "cone", "torus"}:
                raise DesktopActionError("Unsupported primitive")
            args["primitive"] = primitive
            if args.get("name") is not None:
                args["name"] = str(args["name"])[:200]
            for key in ("location", "scale"):
                value = cls._vec3(args.get(key))
                if value is not None:
                    args[key] = value
                else:
                    args.pop(key, None)

        elif action == "set_render_resolution":
            x = int(args.get("x"))
            y = int(args.get("y"))
            pct = int(args.get("percentage", 100))
            if not 64 <= x <= 8192 or not 64 <= y <= 8192:
                raise DesktopActionError("Render dimensions must be between 64 and 8192")
            if not 1 <= pct <= 100:
                raise DesktopActionError("Render percentage must be between 1 and 100")
            args = {"x": x, "y": y, "percentage": pct}

        elif action in {"inspect_scene", "render_preview", "save_project", "undo"}:
            args = {}

        return DesktopActionPlan(action=action, arguments=args)

    async def plan(self, app: str, instruction: str, state: dict[str, Any] | None = None) -> DesktopActionPlan:
        app_norm = app.strip().lower().replace(" ", "_")
        if app_norm != "blender":
            return DesktopActionPlan(
                action="unsupported",
                arguments={},
                reason=f"No structured write adapter is installed for {app_norm} yet.",
            )
        provider = self.router.primary()
        reply = await provider.complete(
            PLANNER_SYSTEM,
            json.dumps(
                {
                    "app": "blender",
                    "instruction": instruction,
                    "reported_state": state or {},
                    "allowed_actions": BLENDER_ACTIONS,
                },
                ensure_ascii=False,
            ),
        )
        raw = reply.text.strip()
        match = re.search(r"\{.*\}", raw, re.S)
        try:
            data = json.loads(match.group(0) if match else raw)
        except json.JSONDecodeError as exc:
            raise DesktopActionError("Planner returned invalid JSON") from exc
        action = str(data.get("action") or "unsupported")
        if action == "unsupported":
            return DesktopActionPlan(
                "unsupported", {}, str(data.get("reason") or "Ambiguous or unsupported instruction")[:500]
            )
        plan = self.validate_blender(action, data.get("arguments") or {})
        plan.reason = str(data.get("reason") or "")[:500]
        return plan
