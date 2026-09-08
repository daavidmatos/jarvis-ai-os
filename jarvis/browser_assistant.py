from __future__ import annotations

import re
from urllib.parse import quote_plus
from uuid import UUID

from jarvis.voice_persona import ensure_senhor


class BrowserAssistant:
    """Direct browser-tab handoff for the mobile/web JARVIS client.

    This is intentionally separate from future remote browser automation. It can open
    a new browser tab and prefill a Google search immediately, but it does not pretend
    to click through arbitrary websites or authenticated accounts on its own.
    """

    def __init__(self, db):
        self.db = db

    @staticmethod
    def looks_like_request(message: str) -> bool:
        text = re.sub(r"\s+", " ", message.lower().strip())
        tab_markers = (
            "nova guia", "nova aba", "outra guia", "outra aba",
            "guia no navegador", "aba no navegador",
        )
        browser_markers = (
            "abra o navegador", "abre o navegador", "abrir o navegador",
            "abra uma guia", "abre uma guia", "abra uma aba", "abre uma aba",
        )
        return any(x in text for x in tab_markers) or any(x in text for x in browser_markers)

    @staticmethod
    def _query(message: str) -> str | None:
        text = re.sub(r"\s+", " ", message.strip())
        patterns = (
            r"(?:pesquise|pesquisa|pesquisar|procure|buscar|busque)\s+(?:por\s+)?(.+)$",
            r"(?:e\s+)?(?:pesquise|pesquisa|procure|busque)\s+(?:por\s+)?(.+)$",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                query = match.group(1).strip(" .,!?:;\"'")
                if query:
                    return query
        return None

    @classmethod
    def _target_url(cls, message: str) -> tuple[str, str | None]:
        query = cls._query(message)
        if query:
            return f"https://www.google.com/search?q={quote_plus(query)}", query
        return "https://www.google.com/", None

    async def handle(self, sid: UUID, message: str) -> dict:
        url, query = self._target_url(message)
        wid = self.db.create_workflow(
            sid,
            message,
            {"type": "browser_tab", "query": query, "url": url},
        )
        if query:
            text = ensure_senhor(f"Abrindo uma nova guia e pesquisando por {query}.")
        else:
            text = ensure_senhor("Abrindo uma nova guia no navegador.")
        actions = [
            {
                "type": "open_url",
                "label": "ABRIR GUIA",
                "url": url,
                "auto": True,
            }
        ]
        self.db.finish_workflow(
            wid,
            "completed",
            {"message": text, "url": url, "query": query},
        )
        self.db.audit("browser.tab.open", {"query": query}, wid)
        return {
            "workflow_id": wid,
            "session_id": sid,
            "status": "completed",
            "message": text,
            "provider": "browser",
            "model": None,
            "sources": [],
            "actions": actions,
        }
