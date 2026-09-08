from __future__ import annotations

import platform
import re
import shutil
import subprocess
from pathlib import Path


def blender_config_roots() -> list[Path]:
    system = platform.system().lower()
    home = Path.home()
    roots: list[Path] = []
    if system == "linux":
        roots.append(home / ".config" / "blender")
    elif system == "darwin":
        roots.append(home / "Library" / "Application Support" / "Blender")
    elif system == "windows":
        appdata = Path.home() / "AppData" / "Roaming"
        roots.append(appdata / "Blender Foundation" / "Blender")
    return roots


def _blender_version_from_binary() -> str | None:
    try:
        out = subprocess.run(
            ["blender", "--version"],
            check=False,
            capture_output=True,
            text=True,
            timeout=5,
        ).stdout
        match = re.search(r"Blender\s+(\d+\.\d+)", out)
        return match.group(1) if match else None
    except Exception:
        return None


def discover_addon_dirs() -> list[Path]:
    candidates: list[Path] = []
    for root in blender_config_roots():
        if root.exists():
            for child in root.iterdir():
                if child.is_dir() and re.fullmatch(r"\d+\.\d+", child.name):
                    candidates.append(child / "scripts" / "addons")
    if not candidates:
        version = _blender_version_from_binary()
        roots = blender_config_roots()
        if version and roots:
            candidates.append(roots[0] / version / "scripts" / "addons")
    return sorted(set(x.resolve() for x in candidates))


def install_blender_addon() -> list[Path]:
    source = Path(__file__).resolve().parent / "blender_addon"
    if not (source / "__init__.py").exists():
        raise RuntimeError("Bundled Blender add-on is missing.")
    targets = discover_addon_dirs()
    if not targets:
        raise RuntimeError(
            "No Blender installation/config folder was found. Open Blender once, close it, and run this command again."
        )
    installed: list[Path] = []
    for addons_dir in targets:
        addons_dir.mkdir(parents=True, exist_ok=True)
        target = addons_dir / "jarvis_bridge"
        shutil.copytree(source, target, dirs_exist_ok=True)
        installed.append(target)
    return installed
