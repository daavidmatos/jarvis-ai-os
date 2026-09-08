from __future__ import annotations

import re
from urllib.parse import urlencode
from uuid import UUID

from jarvis.voice_persona import ensure_senhor


class MobilityAssistant:
    """Mobile ride-request handoff for services such as Uber.

    The public Uber rider deep link can start a ride-request flow with pickup and
    destination prefilled. It does not bypass Uber's own fare/category/final request
    confirmation, so JARVIS must never claim the ride was booked from the deep link.
    """

    def __init__(self, db):
        self.db = db

    @staticmethod
    def looks_like_request(message: str) -> bool:
        text = message.lower().strip()
        if "uber" not in text:
            return False
        verbs = (
            "peça", "peca", "pedir", "pede", "chame", "chama", "chamar",
            "solicite", "solicitar", "corrida", "me leve", "ir para", "ir pro",
            "ir pra", "quero ir",
        )
        return any(v in text for v in verbs)

    @staticmethod
    def _destination(message: str) -> str | None:
        text = re.sub(r"\s+", " ", message.strip())
        patterns = (
            r"(?:para|pra)\s+ir\s+(?:para|pro|pra|ao|à)\s+(.+)$",
            r"(?:quero\s+ir|me\s+leve|levar\s+me|leve\s+me)\s+(?:para|pro|pra|ao|à)\s+(.+)$",
            r"(?:uber|corrida).*?\s(?:para|pro|pra|ao|à)\s+(.+)$",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                value = match.group(1).strip(" .,!?:;\"'")
                if len(value) >= 2:
                    return value
        return None

    @staticmethod
    def _uber_url(destination: str, location: dict) -> str:
        params = {
            "pickup[latitude]": f"{float(location['latitude']):.7f}",
            "pickup[longitude]": f"{float(location['longitude']):.7f}",
            "pickup[nickname]": "Minha localização",
            "dropoff[nickname]": destination,
            "dropoff[formatted_address]": destination,
        }
        return "uber://riderequest?" + urlencode(params)

    async def handle(
        self,
        sid: UUID,
        message: str,
        location: dict | None,
    ) -> dict:
        destination = self._destination(message)
        wid = self.db.create_workflow(
            sid,
            message,
            {"type": "mobility", "provider": "uber", "destination": destination},
        )

        if not destination:
            text = ensure_senhor("Para onde o senhor quer ir de Uber?")
            self.db.finish_workflow(wid, "completed", {"message": text})
            return {
                "workflow_id": wid,
                "session_id": sid,
                "status": "completed",
                "message": text,
                "provider": "uber",
                "model": None,
                "sources": [],
                "actions": [],
            }

        if not location:
            text = ensure_senhor(
                "Preciso da sua localização atual para preparar o embarque. "
                "Autorize a localização e eu continuo a solicitação."
            )
            actions = [
                {
                    "type": "request_location",
                    "label": "USAR LOCALIZAÇÃO",
                    "auto": False,
                }
            ]
            self.db.finish_workflow(
                wid,
                "completed",
                {"message": text, "destination": destination, "needs_location": True},
            )
            return {
                "workflow_id": wid,
                "session_id": sid,
                "status": "completed",
                "message": text,
                "provider": "uber",
                "model": None,
                "sources": [],
                "actions": actions,
            }

        url = self._uber_url(destination, location)
        text = ensure_senhor(
            f"Vou abrir o Uber com o embarque na sua localização atual e o destino "
            f"{destination}. A categoria, a tarifa e a solicitação final ainda precisam "
            "ser confirmadas dentro do Uber."
        )
        actions = [
            {
                "type": "open_url",
                "label": "ABRIR UBER",
                "url": url,
                "auto": False,
            }
        ]
        self.db.finish_workflow(
            wid,
            "completed",
            {
                "message": text,
                "destination": destination,
                "pickup": {
                    "latitude": location.get("latitude"),
                    "longitude": location.get("longitude"),
                },
                "handoff": "uber_deep_link",
            },
        )
        self.db.audit(
            "mobility.uber.prepared",
            {"destination": destination},
            wid,
        )
        return {
            "workflow_id": wid,
            "session_id": sid,
            "status": "completed",
            "message": text,
            "provider": "uber",
            "model": None,
            "sources": [],
            "actions": actions,
        }
