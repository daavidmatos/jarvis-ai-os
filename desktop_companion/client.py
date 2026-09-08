from __future__ import annotations

import asyncio
import json
import time
from dataclasses import asdict
from typing import Any

from desktop_companion.blender_ipc import BlenderIPC
from desktop_companion.capture import capture_primary_monitor
from desktop_companion.config import CompanionConfig
from desktop_companion.detect import observe


class DesktopCompanion:
    def __init__(self, config: CompanionConfig):
        self.config = config
        self.blender = BlenderIPC()
        self.pending_commands: dict[str, dict[str, Any]] = {}
        self._last_capture = 0.0

    def current_state(self) -> dict[str, Any]:
        blender_state = self.blender.state()
        obs = observe(blender_state)
        return {
            "apps": obs.apps,
            "active_app": obs.active_app,
            "active_document": obs.active_document,
            "state": {
                "active_window_title": obs.active_window_title,
                "blender": blender_state,
            },
            "platform": obs.platform,
        }

    async def _hello(self, ws) -> None:
        state = self.current_state()
        await ws.send(
            json.dumps(
                {
                    "type": "hello",
                    "client_id": self.config.ensure_client_id(),
                    **state,
                },
                ensure_ascii=False,
            )
        )

    async def _state_loop(self, ws) -> None:
        while True:
            state = self.current_state()
            await ws.send(json.dumps({"type": "state", **state}, ensure_ascii=False))
            await self._maybe_send_frame(ws, state)
            await asyncio.sleep(max(0.75, float(self.config.state_interval)))

    async def _maybe_send_frame(self, ws, state: dict[str, Any]) -> None:
        if not self.config.screenshots:
            return
        visual_apps = {"blender", "photoshop", "illustrator", "premiere", "after_effects", "figma"}
        apps = set(state.get("apps") or [])
        active = state.get("active_app")
        if active not in visual_apps and not apps.intersection(visual_apps):
            return
        now = time.monotonic()
        if now - self._last_capture < max(2.0, float(self.config.capture_interval)):
            return
        self._last_capture = now
        try:
            frame = await asyncio.to_thread(
                capture_primary_monitor,
                self.config.max_frame_width,
                self.config.jpeg_quality,
            )
        except Exception as exc:
            await ws.send(
                json.dumps(
                    {
                        "type": "state",
                        **state,
                        "state": {
                            **(state.get("state") or {}),
                            "frame_capture_error": str(exc),
                        },
                    },
                    ensure_ascii=False,
                )
            )
            return
        await ws.send(json.dumps(frame.to_message()))

    async def _send_result(
        self,
        ws,
        command_id: str,
        *,
        ok: bool,
        result: dict[str, Any] | None = None,
        error: str | None = None,
    ) -> None:
        state = self.current_state()
        await ws.send(
            json.dumps(
                {
                    "type": "result",
                    "command_id": command_id,
                    "ok": ok,
                    "result": result or {},
                    "error": error,
                    **state,
                },
                ensure_ascii=False,
            )
        )

    async def _handle_command(self, ws, message: dict[str, Any]) -> None:
        command_id = str(message.get("command_id") or "")
        app = str(message.get("app") or "").strip().lower()
        instruction = str(message.get("instruction") or "").strip()
        if not command_id or not app or not instruction:
            return
        if app != "blender":
            await self._send_result(
                ws,
                command_id,
                ok=False,
                error=(
                    f"No structured write adapter is installed for {app}. "
                    "JARVIS may inspect screenshots/state, but cannot safely edit this app yet."
                ),
            )
            return
        state = self.blender.state()
        if not state.get("available"):
            await self._send_result(
                ws,
                command_id,
                ok=False,
                error=str(state.get("reason") or "Blender add-on is not available."),
            )
            return
        self.pending_commands[command_id] = message
        await ws.send(
            json.dumps(
                {
                    "type": "plan_request",
                    "command_id": command_id,
                    "app": "blender",
                    "instruction": instruction,
                    "state": state,
                },
                ensure_ascii=False,
            )
        )

    async def _handle_plan_response(self, ws, message: dict[str, Any]) -> None:
        command_id = str(message.get("command_id") or "")
        pending = self.pending_commands.pop(command_id, None)
        if not pending:
            return
        plan = message.get("plan") if isinstance(message.get("plan"), dict) else {}
        action = str(plan.get("action") or "unsupported")
        arguments = plan.get("arguments") if isinstance(plan.get("arguments"), dict) else {}
        if action == "unsupported":
            await self._send_result(
                ws,
                command_id,
                ok=False,
                error=str(plan.get("reason") or "Instruction is ambiguous or unsupported."),
            )
            return
        try:
            self.blender.queue_action(command_id, action, arguments)
            result = await asyncio.to_thread(self.blender.wait_result, command_id, 90.0)
        except Exception as exc:
            await self._send_result(ws, command_id, ok=False, error=str(exc))
            return
        await self._send_result(
            ws,
            command_id,
            ok=bool(result.get("ok")),
            result=result,
            error=None if result.get("ok") else str(result.get("error") or "Blender action failed"),
        )

    async def _receive_loop(self, ws) -> None:
        async for raw in ws:
            try:
                message = json.loads(raw)
            except Exception:
                continue
            kind = str(message.get("type") or "")
            if kind == "command":
                await self._handle_command(ws, message)
            elif kind == "plan_response":
                await self._handle_plan_response(ws, message)
            elif kind == "ping":
                await ws.send(json.dumps({"type": "pong"}))

    async def run_forever(self, *, allow_insecure_remote: bool = False) -> None:
        try:
            from websockets.asyncio.client import connect
        except ImportError as exc:
            raise RuntimeError(
                "Desktop Companion dependencies are missing. Install requirements-desktop.txt."
            ) from exc

        url = self.config.websocket_url(allow_insecure_remote=allow_insecure_remote)
        delay = 1.0
        while True:
            try:
                async with connect(
                    url,
                    ping_interval=20,
                    ping_timeout=20,
                    max_size=8 * 1024 * 1024,
                    close_timeout=5,
                ) as ws:
                    await self._hello(ws)
                    delay = 1.0
                    async with asyncio.TaskGroup() as tg:
                        tg.create_task(self._state_loop(ws))
                        tg.create_task(self._receive_loop(ws))
            except asyncio.CancelledError:
                raise
            except KeyboardInterrupt:
                return
            except Exception as exc:
                print(f"[JARVIS Desktop] conexão indisponível: {exc}")
                await asyncio.sleep(delay)
                delay = min(delay * 2.0, 30.0)
