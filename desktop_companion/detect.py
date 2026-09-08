from __future__ import annotations

import os
import platform
import subprocess
from dataclasses import dataclass
from pathlib import Path
from typing import Iterable


PROCESS_ALIASES: dict[str, tuple[str, ...]] = {
    "blender": ("blender",),
    "photoshop": ("photoshop", "photoshop.exe"),
    "illustrator": ("illustrator", "illustrator.exe"),
    "premiere": ("adobe premiere pro", "premiere pro", "adobe premiere pro.exe"),
    "after_effects": ("afterfx", "afterfx.exe", "after effects"),
    "figma": ("figma", "figma.exe"),
}


@dataclass
class DesktopObservation:
    platform: str
    apps: list[str]
    active_app: str | None
    active_document: str | None
    active_window_title: str | None


def canonical_apps(process_names: Iterable[str]) -> list[str]:
    normalized = [str(x).strip().lower() for x in process_names if str(x).strip()]
    found: list[str] = []
    for app, aliases in PROCESS_ALIASES.items():
        if any(any(alias in proc for alias in aliases) for proc in normalized):
            found.append(app)
    return found


def _linux_processes() -> list[str]:
    try:
        result = subprocess.run(
            ["ps", "-eo", "comm="],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
        return [x.strip() for x in result.stdout.splitlines() if x.strip()]
    except Exception:
        return []


def _windows_processes() -> list[str]:
    try:
        result = subprocess.run(
            ["tasklist", "/FO", "CSV", "/NH"],
            check=False,
            capture_output=True,
            text=True,
            timeout=4,
        )
        rows = []
        for line in result.stdout.splitlines():
            line = line.strip().strip('"')
            if line:
                rows.append(line.split('","', 1)[0])
        return rows
    except Exception:
        return []


def _mac_processes() -> list[str]:
    try:
        result = subprocess.run(
            ["ps", "-axo", "comm="],
            check=False,
            capture_output=True,
            text=True,
            timeout=3,
        )
        return [Path(x.strip()).name for x in result.stdout.splitlines() if x.strip()]
    except Exception:
        return []


def process_names() -> list[str]:
    system = platform.system().lower()
    if system == "linux":
        return _linux_processes()
    if system == "windows":
        return _windows_processes()
    if system == "darwin":
        return _mac_processes()
    return []


def _active_window_linux() -> tuple[str | None, str | None]:
    # xdotool works on X11/XWayland. On strict Wayland this intentionally fails
    # closed and process detection remains available.
    try:
        wid = subprocess.run(
            ["xdotool", "getactivewindow"],
            check=True,
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip()
        title = subprocess.run(
            ["xdotool", "getwindowname", wid],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip() or None
        wmclass = subprocess.run(
            ["xdotool", "getwindowclassname", wid],
            check=False,
            capture_output=True,
            text=True,
            timeout=2,
        ).stdout.strip().lower()
        app = canonical_apps([wmclass])[0] if canonical_apps([wmclass]) else None
        return app, title
    except Exception:
        return None, None


def _active_window_windows() -> tuple[str | None, str | None]:
    try:
        import ctypes

        user32 = ctypes.windll.user32
        hwnd = user32.GetForegroundWindow()
        length = user32.GetWindowTextLengthW(hwnd)
        buf = ctypes.create_unicode_buffer(length + 1)
        user32.GetWindowTextW(hwnd, buf, length + 1)
        title = buf.value or None
        app = None
        if title:
            app_list = canonical_apps([title])
            app = app_list[0] if app_list else None
        return app, title
    except Exception:
        return None, None


def active_window() -> tuple[str | None, str | None]:
    system = platform.system().lower()
    if system == "linux":
        return _active_window_linux()
    if system == "windows":
        return _active_window_windows()
    return None, None


def observe(blender_state: dict | None = None) -> DesktopObservation:
    apps = canonical_apps(process_names())
    active_app, title = active_window()
    active_document = None
    if blender_state and blender_state.get("available"):
        if "blender" not in apps:
            apps.append("blender")
        if active_app is None and blender_state.get("is_active"):
            active_app = "blender"
        active_document = blender_state.get("project") or blender_state.get("scene")
    return DesktopObservation(
        platform=f"{platform.system()} {platform.release()}",
        apps=sorted(set(apps)),
        active_app=active_app,
        active_document=active_document,
        active_window_title=title,
    )
