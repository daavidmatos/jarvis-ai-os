from __future__ import annotations

import json
import os
from dataclasses import asdict, dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import quote

from jarvis.config import settings
from jarvis.desktop_bridge import desktop_bridge
from jarvis.router import ModelRouter


@dataclass
class UniversalWorkspaceState:
    session_id: str
    kind: str
    title: str
    target: str
    mode: str = "collaborative"
    status: str = "active"
    integration_state: str = "connector_required"
    capabilities: list[str] = field(default_factory=list)
    snapshot: dict[str, Any] = field(default_factory=dict)
    note: str | None = None
    created_at: str = ""
    updated_at: str = ""


class UniversalWorkspaceStore:
    @property
    def path(self) -> Path:
        return settings.secrets_file.parent / "universal_workspaces.json"

    def _read(self) -> dict[str, dict[str, Any]]:
        if not self.path.exists():
            return {}
        try:
            data = json.loads(self.path.read_text(encoding="utf-8"))
            return data if isinstance(data, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write(self, data: dict[str, dict[str, Any]]) -> None:
        self.path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(self.path.parent, 0o700)
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, self.path)

    def get(self, session_id: str) -> UniversalWorkspaceState | None:
        raw = self._read().get(session_id)
        return UniversalWorkspaceState(**raw) if raw else None

    def save(self, state: UniversalWorkspaceState) -> UniversalWorkspaceState:
        now = datetime.now(timezone.utc).isoformat()
        if not state.created_at:
            state.created_at = now
        state.updated_at = now
        data = self._read()
        data[state.session_id] = asdict(state)
        self._write(data)
        return state

    def close(self, session_id: str) -> UniversalWorkspaceState | None:
        state = self.get(session_id)
        if not state:
            return None
        state.status = "closed"
        return self.save(state)

    def list(self) -> list[UniversalWorkspaceState]:
        rows = [UniversalWorkspaceState(**raw) for raw in self._read().values()]
        return sorted(rows, key=lambda x: x.updated_at, reverse=True)


universal_workspace_store = UniversalWorkspaceStore()


class UniversalCollaborationHub:
    """Routes collaborative work to the right visual workspace.

    Collaboration is distinct from autonomous Mission mode. Starting a workspace
    never grants blanket execution authority. Read-only inspection is automatic;
    a concrete edit in collaborative mode authorizes only that single requested
    edit. Autonomous multi-step work remains governed by Mission envelopes.
    """

    TOGETHER_MARKERS = (
        "vamos criar",
        "vamos montar",
        "vamos fazer",
        "vamos editar",
        "vamos trabalhar",
        "vamos organizar",
        "criar junto",
        "editar junto",
        "fazer junto",
        "trabalhar junto",
        "quero criar com você",
        "quero criar com voce",
        "quero fazer com você",
        "quero fazer com voce",
    )

    TARGETS: tuple[tuple[str, tuple[str, ...], str, str, list[str]], ...] = (
        ("google_ads", ("google ads", "google ad"), "Google Ads", "cloud_api", ["inspect", "analyze", "edit", "create"]),
        ("document", ("google docs", "docs", "documento", "word", "texto"), "Documento", "cloud_connector", ["inspect", "comment", "edit", "format", "export"]),
        ("spreadsheet", ("google sheets", "sheets", "planilha", "excel"), "Planilha", "cloud_connector", ["inspect", "analyze", "edit_cells", "formula", "chart", "export"]),
        ("project_board", ("trello", "kanban", "quadro do projeto", "project board", "asana"), "Projeto", "cloud_or_desktop", ["inspect", "summarize", "move_cards", "create_tasks", "prioritize"]),
        ("design", ("photoshop", "illustrator", "figma", "adobe"), "Design", "desktop_bridge", ["inspect", "visual_review", "edit", "export"]),
        ("video_edit", ("premiere", "after effects", "after_effects"), "Edição de vídeo", "desktop_bridge", ["inspect", "timeline_review", "edit", "render"]),
        ("3d_scene", ("blender", "projeto 3d", "projeto 3d", "3d"), "Projeto 3D", "desktop_bridge", ["inspect", "scene_review", "edit", "render"]),
    )

    def __init__(self, router: ModelRouter, tools: Any):
        self.router = router
        self.tools = tools
        # Lazy import avoids a ToolRegistry <-> collaboration import cycle.
        from jarvis.collaboration import CollaborativeWorkbench, workbench_store

        self.google_ads = CollaborativeWorkbench(router, tools)
        self.google_ads_store = workbench_store

    @classmethod
    def detect_target(cls, message: str) -> dict[str, Any] | None:
        text = message.lower()
        for kind, aliases, title, transport, capabilities in cls.TARGETS:
            matched = next((alias for alias in aliases if alias in text), None)
            if matched:
                target = matched.replace(" ", "_")
                if kind == "design" and "photoshop" in text:
                    target = "photoshop"
                    title = "Photoshop"
                elif kind == "design" and "illustrator" in text:
                    target = "illustrator"
                    title = "Illustrator"
                elif kind == "design" and "figma" in text:
                    target = "figma"
                    title = "Figma"
                elif kind == "video_edit" and "premiere" in text:
                    target = "premiere"
                    title = "Premiere Pro"
                elif kind == "video_edit" and "after" in text:
                    target = "after_effects"
                    title = "After Effects"
                elif kind == "3d_scene":
                    target = "blender"
                    title = "Blender"
                elif kind == "project_board" and "trello" in text:
                    target = "trello"
                    title = "Trello"
                elif kind == "document" and "google docs" in text:
                    target = "google_docs"
                    title = "Google Docs"
                elif kind == "spreadsheet" and "google sheets" in text:
                    target = "google_sheets"
                    title = "Google Sheets"
                return {
                    "kind": kind,
                    "target": target,
                    "title": title,
                    "transport": transport,
                    "capabilities": list(capabilities),
                }
        return None

    @classmethod
    def looks_like_start(cls, message: str) -> bool:
        text = message.lower()
        return bool(cls.detect_target(message)) and any(x in text for x in cls.TOGETHER_MARKERS)

    def _workspace_url(self, session_id: str) -> str:
        return f"/static/workbench.html?session={quote(session_id)}"

    def _desktop_refresh(self, state: UniversalWorkspaceState) -> UniversalWorkspaceState:
        snapshot = desktop_bridge.snapshot_for_app(state.target)
        if snapshot:
            state.integration_state = "connected"
            state.snapshot = snapshot
            state.note = None
        else:
            state.integration_state = "desktop_bridge_required"
            state.note = (
                f"O JARVIS precisa do Desktop Bridge conectado ao {state.title} para enxergar "
                "e operar esse projeto no computador."
            )
        return universal_workspace_store.save(state)

    def _cloud_refresh(self, state: UniversalWorkspaceState) -> UniversalWorkspaceState:
        # Connector adapters for Docs/Sheets/Trello plug into this interface. Until
        # one is configured, JARVIS must never pretend it can see live project data.
        state.integration_state = "connector_required"
        state.note = (
            f"O Workbench de {state.title} está pronto, mas o conector dessa ferramenta "
            "ainda precisa ser autorizado para ler ou editar dados reais."
        )
        return universal_workspace_store.save(state)

    async def start(self, session_id: str, message: str) -> dict[str, Any] | None:
        target = self.detect_target(message)
        if not target:
            return None
        if target["kind"] == "google_ads":
            result = await self.google_ads.start(session_id)
            actions = list(result.get("actions") or [])
            actions.insert(0, {"type": "open_url", "label": "ABRIR WORKBENCH", "url": self._workspace_url(session_id)})
            result["actions"] = actions
            return result

        state = UniversalWorkspaceState(
            session_id=session_id,
            kind=target["kind"],
            title=target["title"],
            target=target["target"],
            capabilities=target["capabilities"],
            integration_state="initializing",
        )
        universal_workspace_store.save(state)
        if target["transport"] == "desktop_bridge":
            state = self._desktop_refresh(state)
        elif target["transport"] == "cloud_or_desktop":
            state = self._desktop_refresh(state)
            if state.integration_state != "connected":
                state.integration_state = "connector_required"
                state.note = (
                    f"Para trabalhar no {state.title}, conecte a API da ferramenta ou o Desktop Bridge."
                )
                universal_workspace_store.save(state)
        else:
            state = self._cloud_refresh(state)

        if state.integration_state == "connected":
            message_out = (
                f"Workbench de {state.title} aberto. Estou vendo o estado atual e vou trabalhar junto com você. "
                "Não vou assumir a execução inteira sem você pedir."
            )
        else:
            message_out = (
                f"Workbench de {state.title} aberto. Ainda não consigo ver o projeto real porque falta conectar "
                f"a integração necessária. A estrutura colaborativa está pronta; {state.note or ''}"
            )
        return {
            "message": message_out,
            "provider": "workspace",
            "model": None,
            "actions": [{"type": "open_url", "label": "ABRIR WORKBENCH", "url": self._workspace_url(session_id)}],
            "workspace": asdict(state),
        }

    @staticmethod
    def _close_like(message: str) -> bool:
        text = message.lower().strip()
        return text in {"fechar", "feche", "fechar workbench", "sair do workbench", "encerrar"}

    @staticmethod
    def _inspect_like(message: str) -> bool:
        text = message.lower()
        return any(x in text for x in ("me mostra", "mostra", "como está", "como esta", "andamento", "status", "analisa", "analisar", "veja", "olha"))

    @staticmethod
    def _explicit_single_edit(message: str) -> bool:
        text = message.lower().strip()
        if text.startswith("vamos "):
            return False
        verbs = (
            "mude ", "troque ", "adicione ", "remova ", "apague ", "delete ",
            "duplique ", "mova ", "renomeie ", "aumente ", "reduza ", "aplique ",
            "renderize ", "exporte ", "salve ", "crie ", "edite ", "corrija ",
        )
        return any(text.startswith(v) for v in verbs)

    async def _analyze_snapshot(self, state: UniversalWorkspaceState, message: str) -> tuple[str, str | None, str | None]:
        if not state.snapshot:
            return state.note or "Ainda não tenho estado real dessa ferramenta para analisar.", "workspace", None
        provider = self.router.primary()
        response = await provider.complete(
            """You are JARVIS in collaborative workspace mode. Analyze only the supplied live workspace state. Be direct and concise. State what you can actually observe, the most important issue/opportunity, and one useful next action. Never invent screen contents or project state.""",
            json.dumps({"request": message, "workspace": asdict(state)}, ensure_ascii=False),
        )
        return response.text, response.provider, response.model

    async def handle(self, session_id: str, message: str) -> dict[str, Any] | None:
        google_state = self.google_ads_store.get(session_id)
        if google_state and google_state.status == "active":
            result = await self.google_ads.handle(session_id, message)
            if result is not None:
                actions = list(result.get("actions") or [])
                actions.insert(0, {"type": "open_url", "label": "WORKBENCH", "url": self._workspace_url(session_id)})
                result["actions"] = actions
                return result

        state = universal_workspace_store.get(session_id)
        if not state or state.status != "active":
            return None
        if self._close_like(message):
            state = universal_workspace_store.close(session_id) or state
            return {
                "message": "Workbench fechado. Nenhuma alteração adicional será feita.",
                "provider": "workspace",
                "model": None,
                "actions": [],
                "workspace": asdict(state),
            }

        if state.kind in {"design", "video_edit", "3d_scene"}:
            state = self._desktop_refresh(state)
        elif state.kind == "project_board" and desktop_bridge.find_app(state.target):
            state = self._desktop_refresh(state)

        if self._explicit_single_edit(message):
            if state.integration_state != "connected":
                text = state.note or "A ferramenta ainda não está conectada para edição."
                return self._response(state, text)
            snapshot = desktop_bridge.snapshot_for_app(state.target)
            if not snapshot:
                state = self._desktop_refresh(state)
                return self._response(state, state.note or "Desktop Bridge desconectado.")
            command = await desktop_bridge.queue_command(
                snapshot["client_id"],
                state.target,
                message,
                mode="collaborative",
                approval_scope="single_command",
            )
            state.snapshot = {**state.snapshot, "pending_command": command}
            universal_workspace_store.save(state)
            return self._response(
                state,
                "Comando enviado ao Desktop Bridge. Essa autorização vale somente para esta alteração; vou atualizar o painel quando o aplicativo confirmar o resultado.",
            )

        if self._inspect_like(message):
            text, provider, model = await self._analyze_snapshot(state, message)
            result = self._response(state, text)
            result["provider"] = provider
            result["model"] = model
            return result

        return self._response(
            state,
            "Estou no modo colaborativo. Posso revisar o estado atual, discutir uma alteração ou executar uma mudança específica que você mandar.",
        )

    def _response(self, state: UniversalWorkspaceState, message: str) -> dict[str, Any]:
        return {
            "message": message,
            "provider": "workspace",
            "model": None,
            "actions": [{"type": "open_url", "label": "WORKBENCH", "url": self._workspace_url(state.session_id)}],
            "workspace": asdict(state),
        }

    async def handle_or_start(self, session_id: str, message: str) -> dict[str, Any] | None:
        active = await self.handle(session_id, message)
        if active is not None:
            return active
        if self.looks_like_start(message):
            return await self.start(session_id, message)
        return None

    def get_workspace(self, session_id: str) -> dict[str, Any] | None:
        google_state = self.google_ads_store.get(session_id)
        if google_state and google_state.status == "active":
            return self.google_ads._workbench_payload(google_state)
        state = universal_workspace_store.get(session_id)
        return asdict(state) if state else None

    def list_workspaces(self) -> list[dict[str, Any]]:
        rows = [asdict(x) for x in universal_workspace_store.list()]
        return rows

    def capability_catalog(self) -> list[dict[str, Any]]:
        bridge = desktop_bridge.status()
        items = []
        for kind, aliases, title, transport, capabilities in self.TARGETS:
            if kind == "google_ads":
                readiness = "connector_required"
            elif transport == "desktop_bridge":
                readiness = "connected" if any(desktop_bridge.find_app(alias.replace(" ", "_")) for alias in aliases) else "desktop_bridge_required"
            else:
                readiness = "connector_required"
            items.append({
                "kind": kind,
                "title": title,
                "transport": transport,
                "capabilities": capabilities,
                "readiness": readiness,
            })
        return items
