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
        text = re.sub(r"\s+", " ", message.lower().strip())
        if "uber" not in text:
            return False

        # Speech transcription frequently changes the imperative "peça" into
        # first-person forms such as "peço". Treat common natural rider phrases as
        # one intent instead of falling back to generic LLM chat.
        action_markers = (
            "peça", "peca", "peço", "peco", "pedir", "pede", "pedi um uber",
            "chame", "chama", "chamar", "me chama", "me chame",
            "solicite", "solicitar", "solicita", "manda um uber", "mande um uber",
            "quero um uber", "preciso de um uber", "preciso dum uber",
            "corrida", "me leve", "me leva", "levar me", "leve me",
            "ir para", "ir pro", "ir pra", "quero ir", "vou para", "vou pro", "vou pra",
        )
        if any(marker in text for marker in action_markers):
            return True

        # If Uber is mentioned together with a clear destination preposition, the
        # user's intent is operational enough to route to mobility even when the
        # speech recognizer omitted the exact request verb.
        return bool(re.search(r"\buber\b.*\b(?:para|pra|pro|ao|à)\b\s+\S+", text, re.I))

    @staticmethod
    def _clean_destination(value: str) -> str | None:
        value = value.strip(" .,!?:;\"'")
        value = re.sub(r"^(?:o|a|os|as)\s+", "", value, flags=re.I)
        return value if len(value) >= 2 else None

    @classmethod
    def _destination(cls, message: str) -> str | None:
        text = re.sub(r"\s+", " ", message.strip())
        patterns = (
            r"(?:para|pra)\s+ir\s+(?:para|pro|pra|ao|à)\s+(.+)$",
            r"(?:quero\s+ir|me\s+leve|me\s+leva|levar\s+me|leve\s+me)\s+(?:para|pro|pra|ao|à)\s+(.+)$",
            r"(?:uber|corrida).*?\s(?:para|pro|pra|ao|à)\s+(.+)$",
        )
        for pattern in patterns:
            match = re.search(pattern, text, re.I)
            if match:
                value = cls._clean_destination(match.group(1))
                if value:
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
