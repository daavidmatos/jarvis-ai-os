from __future__ import annotations

import argparse
import asyncio

from desktop_companion.client import DesktopCompanion
from desktop_companion.config import CompanionConfig
from desktop_companion.install import install_blender_addon


def _parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(prog="python -m desktop_companion", description="JARVIS Desktop Companion")
    sub = p.add_subparsers(dest="command", required=True)

    configure = sub.add_parser("configure", help="Save the JARVIS server connection once")
    configure.add_argument("--server", required=True, help="JARVIS base URL, e.g. https://jarvis.example.com")
    configure.add_argument("--token", default="", help="Desktop Bridge token; required for hosted mode")
    configure.add_argument("--screenshots", action="store_true", help="Allow bounded visual-app screenshots")

    run = sub.add_parser("run", help="Run the persistent desktop companion")
    run.add_argument("--allow-insecure-remote", action="store_true")

    sub.add_parser("status", help="Show local companion/Blender readiness")
    sub.add_parser("install-blender-addon", help="Install/update the bundled JARVIS Blender add-on")
    return p


def main() -> None:
    args = _parser().parse_args()
    if args.command == "configure":
        cfg = CompanionConfig.load()
        cfg.server_url = args.server
        cfg.token = args.token
        cfg.screenshots = bool(args.screenshots)
        path = cfg.save()
        print(f"Configuração salva em {path}")
        print("Capturas de tela: " + ("ATIVADAS" if cfg.screenshots else "DESATIVADAS"))
        return

    if args.command == "install-blender-addon":
        targets = install_blender_addon()
        for target in targets:
            print(f"Add-on instalado: {target}")
        print("Abra/reinicie o Blender e habilite 'JARVIS Desktop Bridge' em Preferences > Add-ons.")
        return

    cfg = CompanionConfig.load()
    companion = DesktopCompanion(cfg)
    if args.command == "status":
        print("Servidor:", cfg.server_url)
        print("Client ID:", cfg.client_id)
        print("Screenshots:", "on" if cfg.screenshots else "off")
        print("Blender:", companion.blender.state())
        print("Desktop:", companion.current_state())
        return

    if args.command == "run":
        asyncio.run(companion.run_forever(allow_insecure_remote=bool(args.allow_insecure_remote)))


if __name__ == "__main__":
    main()
