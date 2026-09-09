from __future__ import annotations

import re
from uuid import UUID

from jarvis.google_workspace import GoogleWorkspaceError, google_workspace
from jarvis.integrations.google_content import DOCS_BASE, SHEETS_BASE, google_content
from jarvis.voice_persona import ensure_senhor


class ContentAssistant:
    """Direct, explicit creation path for Google Docs and Sheets."""

    def __init__(self, router, db):
        self.router = router
        self.db = db

    @staticmethod
    def looks_like_request(message: str) -> bool:
        text = " ".join(message.lower().split())
        create = any(x in text for x in ("crie", "cria", "criar", "faça", "faca", "monte"))
        target = any(x in text for x in ("documento", "google docs", "doc ", "planilha", "google sheets", "spreadsheet"))
        return create and target

    @staticmethod
    def _kind(message: str) -> str:
        text = message.lower()
        return "spreadsheet" if any(x in text for x in ("planilha", "google sheets", "spreadsheet")) else "document"

    @staticmethod
    def _title(message: str, kind: str) -> str:
        patterns = (
            r"(?:chamad[oa]|com o nome|nomeado|intitulado)\s+[\"']?([^\"']+?)[\"']?(?:\.|$)",
            r"(?:sobre|para)\s+(.+?)(?:\.|$)",
        )
        for pattern in patterns:
            m = re.search(pattern, message, re.I)
            if m:
                value = m.group(1).strip(" .,:;\"'")
                if 2 <= len(value) <= 80:
                    return value[:80]
        return "Planilha JARVIS" if kind == "spreadsheet" else "Documento JARVIS"

    async def _draft_document(self, message: str, title: str) -> str:
        provider = self.router.primary()
        reply = await provider.complete(
            """Você é o JARVIS criando conteúdo para um Google Doc solicitado explicitamente pelo usuário.
Escreva em português brasileiro. Entregue somente o conteúdo do documento, sem explicar o processo.
Se o pedido for vago, crie uma estrutura curta e útil. Não invente dados factuais específicos que o usuário não forneceu.""",
            f"Título: {title}\nPedido: {message}",
            temperature=0.2,
        )
        return reply.text.strip()

    async def handle(self, sid: UUID, message: str) -> dict:
        kind = self._kind(message)
        status = google_content.status()
        wid = self.db.create_workflow(sid, message, {"type": "content_create", "kind": kind})
        required = status.get("sheets_scope") if kind == "spreadsheet" else status.get("docs_scope")
        if not status.get("connected") or not required:
            text = ensure_senhor(
                "Reconheci que o senhor quer criar o arquivo, mas a conta Google ainda precisa ser conectada/reconectada uma vez. "
                "Depois disso eu crio e edito Docs e Sheets diretamente, sem o senhor precisar montar o arquivo manualmente."
            )
            self.db.finish_workflow(wid, "blocked", {"message": text, "blocker": "google_content_oauth"})
            return {
                "workflow_id": wid,
                "session_id": sid,
                "status": "blocked",
                "message": text,
                "provider": "google_workspace",
                "model": None,
                "sources": [],
                "actions": [{"type": "open_url", "label": "CONECTAR GOOGLE", "url": "/v1/integrations/google/connect", "auto": False}],
            }

        title = self._title(message, kind)
        try:
            if kind == "spreadsheet":
                created = await google_workspace.request(
                    "POST",
                    f"{SHEETS_BASE}/spreadsheets",
                    json={"properties": {"title": title}},
                )
                file_id = created.get("spreadsheetId")
                url = f"https://docs.google.com/spreadsheets/d/{file_id}/edit"
                text = ensure_senhor(f"Planilha {title} criada. Já deixei o arquivo pronto para edição.")
            else:
                created = await google_workspace.request("POST", f"{DOCS_BASE}/documents", json={"title": title})
                file_id = created.get("documentId")
                content = await self._draft_document(message, title)
                if content and file_id:
                    await google_workspace.request(
                        "POST",
                        f"{DOCS_BASE}/documents/{file_id}:batchUpdate",
                        json={"requests": [{"insertText": {"location": {"index": 1}, "text": content}}]},
                    )
                url = f"https://docs.google.com/document/d/{file_id}/edit"
                text = ensure_senhor(f"Documento {title} criado e preenchido. Está pronto para o senhor revisar ou continuar editando comigo.")
        except GoogleWorkspaceError as exc:
            text = ensure_senhor(f"Tentei criar o arquivo no Google, mas a integração respondeu: {exc}")
            self.db.finish_workflow(wid, "failed", {"message": text})
            return {
                "workflow_id": wid,
                "session_id": sid,
                "status": "failed",
                "message": text,
                "provider": "google_workspace",
                "model": None,
                "sources": [],
                "actions": [],
            }

        self.db.finish_workflow(wid, "completed", {"message": text, "file_id": file_id, "url": url})
        self.db.audit("content.created", {"kind": kind, "file_id": file_id}, wid)
        return {
            "workflow_id": wid,
            "session_id": sid,
            "status": "completed",
            "message": text,
            "provider": "google_workspace",
            "model": None,
            "sources": [],
            "actions": [{"type": "open_url", "label": "ABRIR ARQUIVO", "url": url, "auto": False}],
        }
