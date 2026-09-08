from __future__ import annotations

import platform
import subprocess
import sys
from pathlib import Path


SERVICE_NAME = "jarvis-desktop.service"


def service_text() -> str:
    repo_root = Path(__file__).resolve().parent.parent
    python = Path(sys.executable).resolve()
    return f"""[Unit]
Description=JARVIS Desktop Companion
After=network-online.target
Wants=network-online.target

[Service]
Type=simple
WorkingDirectory={repo_root}
ExecStart={python} -m desktop_companion run
Restart=always
RestartSec=5
Environment=PYTHONUNBUFFERED=1

[Install]
WantedBy=default.target
"""


def install_user_service(start: bool = True) -> Path:
    if platform.system().lower() != "linux":
        raise RuntimeError("Automatic service installation is currently implemented for Linux/systemd only.")
    folder = Path("~/.config/systemd/user").expanduser().resolve()
    folder.mkdir(parents=True, exist_ok=True)
    path = folder / SERVICE_NAME
    path.write_text(service_text(), encoding="utf-8")
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=True)
    command = ["systemctl", "--user", "enable"]
    if start:
        command.append("--now")
    command.append(SERVICE_NAME)
    subprocess.run(command, check=True)
    return path


def remove_user_service() -> None:
    if platform.system().lower() != "linux":
        raise RuntimeError("Automatic service removal is currently implemented for Linux/systemd only.")
    subprocess.run(["systemctl", "--user", "disable", "--now", SERVICE_NAME], check=False)
    path = Path("~/.config/systemd/user").expanduser().resolve() / SERVICE_NAME
    if path.exists():
        path.unlink()
    subprocess.run(["systemctl", "--user", "daemon-reload"], check=False)
