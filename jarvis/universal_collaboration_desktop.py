from __future__ import annotations

import json
from dataclasses import asdict
from typing import Any

from jarvis.desktop_actions import DesktopActionPlanner
from jarvis.desktop_bridge import desktop_bridge
from jarvis.desktop_frames import DesktopFrameError, desktop_frames
from jarvis.universal_collaboration import UniversalWorkspaceState, universal_workspace_store
from jarvis.universal_collaboration_v2 import (
    EnhancedUniversalCollaborationHub as CloudEnhancedUniversalCollaborationHub,
)


class EnhancedUniversalCollaborationHub(CloudEnhancedUniversalCollaborationHub):
    """Universal Workbench with cloud collaboration + real Desktop Companion vision."""

    def __init__(self, router, tools):
        super().__init__(router, tools)
        self.desktop_planner = DesktopActionPlanner(router)

    async def _analyze_snapshot(
        self, state: UniversalWorkspaceState, message: str
    ) -> tuple[str, str | None, str | None]:
        if not state.snapshot:
            return (
                state.note or "Ainda não tenho estado real dessa ferramenta para analisar.",
                "workspace",
                None,
            )
        provider = self.router.primary()
        payload = json.dumps(
            {"request": message, "workspace": state.snapshot},
            ensure_ascii=False,
        )
        frame = state.snapshot.get("frame") if isinstance(state.snapshot, dict) else None
        storage_key = frame.get("storage_key") if isinstance(frame, dict) else None
        if storage_key and hasattr(provider, "complete_vision"):
            try:
                image = desktop_frames.read(str(storage_key))
                response = await provider.complete_vision(
                    """You are JARVIS visually reviewing a live desktop application in collaborative mode.
Use BOTH the screenshot and reported application state. Be direct and concise. State what is actually visible,
the most important issue/opportunity, and one useful next action. Never invent hidden layers, geometry,
timeline content, values, or controls you cannot see. If the screenshot is insufficient, say so.""",
                    payload,
                    image,
                    str(frame.get("mime_type") or "image/jpeg"),
                )
                return response.text, response.provider, response.model
            except (DesktopFrameError, OSError, RuntimeError, ValueError):
                pass
        response = await provider.complete(
            """You are JARVIS in collaborative workspace mode. Analyze only the supplied live application state.
Be direct and concise. State what you can actually observe, the most important issue/opportunity, and one useful
next action. No screenshot is available, so never claim visual details.""",
            payload,
        )
        return response.text, response.provider, response.model

    async def _desktop_single_edit(
        self,
        state: UniversalWorkspaceState,
        message: str,
    ) -> dict[str, Any]:
        state = self._desktop_refresh(state)
        if state.integration_state != "connected":
            return self._response(state, state.note or "Desktop Bridge desconectado.")
        snapshot = desktop_bridge.snapshot_for_app(state.target)
        if not snapshot:
            return self._response(state, "Desktop Bridge desconectado.")
        plan = await self.desktop_planner.plan(
            state.target,
            message,
            snapshot.get("state") if isinstance(snapshot.get("state"), dict) else {},
        )
        if plan.action == "unsupported":
            return self._response(
                state,
                plan.reason
                or f"Ainda não há um adaptador de edição segura para {state.title}. Posso inspecionar o estado visual, mas não vou simular uma edição.",
            )
        command = await desktop_bridge.queue_command(
            snapshot["client_id"],
            state.target,
            message,
            mode="collaborative",
            approval_scope="single_command",
            plan=plan.to_dict(),
        )
        state.snapshot = {**snapshot, "pending_command": command}
        universal_workspace_store.save(state)
        return self._response(
            state,
            f"Entendi a alteração e enviei uma ação estruturada ao {state.title}. A autorização vale somente para este comando; o painel será atualizado após a confirmação local.",
        )

    async def handle(self, session_id: str, message: str) -> dict[str, Any] | None:
        state = universal_workspace_store.get(session_id)
        if (
            state
            and state.status == "active"
            and state.kind in {"design", "video_edit", "3d_scene"}
            and self._explicit_single_edit(message)
        ):
            return await self._desktop_single_edit(state, message)
        return await super().handle(session_id, message)

    def get_workspace(self, session_id: str) -> dict[str, Any] | None:
        state = universal_workspace_store.get(session_id)
        if state and state.status == "active" and state.kind in {"design", "video_edit", "3d_scene"}:
            state = self._desktop_refresh(state)
            return asdict(state)
        return super().get_workspace(session_id)
