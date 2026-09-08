from __future__ import annotations

from uuid import UUID

from jarvis.voice_persona import ensure_senhor


INTERNET_SYSTEM = """You are JARVIS Internet Research.
Use ONLY the supplied live web search evidence for factual claims about current prices,
stock, stores, products, services, news, websites or other time-sensitive information.
If evidence is incomplete, say so briefly instead of filling gaps from memory.
Be concise, practical and address the user as 'senhor'. Prefer a direct recommendation
when the evidence supports one. Do not claim to have entered an account, added items to a
cart, placed an order or completed any external action unless the tool result proves it.
Answer in Brazilian Portuguese unless the user explicitly asks for another language.
"""


class InternetAssistant:
    """Low-latency path for explicit live-web requests.

    Research commands must never silently fall back to model memory. Natural voice
    phrasing such as "quem é X, pesquise para mim" therefore routes here even when the
    user does not literally say "na internet".
    """

    def __init__(self, router, tools, db):
        self.router = router
        self.tools = tools
        self.db = db

    @staticmethod
    def looks_like_request(message: str) -> bool:
        text = message.lower().strip()
        explicit = (
            "pesquise na internet",
            "pesquisa na internet",
            "procure na internet",
            "busque na internet",
            "pesquise online",
            "procure online",
            "busque online",
            "pesquise na web",
            "procure na web",
            "busque na web",
            "veja na internet",
            "olhe na internet",
        )
        fresh = (
            "preço agora",
            "preco agora",
            "preço atual",
            "preco atual",
            "estoque agora",
            "estoque atual",
            "onde comprar",
            "onde encontro para comprar",
            "onde encontro pra comprar",
            "qual loja vende",
            "site oficial",
        )
        commerce = (
            "ifood",
            "mercado online",
            "supermercado online",
            "delivery",
        )
        research_verbs = ("pesquise", "pesquisar", "busque", "buscar")
        commerce_verbs = (
            "pesquise", "pesquisar", "procure", "procurar", "busque", "buscar",
            "ache", "encontre",
        )
        return (
            any(x in text for x in explicit)
            or any(x in text for x in fresh)
            or any(v in text for v in research_verbs)
            or (any(x in text for x in commerce) and any(v in text for v in commerce_verbs))
        )

    async def research(self, sid: UUID, message: str, context: str) -> dict:
        search = await self.tools.execute("web.search", query=message, max_results=6)
        payload = search.get("result", {}) if search.get("ok") else {}
        results = payload.get("results", []) or []
        provider_name = payload.get("provider")

        wid = self.db.create_workflow(
            sid,
            message,
            {"type": "internet_research", "search_provider": provider_name},
        )

        if not results:
            text = ensure_senhor(
                "Não consegui obter resultados ao vivo da internet agora. "
                "Não vou substituir isso por uma resposta inventada ou desatualizada."
            )
            self.db.finish_workflow(
                wid,
                "failed",
                {"message": text, "search_provider": provider_name, "results": []},
            )
            return {
                "workflow_id": wid,
                "session_id": sid,
                "status": "failed",
                "message": text,
                "provider": provider_name,
                "model": None,
                "sources": [],
                "actions": [],
            }

        evidence_rows = []
        for index, item in enumerate(results, start=1):
            evidence_rows.append(
                f"[{index}] {item.get('title') or 'Resultado'}\n"
                f"URL: {item.get('url') or '(sem URL)'}\n"
                f"Trecho: {item.get('snippet') or '(sem trecho)'}"
            )
        evidence = "\n\n".join(evidence_rows)
        provider = self.router.primary()
        reply = await provider.complete(
            INTERNET_SYSTEM,
            (
                f"Conversation context:\n{context}\n\n"
                f"User request:\n{message}\n\n"
                f"LIVE WEB SEARCH EVIDENCE:\n{evidence}"
            ),
            temperature=0.1,
        )
        text = ensure_senhor(reply.text)
        actions = [
            {
                "type": "open_url",
                "label": (item.get("title") or "ABRIR")[:36],
                "url": item.get("url"),
                "auto": False,
            }
            for item in results[:3]
            if item.get("url")
        ]
        self.db.finish_workflow(
            wid,
            "completed",
            {
                "message": text,
                "search_provider": provider_name,
                "result_count": len(results),
            },
        )
        self.db.audit(
            "internet.search",
            {"provider": provider_name, "result_count": len(results)},
            wid,
        )
        return {
            "workflow_id": wid,
            "session_id": sid,
            "status": "completed",
            "message": text,
            "provider": reply.provider,
            "model": reply.model,
            "sources": results,
            "actions": actions,
        }
