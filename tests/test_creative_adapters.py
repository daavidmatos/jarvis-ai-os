from __future__ import annotations

import json
from pathlib import Path
from xml.etree import ElementTree

import pytest

from jarvis.desktop_actions import DesktopActionError, DesktopActionPlanner
from jarvis.desktop_bridge import DesktopBridge


ROOT = Path(__file__).resolve().parents[1]


def test_figma_landing_page_action_is_bounded():
    plan = DesktopActionPlanner.validate_figma(
        "create_landing_page",
        {
            "name": "Cream landing",
            "product_name": "Aura Cream",
            "headline": "Cuidado simples para todos os dias",
            "subheadline": "Uma rotina objetiva.",
            "cta": "Conhecer",
            "accent_hex": "111111",
            "background_hex": "F7F3EE",
        },
    )
    assert plan.action == "create_landing_page"
    assert plan.arguments["accent_hex"] == "#111111"
    assert plan.arguments["sections"]


def test_figma_existing_node_edits_require_target():
    with pytest.raises(DesktopActionError):
        DesktopActionPlanner.validate_figma("delete_node", {})


def test_photoshop_marketing_canvas_validation():
    plan = DesktopActionPlanner.validate_photoshop(
        "create_marketing_canvas",
        {
            "name": "Launch",
            "width": 1080,
            "height": 1350,
            "headline": "Novo produto",
            "subheadline": "Conheça agora",
            "cta": "Comprar",
        },
    )
    assert plan.arguments["width"] == 1080
    assert plan.arguments["background_hex"].startswith("#")


def test_illustrator_landing_mockup_validation():
    plan = DesktopActionPlanner.validate_illustrator(
        "create_landing_mockup",
        {
            "name": "Landing",
            "product_name": "Cream",
            "headline": "Pele simples, rotina simples",
            "subheadline": "Mockup",
            "cta": "Ver produto",
        },
    )
    assert plan.arguments["width"] == 1440
    assert plan.arguments["height"] == 3000


def test_after_effects_marketing_comp_validation():
    plan = DesktopActionPlanner.validate_after_effects(
        "create_marketing_comp",
        {
            "name": "Cream launch",
            "width": 1080,
            "height": 1920,
            "duration": 8,
            "fps": 30,
            "headline": "Novo creme",
        },
    )
    assert plan.arguments["duration"] == 8
    assert plan.arguments["fps"] == 30


def test_unlisted_creative_action_is_rejected():
    with pytest.raises(DesktopActionError):
        DesktopActionPlanner.validate_photoshop("run_script", {"code": "alert(1)"})


def test_bridge_prefers_dedicated_write_adapter():
    bridge = DesktopBridge()
    bridge.register(
        "screen-observer",
        "Linux",
        apps=["figma"],
        state={"adapter": {"name": "screen", "write": False}},
    )
    bridge.register(
        "figma-plugin",
        "Figma",
        apps=["figma"],
        state={"adapter": {"name": "jarvis-figma", "write": True}},
    )
    assert bridge.find_app("figma").client_id == "figma-plugin"


def test_adapter_manifests_are_parseable():
    figma = json.loads((ROOT / "creative_adapters" / "figma" / "manifest.json").read_text())
    photoshop = json.loads((ROOT / "creative_adapters" / "photoshop" / "manifest.json").read_text())
    ElementTree.parse(ROOT / "creative_adapters" / "adobe_cep" / "CSXS" / "manifest.xml")
    assert figma["name"].startswith("JARVIS")
    assert photoshop["host"]["app"] == "PS"


def test_creative_adapter_entrypoints_exist():
    paths = [
        ROOT / "creative_adapters" / "figma" / "code.js",
        ROOT / "creative_adapters" / "figma" / "ui.html",
        ROOT / "creative_adapters" / "photoshop" / "index.js",
        ROOT / "creative_adapters" / "adobe_cep" / "panel.js",
        ROOT / "creative_adapters" / "adobe_cep" / "jsx" / "bridge.jsx",
    ]
    assert all(path.exists() and path.stat().st_size > 100 for path in paths)
