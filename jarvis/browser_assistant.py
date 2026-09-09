from __future__ import annotations

import re
from urllib.parse import quote_plus
from uuid import UUID

from jarvis.voice_persona import ensure_senhor


class BrowserAssistant:
    """Direct browser handoff for explicit user-visible navigation/search commands."""

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
            "abra no google", "abre no google", "abrir no google",
            "abra o google", "abre o google", "abrir o google",
            "abra google", "abre google", "abrir google",
        )
        google_visual = (
            "pesquise aqui no google", "pesquisa aqui no google",
            "pesquise no google", "pesquisa no google", "procure no google",
            "busque no google", "quero ver o resultado no google",
            "quero ver os resultados no google", "mostre no google",
        )
        google_chain = bool(
            re.search(
                r"\b(?:abra|abre|abrir)\s+(?:o\s+)?google\b.*\b(?:pesquise|pesquisa|procure|busque|buscar|pesquisar)\b",
                text,
                re.I,
            )
        )
        return (
            any(x in text for x in tab_markers)
            or any(x in text for x in browser_markers)
            or any(x in text for x in google_visual)
            or google_chain
        )

    @staticmethod
    def _query(message: str) -> str | None:
        text = re.sub(r"\s+", " ", message.strip())
        # Remove conversational suffixes about wanting to see the result in Google.
        text = re.sub(
            r"\s+e\s+eu\s+quero\s+ver\s+(?:o|os)\s+resultados?\s+(?:dentro\s+do|no)\s+google\.?$",
            "",
            text,
            flags=re.I,
        )
        # Prefer the explicit search clause wherever it appears. This correctly handles
        # natural commands such as "Abra o Google e pesquise por televisões" instead
        # of treating "Google e pesquise..." as the query.
        search_match = re.search(
            r"(?:pesquise|pesquisa|pesquisar|procure|buscar|busque)\s+(?:aqui\s+)?(?:no\s+google\s+)?(?:por\s+)?(.+)$",
            text,
            re.I,
        )
        if search_match:
            query = search_match.group(1).strip(" .,!?:;\"'")
            if query:
                return query

        open_search = re.search(
            r"(?:abra|abre|abrir)\s+(?:o\s+)?google\s+(?:e\s+)?(?:uma\s+busca\s+)?(?:por\s+)?(.+)$",
            text,
            re.I,
        )
        if open_search:
            query = open_search.group(1).strip(" .,!?:;\"'")
            if query and query.lower() not in {"google", "o google"}:
                return query
        return None

    @classmethod
    def _target_url(cls, message: str) -> tuple[str, str | None]:
        query = cls._query(message)
        if query:
            return f"https://www.google.com/search?q={quote_plus(query)}&hl=pt-BR", query
        return "https://www.google.com/", None

    async def handle(self, sid: UUID, message: str) -> dict:
        url, query = self._target_url(message)
        wid = self.db.create_workflow(
            sid,
            message,
            {"type": "browser_tab", "query": query, "url": url},
        )
        if query:
            text = ensure_senhor(f"Abrindo o Google e pesquisando por {query}.")
        else:
            text = ensure_senhor("Abrindo o Google no navegador.")
        actions = [
            {
                "type": "open_url",
                "label": "ABRIR GOOGLE" if query else "ABRIR GUIA",
                "url": url,
                "auto": True,
                "same_tab_fallback": True,
            }
        ]
        self.db.finish_workflow(wid, "completed", {"message": text, "url": url, "query": query})
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
