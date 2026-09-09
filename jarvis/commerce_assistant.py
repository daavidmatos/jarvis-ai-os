from __future__ import annotations

import re
from uuid import UUID

from jarvis.config import settings
from jarvis.integrations.browserless_agent import BrowserlessAgentError, browserless_agent
from jarvis.voice_persona import ensure_senhor


class CommerceAssistant:
    """Execution-first commerce handoff for iFood.

    The assistant may browse, compare, open a restaurant and prepare a cart. It must
    stop before the final purchase/payment action unless a future explicitly approved
    high-risk transaction tool is used.
    """

    def __init__(self, db):
        self.db = db

    @staticmethod
    def looks_like_request(message: str) -> bool:
        text = re.sub(r"\s+", " ", message.lower().strip())
        if "ifood" not in text:
            return False
        operational = (
            "faça um pedido", "faca um pedido", "fazer um pedido", "pedido pra mim",
            "pedido para mim", "peça", "peca", "pedir", "pede", "quero pedir",
            "compre", "comprar", "adicione", "coloque no carrinho", "monte o carrinho",
            "abra", "entre", "procure", "busque", "encontre", "cardápio", "cardapio",
        )
        return any(x in text for x in operational) or "ifood" in text

    @staticmethod
    def _explicit_item_request(message: str) -> bool:
        text = message.lower()
        item_markers = (
            "pizza de", "hambúrguer", "hamburguer", "combo", "refrigerante", "coca",
            "porção", "porcao", "prato", "lanche", "item", "quero uma", "quero um",
        )
        return any(x in text for x in item_markers)

    async def handle(self, sid: UUID, message: str, location: dict | None = None) -> dict:
        wid = self.db.create_workflow(
            sid,
            message,
            {"type": "commerce_prepare", "provider": "ifood"},
        )

        if not browserless_agent.status()["configured"]:
            text = ensure_senhor(
                "O fluxo do iFood foi reconhecido, mas o navegador autônomo ainda não está conectado. "
                "Quando o Browserless for conectado, eu consigo entrar no iFood, localizar o restaurante, "
                "ler o cardápio e montar o carrinho; a confirmação final do pagamento continua com o senhor."
            )
            actions = [
                {
                    "type": "open_url",
                    "label": "ABRIR IFOOD",
                    "url": "https://www.ifood.com.br/",
                    "auto": False,
                }
            ]
            self.db.finish_workflow(
                wid,
                "blocked",
                {"message": text, "blocker": "browserless_not_configured"},
            )
            return {
                "workflow_id": wid,
                "session_id": sid,
                "status": "blocked",
                "message": text,
                "provider": "ifood",
                "model": None,
                "sources": [],
                "actions": actions,
            }

        has_items = self._explicit_item_request(message)
        task = (
            "You are operating iFood for the account owner. Follow the user's request exactly. "
            "Navigate the real iFood website and use only information visible there. "
            "You MAY search restaurants, open menus, compare items/prices and add reversible items to the cart. "
            "DO NOT click the final order/place-order/payment/confirm-purchase action. Stop before any irreversible "
            "purchase or payment. If login, SMS, 2FA or a human-only choice is required, stop and say exactly what is needed. "
        )
        if has_items:
            task += (
                "The user appears to have specified items. Try to prepare the cart with those exact items and report the cart subtotal, "
                "delivery fee and total if visible, then stop before final confirmation. "
            )
        else:
            task += (
                "The user did not specify a concrete menu item. Locate the requested restaurant, inspect the real menu, return up to three "
                "relevant options with visible prices, and ask which one to add. Do not guess menu items. "
            )
        task += f"\nUser request: {message}"

        try:
            run = await browserless_agent.run(
                task,
                start_url="https://www.ifood.com.br/",
                allowed_domains=["ifood.com.br", "www.ifood.com.br"],
                profile=settings.browserless_ifood_profile,
                max_steps=24,
                timeout_ms=90000,
            )
        except BrowserlessAgentError as exc:
            text = ensure_senhor(f"Tentei operar o iFood, mas o navegador retornou: {exc}")
            self.db.finish_workflow(wid, "failed", {"message": text})
            return {
                "workflow_id": wid,
                "session_id": sid,
                "status": "failed",
                "message": text,
                "provider": "browserless_ifood",
                "model": None,
                "sources": [],
                "actions": [
                    {
                        "type": "open_url",
                        "label": "ABRIR IFOOD",
                        "url": "https://www.ifood.com.br/",
                        "auto": False,
                    }
                ],
            }

        data = run.get("data") or {}
        answer = data.get("answer") if isinstance(data, dict) else None
        text = ensure_senhor(str(answer or "Concluí a etapa de preparação no iFood."))
        steps = run.get("steps") or []
        self.db.finish_workflow(
            wid,
            "completed",
            {"message": text, "run_id": run.get("id"), "steps": steps[-8:]},
        )
        self.db.audit(
            "commerce.ifood.prepare",
            {"run_id": run.get("id"), "step_count": len(steps)},
            wid,
        )
        return {
            "workflow_id": wid,
            "session_id": sid,
            "status": "completed",
            "message": text,
            "provider": "browserless_ifood",
            "model": "browserless_agent",
            "sources": [],
            "actions": [
                {
                    "type": "open_url",
                    "label": "ABRIR IFOOD",
                    "url": "https://www.ifood.com.br/",
                    "auto": False,
                }
            ],
        }
