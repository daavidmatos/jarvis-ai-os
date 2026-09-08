from __future__ import annotations

import json
import re
from typing import Any

from jarvis.integrations.google_content import GoogleContentError, google_content
from jarvis.integrations.trello import TrelloError, trello
from jarvis.universal_collaboration import (
    UniversalCollaborationHub,
    UniversalWorkspaceState,
    universal_workspace_store,
)


CLOUD_WORKBENCH_SYSTEM = """You are JARVIS interpreting one turn inside a collaborative workspace.
The workspace may be Google Docs, Google Sheets, or Trello. Collaboration is NOT blanket autonomous permission.
Return ONLY valid JSON:
{
  "intent":"select|inspect|analyze|doc_append|doc_replace|sheet_update|sheet_append|trello_move|trello_create|trello_update|discuss|close",
  "target_name":null,
  "target_id":null,
  "old_text":null,
  "new_text":null,
  "text":null,
  "range_a1":null,
  "values":[],
  "card_name":null,
  "card_id":null,
  "list_name":null,
  "list_id":null,
  "description":null,
  "due":null,
  "reply":"short direct reply"
}
Rules:
- Never invent IDs, file names, card names, list names, cell ranges, or existing content.
- "vamos mudar/editar" alone is discussion, not permission to mutate.
- A mutation intent is valid only if this exact user message specifies a concrete edit.
- "me mostra", "como está", "analisa" are read-only.
- If several files/boards exist and the user did not identify one, use inspect/discuss and ask which one.
- For Sheets, only output sheet_update/sheet_append if a concrete A1 range or unambiguous row append is requested.
- Keep reply concise.
"""


class EnhancedUniversalCollaborationHub(UniversalCollaborationHub):
    """Universal hub with live cloud adapters for Docs, Sheets and Trello."""

    @staticmethod
    def _explicit_cloud_edit(message: str) -> bool:
        text = message.lower().strip()
        if text.startswith("vamos "):
            return False
        starts = (
            "mude ", "troque ", "adicione ", "adicione", "remova ", "apague ",
            "delete ", "mova ", "renomeie ", "coloque ", "insira ", "substitua ",
            "preencha ", "atualize ", "crie ", "edite ", "corrija ", "append ",
        )
        if any(text.startswith(x) for x in starts):
            return True
        patterns = (
            "quero que você mude", "quero que voce mude",
            "quero que você adicione", "quero que voce adicione",
            "quero que você remova", "quero que voce remova",
            "quero que você mova", "quero que voce mova",
            "pode mudar", "pode adicionar", "pode remover", "pode mover",
        )
        return any(x in text for x in patterns)

    async def _cloud_command(self, state: UniversalWorkspaceState, message: str) -> dict[str, Any]:
        provider = self.router.primary()
        reply = await provider.complete(
            CLOUD_WORKBENCH_SYSTEM,
            json.dumps(
                {"message": message, "workspace": state.snapshot, "kind": state.kind},
                ensure_ascii=False,
            ),
        )
        raw = reply.text.strip()
        match = re.search(r"\{.*\}", raw, re.S)
        data = json.loads(match.group(0) if match else raw)
        data["provider"] = reply.provider
        data["model"] = reply.model
        return data

    @staticmethod
    def _pick(rows: list[dict[str, Any]], target_id: str | None, target_name: str | None) -> dict[str, Any] | None:
        if target_id:
            row = next((x for x in rows if str(x.get("id")) == str(target_id)), None)
            if row:
                return row
        if target_name:
            wanted = target_name.strip().lower()
            exact = next((x for x in rows if str(x.get("name") or x.get("title") or "").lower() == wanted), None)
            if exact:
                return exact
            partial = [x for x in rows if wanted in str(x.get("name") or x.get("title") or "").lower()]
            if len(partial) == 1:
                return partial[0]
        return None

    async def _open_google_content(self, state: UniversalWorkspaceState) -> UniversalWorkspaceState:
        status = google_content.status()
        required = status["docs_scope"] if state.kind == "document" else status["sheets_scope"]
        if not status["connected"] or not required or not status["drive_scope"]:
            state.integration_state = "connector_required"
            state.note = (
                "Conecte/reconecte a conta Google para autorizar Drive, Docs e Sheets. "
                "O JARVIS não vai fingir que consegue ver arquivos sem esses escopos."
            )
            return universal_workspace_store.save(state)
        try:
            files = await google_content.recent_files(state.kind, 15)
        except GoogleContentError as exc:
            state.integration_state = "connector_error"
            state.note = str(exc)
            return universal_workspace_store.save(state)
        state.integration_state = "connected"
        selected = state.snapshot.get("selected") if isinstance(state.snapshot, dict) else None
        state.snapshot = {"candidates": files, "selected": selected}
        state.note = None
        return universal_workspace_store.save(state)

    async def _open_trello(self, state: UniversalWorkspaceState) -> UniversalWorkspaceState:
        if not trello.status()["configured"]:
            state.integration_state = "connector_required"
            state.note = "Conecte a conta Trello para o JARVIS ler e editar quadros reais."
            return universal_workspace_store.save(state)
        try:
            boards = await trello.boards()
        except TrelloError as exc:
            state.integration_state = "connector_error"
            state.note = str(exc)
            return universal_workspace_store.save(state)
        state.integration_state = "connected"
        selected = state.snapshot.get("selected") if isinstance(state.snapshot, dict) else None
        state.snapshot = {"candidates": boards, "selected": selected}
        state.note = None
        return universal_workspace_store.save(state)

    async def start(self, session_id: str, message: str) -> dict[str, Any] | None:
        target = self.detect_target(message)
        if not target or target["kind"] == "google_ads":
            return await super().start(session_id, message)

        if target["kind"] in {"document", "spreadsheet", "project_board"}:
            state = UniversalWorkspaceState(
                session_id=session_id,
                kind=target["kind"],
                title=target["title"],
                target=target["target"],
                capabilities=target["capabilities"],
                integration_state="initializing",
            )
            universal_workspace_store.save(state)
            if target["kind"] in {"document", "spreadsheet"}:
                state = await self._open_google_content(state)
            elif target["target"] == "trello":
                state = await self._open_trello(state)
            else:
                # Generic project boards can still fall back to the desktop bridge.
                return await super().start(session_id, message)
            if state.integration_state == "connected":
                count = len(state.snapshot.get("candidates", []))
                text = (
                    f"Workbench de {state.title} aberto. Encontrei {count} item(ns) recente(s). "
                    "Escolha um ou diga o nome; eu consigo revisar e editar junto com você."
                )
            else:
                text = f"Workbench de {state.title} aberto. {state.note or ''}"
            return self._response(state, text)
        return await super().start(session_id, message)

    async def _select_google(self, state: UniversalWorkspaceState, cmd: dict[str, Any]) -> tuple[UniversalWorkspaceState, str]:
        candidates = list(state.snapshot.get("candidates", []))
        selected = self._pick(candidates, cmd.get("target_id"), cmd.get("target_name"))
        if not selected:
            names = [str(x.get("name")) for x in candidates[:8] if x.get("name")]
            return state, "Qual arquivo você quer abrir? " + ("Recentes: " + "; ".join(names) if names else "Não encontrei arquivos recentes.")
        try:
            detail = (
                await google_content.document(selected["id"])
                if state.kind == "document"
                else await google_content.spreadsheet(selected["id"])
            )
        except GoogleContentError as exc:
            return state, str(exc)
        state.snapshot["selected"] = detail
        universal_workspace_store.save(state)
        return state, f"{detail.get('title') or selected.get('name')} aberto no Workbench."

    async def _select_trello(self, state: UniversalWorkspaceState, cmd: dict[str, Any]) -> tuple[UniversalWorkspaceState, str]:
        candidates = list(state.snapshot.get("candidates", []))
        selected = self._pick(candidates, cmd.get("target_id"), cmd.get("target_name"))
        if not selected:
            names = [str(x.get("name")) for x in candidates[:8] if x.get("name")]
            return state, "Qual quadro você quer abrir? " + ("Recentes: " + "; ".join(names) if names else "Não encontrei quadros.")
        try:
            detail = await trello.board(selected["id"])
        except TrelloError as exc:
            return state, str(exc)
        state.snapshot["selected"] = detail
        universal_workspace_store.save(state)
        return state, f"Quadro {selected.get('name')} aberto no Workbench."

    async def _analyze_cloud(self, state: UniversalWorkspaceState, message: str) -> tuple[str, str | None, str | None]:
        selected = state.snapshot.get("selected") if isinstance(state.snapshot, dict) else None
        if not selected:
            return "Escolha primeiro o arquivo ou quadro que você quer analisar.", "workspace", None
        provider = self.router.primary()
        reply = await provider.complete(
            """You are JARVIS collaborating on a live document, spreadsheet or project board. Analyze only the supplied snapshot. Be concise and practical. For a project board, identify progress, bottlenecks and next action. For documents, identify structure/content issues. For spreadsheets, identify data/formula/pattern issues only when visible in the supplied cells. Never invent hidden data.""",
            json.dumps({"request": message, "kind": state.kind, "snapshot": selected}, ensure_ascii=False),
        )
        return reply.text, reply.provider, reply.model

    async def _mutate_document(self, state: UniversalWorkspaceState, cmd: dict[str, Any]) -> str:
        selected = state.snapshot.get("selected") or {}
        file_id = selected.get("id")
        if not file_id:
            return "Abra um documento antes de editar."
        intent = cmd.get("intent")
        try:
            if intent == "doc_append":
                text = str(cmd.get("text") or "")
                if not text:
                    return "Qual texto você quer adicionar?"
                await google_content.document_append(file_id, text)
            elif intent == "doc_replace":
                old = str(cmd.get("old_text") or "")
                new = str(cmd.get("new_text") or "")
                if not old:
                    return "Qual trecho exato você quer substituir?"
                await google_content.document_replace(file_id, old, new)
            else:
                return "Essa edição de documento ainda não tem um comando seguro implementado."
            state.snapshot["selected"] = await google_content.document(file_id)
            universal_workspace_store.save(state)
            return "Documento atualizado e Workbench sincronizado."
        except GoogleContentError as exc:
            return f"Não consegui editar o documento: {exc}"

    async def _mutate_sheet(self, state: UniversalWorkspaceState, cmd: dict[str, Any]) -> str:
        selected = state.snapshot.get("selected") or {}
        file_id = selected.get("id")
        if not file_id:
            return "Abra uma planilha antes de editar."
        range_a1 = str(cmd.get("range_a1") or "")
        values = cmd.get("values")
        if not range_a1 or not isinstance(values, list) or not values:
            return "Para alterar a planilha, preciso de um intervalo/célula claro e dos valores que devem entrar."
        try:
            if cmd.get("intent") == "sheet_append":
                await google_content.spreadsheet_append(file_id, range_a1, values)
            else:
                await google_content.spreadsheet_update(file_id, range_a1, values)
            state.snapshot["selected"] = await google_content.spreadsheet(file_id)
            universal_workspace_store.save(state)
            return "Planilha atualizada e Workbench sincronizado."
        except GoogleContentError as exc:
            return f"Não consegui editar a planilha: {exc}"

    @staticmethod
    def _trello_find(selected: dict[str, Any], kind: str, ident: str | None, name: str | None) -> dict[str, Any] | None:
        rows = selected.get("cards" if kind == "card" else "lists", [])
        if ident:
            found = next((x for x in rows if str(x.get("id")) == str(ident)), None)
            if found:
                return found
        if name:
            wanted = name.lower().strip()
            exact = next((x for x in rows if str(x.get("name") or "").lower() == wanted), None)
            if exact:
                return exact
            partial = [x for x in rows if wanted in str(x.get("name") or "").lower()]
            if len(partial) == 1:
                return partial[0]
        return None

    async def _mutate_trello(self, state: UniversalWorkspaceState, cmd: dict[str, Any]) -> str:
        selected = state.snapshot.get("selected") or {}
        board = selected.get("board") or {}
        if not board.get("id"):
            return "Abra um quadro Trello antes de editar."
        intent = cmd.get("intent")
        try:
            if intent == "trello_move":
                card = self._trello_find(selected, "card", cmd.get("card_id"), cmd.get("card_name"))
                target_list = self._trello_find(selected, "list", cmd.get("list_id"), cmd.get("list_name"))
                if not card or not target_list:
                    return "Preciso identificar claramente o card e a lista de destino."
                await trello.move_card(card["id"], target_list["id"])
            elif intent == "trello_create":
                target_list = self._trello_find(selected, "list", cmd.get("list_id"), cmd.get("list_name"))
                name = str(cmd.get("card_name") or "").strip()
                if not target_list or not name:
                    return "Qual card devo criar e em qual lista?"
                await trello.create_card(target_list["id"], name, cmd.get("description"), cmd.get("due"))
            elif intent == "trello_update":
                card = self._trello_find(selected, "card", cmd.get("card_id"), cmd.get("card_name"))
                if not card:
                    return "Qual card você quer atualizar?"
                await trello.update_card(card["id"], description=cmd.get("description"), due=cmd.get("due"))
            else:
                return "Essa alteração do Trello ainda não tem um comando seguro implementado."
            state.snapshot["selected"] = await trello.board(board["id"])
            universal_workspace_store.save(state)
            return "Trello atualizado e Workbench sincronizado."
        except TrelloError as exc:
            return f"Não consegui alterar o Trello: {exc}"

    async def handle(self, session_id: str, message: str) -> dict[str, Any] | None:
        state = universal_workspace_store.get(session_id)
        if not state or state.status != "active" or state.kind not in {"document", "spreadsheet", "project_board"}:
            return await super().handle(session_id, message)

        if self._close_like(message):
            return await super().handle(session_id, message)
        if state.integration_state != "connected":
            return self._response(state, state.note or "A integração ainda não está conectada.")

        cmd = await self._cloud_command(state, message)
        intent = str(cmd.get("intent") or "discuss")
        provider = cmd.get("provider")
        model = cmd.get("model")

        if intent == "select":
            if state.kind in {"document", "spreadsheet"}:
                state, text = await self._select_google(state, cmd)
            else:
                state, text = await self._select_trello(state, cmd)
            result = self._response(state, text)
        elif intent in {"inspect", "analyze"}:
            text, provider, model = await self._analyze_cloud(state, message)
            result = self._response(state, text)
        elif intent in {"doc_append", "doc_replace", "sheet_update", "sheet_append", "trello_move", "trello_create", "trello_update"}:
            if not self._explicit_cloud_edit(message):
                result = self._response(
                    state,
                    "Entendi a ideia, mas não alterei nada. Diga a mudança concreta que você quer fazer e eu aplico somente essa alteração.",
                )
            elif state.kind == "document":
                result = self._response(state, await self._mutate_document(state, cmd))
            elif state.kind == "spreadsheet":
                result = self._response(state, await self._mutate_sheet(state, cmd))
            else:
                result = self._response(state, await self._mutate_trello(state, cmd))
        else:
            result = self._response(state, str(cmd.get("reply") or "Estou trabalhando junto com você nesse workspace."))
        result["provider"] = provider or result.get("provider")
        result["model"] = model
        result["workspace"] = self.get_workspace(session_id)
        return result
