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
    "set_transform": {"name": "string", "location": "vec3_optional", "rotation_euler": "vec3_optional", "scale": "vec3_optional"},
    "nudge_object": {"name": "string", "location_delta": "vec3_optional", "rotation_delta": "vec3_optional", "scale_factor": "number_optional"},
    "set_camera_lens": {"name": "string_optional", "lens_mm": "number"},
    "add_primitive": {"primitive": "cube|sphere|cylinder|plane|cone|torus", "name": "string_optional", "location": "vec3_optional", "scale": "vec3_optional"},
    "set_render_resolution": {"x": "integer", "y": "integer", "percentage": "integer_optional"},
    "render_preview": {},
    "save_project": {},
    "undo": {},
}

FIGMA_ACTIONS: dict[str, dict[str, Any]] = {
    "inspect_document": {},
    "create_rectangle": {"name": "string_optional", "x": "number", "y": "number", "width": "number", "height": "number", "fill_hex": "hex_optional", "corner_radius": "number_optional"},
    "create_text": {"name": "string_optional", "text": "string", "x": "number", "y": "number", "font_size": "number_optional", "font_weight": "regular|bold_optional", "fill_hex": "hex_optional"},
    "create_frame": {"name": "string", "x": "number", "y": "number", "width": "number", "height": "number", "fill_hex": "hex_optional"},
    "create_landing_page": {"name": "string", "product_name": "string", "headline": "string", "subheadline": "string", "cta": "string", "accent_hex": "hex_optional", "background_hex": "hex_optional", "sections": "string_list_optional"},
    "set_text": {"node_id": "string_optional", "node_name": "string_optional", "text": "string"},
    "set_geometry": {"node_id": "string_optional", "node_name": "string_optional", "x": "number_optional", "y": "number_optional", "width": "number_optional", "height": "number_optional"},
    "set_fill": {"node_id": "string_optional", "node_name": "string_optional", "fill_hex": "hex"},
    "delete_node": {"node_id": "string_optional", "node_name": "string_optional"},
    "undo": {},
}

PHOTOSHOP_ACTIONS: dict[str, dict[str, Any]] = {
    "inspect_document": {},
    "create_document": {"name": "string", "width": "integer", "height": "integer", "resolution": "number_optional"},
    "create_text_layer": {"name": "string_optional", "text": "string", "x": "number", "y": "number", "font_size": "number_optional"},
    "create_rectangle_shape": {"name": "string_optional", "x": "number", "y": "number", "width": "number", "height": "number", "fill_hex": "hex_optional", "corner_radius": "number_optional"},
    "create_group": {"name": "string"},
    "rename_layer": {"layer_name": "string", "new_name": "string"},
    "set_layer_opacity": {"layer_name": "string", "opacity": "number"},
    "translate_layer": {"layer_name": "string", "dx": "number", "dy": "number"},
    "create_marketing_canvas": {"name": "string", "width": "integer", "height": "integer", "headline": "string", "subheadline": "string_optional", "cta": "string_optional", "background_hex": "hex_optional", "accent_hex": "hex_optional"},
    "undo": {},
}

ILLUSTRATOR_ACTIONS: dict[str, dict[str, Any]] = {
    "inspect_document": {},
    "create_document": {"name": "string", "width": "number", "height": "number"},
    "create_rectangle": {"name": "string_optional", "x": "number", "y": "number", "width": "number", "height": "number", "fill_hex": "hex_optional", "corner_radius": "number_optional"},
    "create_text": {"name": "string_optional", "text": "string", "x": "number", "y": "number", "font_size": "number_optional", "fill_hex": "hex_optional"},
    "create_artboard": {"x": "number", "y": "number", "width": "number", "height": "number"},
    "create_group": {"name": "string"},
    "set_fill": {"item_name": "string", "fill_hex": "hex"},
    "move_item": {"item_name": "string", "x": "number", "y": "number"},
    "create_landing_mockup": {"name": "string", "width": "number", "height": "number", "product_name": "string", "headline": "string", "subheadline": "string", "cta": "string", "accent_hex": "hex_optional", "background_hex": "hex_optional"},
    "undo": {},
}

AFTER_EFFECTS_ACTIONS: dict[str, dict[str, Any]] = {
    "inspect_project": {},
    "create_composition": {"name": "string", "width": "integer", "height": "integer", "duration": "number", "fps": "number"},
    "add_text_layer": {"comp_name": "string_optional", "name": "string_optional", "text": "string", "x": "number", "y": "number", "font_size": "number_optional"},
    "add_solid_layer": {"comp_name": "string_optional", "name": "string", "width": "integer", "height": "integer", "fill_hex": "hex_optional"},
    "add_shape_rectangle": {"comp_name": "string_optional", "name": "string", "x": "number", "y": "number", "width": "number", "height": "number", "fill_hex": "hex_optional"},
    "set_layer_position": {"comp_name": "string_optional", "layer_name": "string", "x": "number", "y": "number"},
    "set_layer_scale": {"comp_name": "string_optional", "layer_name": "string", "x": "number", "y": "number"},
    "set_layer_opacity": {"comp_name": "string_optional", "layer_name": "string", "opacity": "number"},
    "add_position_keyframe": {"comp_name": "string_optional", "layer_name": "string", "time": "number", "x": "number", "y": "number"},
    "create_marketing_comp": {"name": "string", "width": "integer", "height": "integer", "duration": "number", "fps": "number", "headline": "string", "subheadline": "string_optional", "cta": "string_optional", "background_hex": "hex_optional", "accent_hex": "hex_optional"},
    "undo": {},
}

APP_ACTIONS = {
    "blender": BLENDER_ACTIONS,
    "figma": FIGMA_ACTIONS,
    "photoshop": PHOTOSHOP_ACTIONS,
    "illustrator": ILLUSTRATOR_ACTIONS,
    "after_effects": AFTER_EFFECTS_ACTIONS,
}

PLANNER_SYSTEM = """You are the JARVIS Creative Desktop Action Planner.
Translate ONE already-authorized user instruction into ONE bounded structured action for the named creative application.
The user may delegate creative decisions. When they say to create a landing page, visual, composition, scene or design, make sensible reversible design choices instead of asking unnecessary questions.
You are NOT allowed to return shell commands, arbitrary code/scripts, file deletion, credential access, network requests, plugin installation, or actions outside the supplied allow-list.
Return ONLY valid JSON:
{"action":"one allowed action or unsupported","arguments":{},"reason":"very short explanation"}
Rules:
- Use reported app state to resolve references when possible.
- Never invent the name/id of an existing layer/node/object that is not in reported state. Creation actions may invent names for NEW content.
- If an edit targets an existing item and the target is genuinely ambiguous, return unsupported with the missing detail.
- For broad creation instructions, choose a coherent default layout/style and use the most suitable high-level creation action.
- Prefer one high-level bounded action (for example create_landing_page or create_marketing_comp) over many low-level actions when it fulfills the instruction.
- Never return arbitrary Python, JSX, JavaScript, ExtendScript, shell, batch scripts, or eval strings.
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

    @staticmethod
    def _number(value: Any, name: str, minimum: float = -100000.0, maximum: float = 100000.0) -> float:
        try:
            out = float(value)
        except (TypeError, ValueError) as exc:
            raise DesktopActionError(f"{name} must be numeric") from exc
        if not math.isfinite(out) or not minimum <= out <= maximum:
            raise DesktopActionError(f"{name} is outside safe bounds")
        return out

    @classmethod
    def _integer(cls, value: Any, name: str, minimum: int = 1, maximum: int = 16384) -> int:
        out = int(cls._number(value, name, minimum, maximum))
        return out

    @staticmethod
    def _string(value: Any, name: str, required: bool = True, limit: int = 4000) -> str:
        out = str(value or "").strip()
        if required and not out:
            raise DesktopActionError(f"{name} is required")
        return out[:limit]

    @staticmethod
    def _hex(value: Any, default: str | None = None) -> str | None:
        if value in (None, ""):
            return default
        text = str(value).strip().upper()
        if not text.startswith("#"):
            text = "#" + text
        if not re.fullmatch(r"#[0-9A-F]{6}", text):
            raise DesktopActionError("Color must be a 6-digit hex value")
        return text

    @classmethod
    def _target(cls, args: dict[str, Any], id_key: str, name_key: str) -> None:
        ident = cls._string(args.get(id_key), id_key, required=False, limit=250)
        name = cls._string(args.get(name_key), name_key, required=False, limit=250)
        if not ident and not name:
            raise DesktopActionError(f"{id_key} or {name_key} is required")
        if ident:
            args[id_key] = ident
        else:
            args.pop(id_key, None)
        if name:
            args[name_key] = name
        else:
            args.pop(name_key, None)

    @classmethod
    def validate_blender(cls, action: str, arguments: dict[str, Any]) -> DesktopActionPlan:
        action = str(action or "").strip()
        args = dict(arguments or {})
        if action == "unsupported":
            return DesktopActionPlan("unsupported", {}, "Unsupported or ambiguous instruction")
        if action not in BLENDER_ACTIONS:
            raise DesktopActionError(f"Blender action is not allowed: {action}")
        if action in {"select_object", "set_transform", "nudge_object"}:
            args["name"] = cls._string(args.get("name"), "name", limit=200)
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
            if location is not None: args["location_delta"] = location
            else: args.pop("location_delta", None)
            if rotation is not None: args["rotation_delta"] = rotation
            else: args.pop("rotation_delta", None)
            if args.get("scale_factor") is not None:
                args["scale_factor"] = cls._number(args["scale_factor"], "scale_factor", 0.05, 20.0)
            if not any(k in args for k in ("location_delta", "rotation_delta", "scale_factor")):
                raise DesktopActionError("nudge_object requires a delta")
        elif action == "set_camera_lens":
            name = cls._string(args.get("name"), "name", required=False, limit=200)
            if name: args["name"] = name
            else: args.pop("name", None)
            args["lens_mm"] = cls._number(args.get("lens_mm"), "lens_mm", 1.0, 300.0)
        elif action == "add_primitive":
            primitive = cls._string(args.get("primitive"), "primitive").lower()
            if primitive not in {"cube", "sphere", "cylinder", "plane", "cone", "torus"}:
                raise DesktopActionError("Unsupported primitive")
            args["primitive"] = primitive
            if args.get("name") is not None: args["name"] = cls._string(args["name"], "name", required=False, limit=200)
            for key in ("location", "scale"):
                value = cls._vec3(args.get(key))
                if value is not None: args[key] = value
                else: args.pop(key, None)
        elif action == "set_render_resolution":
            args = {"x": cls._integer(args.get("x"), "x", 64, 8192), "y": cls._integer(args.get("y"), "y", 64, 8192), "percentage": cls._integer(args.get("percentage", 100), "percentage", 1, 100)}
        elif action in {"inspect_scene", "render_preview", "save_project", "undo"}:
            args = {}
        return DesktopActionPlan(action=action, arguments=args)

    @classmethod
    def validate_figma(cls, action: str, arguments: dict[str, Any]) -> DesktopActionPlan:
        if action not in FIGMA_ACTIONS:
            raise DesktopActionError(f"Figma action is not allowed: {action}")
        args = dict(arguments or {})
        if action in {"inspect_document", "undo"}: return DesktopActionPlan(action, {})
        if action in {"create_rectangle", "create_frame"}:
            if action == "create_frame": args["name"] = cls._string(args.get("name"), "name", limit=200)
            elif args.get("name") is not None: args["name"] = cls._string(args.get("name"), "name", required=False, limit=200)
            for key in ("x", "y"): args[key] = cls._number(args.get(key), key)
            for key in ("width", "height"): args[key] = cls._number(args.get(key), key, 1, 10000)
            if args.get("fill_hex") is not None: args["fill_hex"] = cls._hex(args.get("fill_hex"))
            if args.get("corner_radius") is not None: args["corner_radius"] = cls._number(args.get("corner_radius"), "corner_radius", 0, 500)
        elif action == "create_text":
            args["text"] = cls._string(args.get("text"), "text", limit=10000)
            args["x"] = cls._number(args.get("x"), "x")
            args["y"] = cls._number(args.get("y"), "y")
            args["font_size"] = cls._number(args.get("font_size", 32), "font_size", 6, 500)
            args["font_weight"] = "bold" if str(args.get("font_weight", "regular")).lower() == "bold" else "regular"
            if args.get("fill_hex") is not None: args["fill_hex"] = cls._hex(args.get("fill_hex"))
            if args.get("name") is not None: args["name"] = cls._string(args.get("name"), "name", required=False, limit=200)
        elif action == "create_landing_page":
            for key in ("name", "product_name", "headline", "subheadline", "cta"):
                args[key] = cls._string(args.get(key), key, limit=1000)
            args["accent_hex"] = cls._hex(args.get("accent_hex"), "#111111")
            args["background_hex"] = cls._hex(args.get("background_hex"), "#F7F3EE")
            sections = args.get("sections") or ["Benefícios", "Como funciona", "Prova social", "CTA final"]
            if not isinstance(sections, list): raise DesktopActionError("sections must be a list")
            args["sections"] = [cls._string(x, "section", limit=150) for x in sections[:8]]
        elif action == "set_text":
            cls._target(args, "node_id", "node_name")
            args["text"] = cls._string(args.get("text"), "text", limit=10000)
        elif action == "set_geometry":
            cls._target(args, "node_id", "node_name")
            changed = False
            for key in ("x", "y"):
                if args.get(key) is not None: args[key] = cls._number(args[key], key); changed = True
            for key in ("width", "height"):
                if args.get(key) is not None: args[key] = cls._number(args[key], key, 1, 10000); changed = True
            if not changed: raise DesktopActionError("set_geometry requires a geometry change")
        elif action == "set_fill":
            cls._target(args, "node_id", "node_name")
            args["fill_hex"] = cls._hex(args.get("fill_hex"))
        elif action == "delete_node":
            cls._target(args, "node_id", "node_name")
        return DesktopActionPlan(action, args)

    @classmethod
    def validate_photoshop(cls, action: str, arguments: dict[str, Any]) -> DesktopActionPlan:
        if action not in PHOTOSHOP_ACTIONS: raise DesktopActionError(f"Photoshop action is not allowed: {action}")
        args = dict(arguments or {})
        if action in {"inspect_document", "undo"}: return DesktopActionPlan(action, {})
        if action == "create_document":
            args = {"name": cls._string(args.get("name"), "name", limit=200), "width": cls._integer(args.get("width"), "width", 64, 12000), "height": cls._integer(args.get("height"), "height", 64, 12000), "resolution": cls._number(args.get("resolution", 72), "resolution", 36, 1200)}
        elif action == "create_text_layer":
            args["text"] = cls._string(args.get("text"), "text", limit=10000); args["x"] = cls._number(args.get("x"), "x"); args["y"] = cls._number(args.get("y"), "y"); args["font_size"] = cls._number(args.get("font_size", 32), "font_size", 6, 1000)
            if args.get("name") is not None: args["name"] = cls._string(args.get("name"), "name", required=False, limit=200)
        elif action == "create_rectangle_shape":
            for key in ("x", "y"): args[key] = cls._number(args.get(key), key)
            for key in ("width", "height"): args[key] = cls._number(args.get(key), key, 1, 12000)
            args["fill_hex"] = cls._hex(args.get("fill_hex"), "#111111")
            args["corner_radius"] = cls._number(args.get("corner_radius", 0), "corner_radius", 0, 1000)
            if args.get("name") is not None: args["name"] = cls._string(args.get("name"), "name", required=False, limit=200)
        elif action == "create_group": args = {"name": cls._string(args.get("name"), "name", limit=200)}
        elif action == "rename_layer": args = {"layer_name": cls._string(args.get("layer_name"), "layer_name", limit=200), "new_name": cls._string(args.get("new_name"), "new_name", limit=200)}
        elif action == "set_layer_opacity": args = {"layer_name": cls._string(args.get("layer_name"), "layer_name", limit=200), "opacity": cls._number(args.get("opacity"), "opacity", 0, 100)}
        elif action == "translate_layer": args = {"layer_name": cls._string(args.get("layer_name"), "layer_name", limit=200), "dx": cls._number(args.get("dx"), "dx", -12000, 12000), "dy": cls._number(args.get("dy"), "dy", -12000, 12000)}
        elif action == "create_marketing_canvas":
            args = {"name": cls._string(args.get("name"), "name", limit=200), "width": cls._integer(args.get("width"), "width", 64, 12000), "height": cls._integer(args.get("height"), "height", 64, 12000), "headline": cls._string(args.get("headline"), "headline", limit=1000), "subheadline": cls._string(args.get("subheadline"), "subheadline", required=False, limit=1500), "cta": cls._string(args.get("cta"), "cta", required=False, limit=500), "background_hex": cls._hex(args.get("background_hex"), "#F7F3EE"), "accent_hex": cls._hex(args.get("accent_hex"), "#111111")}
        return DesktopActionPlan(action, args)

    @classmethod
    def validate_illustrator(cls, action: str, arguments: dict[str, Any]) -> DesktopActionPlan:
        if action not in ILLUSTRATOR_ACTIONS: raise DesktopActionError(f"Illustrator action is not allowed: {action}")
        args = dict(arguments or {})
        if action in {"inspect_document", "undo"}: return DesktopActionPlan(action, {})
        if action == "create_document": args = {"name": cls._string(args.get("name"), "name", limit=200), "width": cls._number(args.get("width"), "width", 64, 20000), "height": cls._number(args.get("height"), "height", 64, 20000)}
        elif action == "create_rectangle":
            for key in ("x", "y"): args[key] = cls._number(args.get(key), key)
            for key in ("width", "height"): args[key] = cls._number(args.get(key), key, 1, 20000)
            args["fill_hex"] = cls._hex(args.get("fill_hex"), "#111111")
            args["corner_radius"] = cls._number(args.get("corner_radius", 0), "corner_radius", 0, 1000)
            if args.get("name") is not None: args["name"] = cls._string(args.get("name"), "name", required=False, limit=200)
        elif action == "create_text":
            args["text"] = cls._string(args.get("text"), "text", limit=10000); args["x"] = cls._number(args.get("x"), "x"); args["y"] = cls._number(args.get("y"), "y"); args["font_size"] = cls._number(args.get("font_size", 32), "font_size", 6, 1000); args["fill_hex"] = cls._hex(args.get("fill_hex"), "#111111")
            if args.get("name") is not None: args["name"] = cls._string(args.get("name"), "name", required=False, limit=200)
        elif action == "create_artboard":
            for key in ("x", "y"): args[key] = cls._number(args.get(key), key)
            for key in ("width", "height"): args[key] = cls._number(args.get(key), key, 1, 20000)
        elif action == "create_group": args = {"name": cls._string(args.get("name"), "name", limit=200)}
        elif action == "set_fill": args = {"item_name": cls._string(args.get("item_name"), "item_name", limit=200), "fill_hex": cls._hex(args.get("fill_hex"))}
        elif action == "move_item": args = {"item_name": cls._string(args.get("item_name"), "item_name", limit=200), "x": cls._number(args.get("x"), "x"), "y": cls._number(args.get("y"), "y")}
        elif action == "create_landing_mockup":
            args = {"name": cls._string(args.get("name"), "name", limit=200), "width": cls._number(args.get("width", 1440), "width", 320, 20000), "height": cls._number(args.get("height", 3000), "height", 480, 30000), "product_name": cls._string(args.get("product_name"), "product_name", limit=300), "headline": cls._string(args.get("headline"), "headline", limit=1000), "subheadline": cls._string(args.get("subheadline"), "subheadline", limit=1500), "cta": cls._string(args.get("cta"), "cta", limit=500), "accent_hex": cls._hex(args.get("accent_hex"), "#111111"), "background_hex": cls._hex(args.get("background_hex"), "#F7F3EE")}
        return DesktopActionPlan(action, args)

    @classmethod
    def validate_after_effects(cls, action: str, arguments: dict[str, Any]) -> DesktopActionPlan:
        if action not in AFTER_EFFECTS_ACTIONS: raise DesktopActionError(f"After Effects action is not allowed: {action}")
        args = dict(arguments or {})
        if action in {"inspect_project", "undo"}: return DesktopActionPlan(action, {})
        if action in {"create_composition", "create_marketing_comp"}:
            args["name"] = cls._string(args.get("name"), "name", limit=200); args["width"] = cls._integer(args.get("width"), "width", 64, 8192); args["height"] = cls._integer(args.get("height"), "height", 64, 8192); args["duration"] = cls._number(args.get("duration", 10), "duration", 0.1, 3600); args["fps"] = cls._number(args.get("fps", 30), "fps", 1, 240)
            if action == "create_marketing_comp":
                args["headline"] = cls._string(args.get("headline"), "headline", limit=1000); args["subheadline"] = cls._string(args.get("subheadline"), "subheadline", required=False, limit=1500); args["cta"] = cls._string(args.get("cta"), "cta", required=False, limit=500); args["background_hex"] = cls._hex(args.get("background_hex"), "#111111"); args["accent_hex"] = cls._hex(args.get("accent_hex"), "#FFFFFF")
        elif action == "add_text_layer":
            args["comp_name"] = cls._string(args.get("comp_name"), "comp_name", required=False, limit=200); args["name"] = cls._string(args.get("name"), "name", required=False, limit=200); args["text"] = cls._string(args.get("text"), "text", limit=10000); args["x"] = cls._number(args.get("x"), "x"); args["y"] = cls._number(args.get("y"), "y"); args["font_size"] = cls._number(args.get("font_size", 64), "font_size", 6, 1000)
        elif action in {"add_solid_layer", "add_shape_rectangle"}:
            args["comp_name"] = cls._string(args.get("comp_name"), "comp_name", required=False, limit=200); args["name"] = cls._string(args.get("name"), "name", limit=200); args["fill_hex"] = cls._hex(args.get("fill_hex"), "#111111")
            if action == "add_solid_layer": args["width"] = cls._integer(args.get("width"), "width", 1, 8192); args["height"] = cls._integer(args.get("height"), "height", 1, 8192)
            else:
                for key in ("x", "y"): args[key] = cls._number(args.get(key), key)
                for key in ("width", "height"): args[key] = cls._number(args.get(key), key, 1, 8192)
        elif action in {"set_layer_position", "set_layer_scale"}:
            args["comp_name"] = cls._string(args.get("comp_name"), "comp_name", required=False, limit=200); args["layer_name"] = cls._string(args.get("layer_name"), "layer_name", limit=200); args["x"] = cls._number(args.get("x"), "x", -50000, 50000); args["y"] = cls._number(args.get("y"), "y", -50000, 50000)
        elif action == "set_layer_opacity":
            args["comp_name"] = cls._string(args.get("comp_name"), "comp_name", required=False, limit=200); args["layer_name"] = cls._string(args.get("layer_name"), "layer_name", limit=200); args["opacity"] = cls._number(args.get("opacity"), "opacity", 0, 100)
        elif action == "add_position_keyframe":
            args["comp_name"] = cls._string(args.get("comp_name"), "comp_name", required=False, limit=200); args["layer_name"] = cls._string(args.get("layer_name"), "layer_name", limit=200); args["time"] = cls._number(args.get("time"), "time", 0, 3600); args["x"] = cls._number(args.get("x"), "x", -50000, 50000); args["y"] = cls._number(args.get("y"), "y", -50000, 50000)
        return DesktopActionPlan(action, args)

    @classmethod
    def validate(cls, app: str, action: str, arguments: dict[str, Any]) -> DesktopActionPlan:
        app = app.strip().lower().replace(" ", "_")
        if app == "blender": return cls.validate_blender(action, arguments)
        if app == "figma": return cls.validate_figma(action, arguments)
        if app == "photoshop": return cls.validate_photoshop(action, arguments)
        if app == "illustrator": return cls.validate_illustrator(action, arguments)
        if app in {"after_effects", "aftereffects"}: return cls.validate_after_effects(action, arguments)
        return DesktopActionPlan("unsupported", {}, f"No structured write adapter is installed for {app} yet.")

    async def plan(self, app: str, instruction: str, state: dict[str, Any] | None = None) -> DesktopActionPlan:
        app_norm = app.strip().lower().replace(" ", "_")
        if app_norm == "aftereffects": app_norm = "after_effects"
        allowed = APP_ACTIONS.get(app_norm)
        if not allowed:
            return DesktopActionPlan("unsupported", {}, f"No structured write adapter is installed for {app_norm} yet.")
        provider = self.router.primary()
        reply = await provider.complete(
            PLANNER_SYSTEM,
            json.dumps({"app": app_norm, "instruction": instruction, "reported_state": state or {}, "allowed_actions": allowed}, ensure_ascii=False),
        )
        raw = reply.text.strip()
        match = re.search(r"\{.*\}", raw, re.S)
        try:
            data = json.loads(match.group(0) if match else raw)
        except json.JSONDecodeError as exc:
            raise DesktopActionError("Planner returned invalid JSON") from exc
        action = str(data.get("action") or "unsupported")
        if action == "unsupported":
            return DesktopActionPlan("unsupported", {}, str(data.get("reason") or "Ambiguous or unsupported instruction")[:500])
        plan = self.validate(app_norm, action, data.get("arguments") or {})
        plan.reason = str(data.get("reason") or "")[:500]
        return plan
