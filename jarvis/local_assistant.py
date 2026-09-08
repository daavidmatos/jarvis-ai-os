from __future__ import annotations

import json
import math
import os
import re
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Any
from urllib.parse import urlencode

import httpx

from jarvis.config import settings
from jarvis.router import ModelRouter


PLACES_TEXT_SEARCH_URL = "https://places.googleapis.com/v1/places:searchText"


class LocalAssistantError(RuntimeError):
    pass


@dataclass
class LocalPlace:
    place_id: str
    name: str
    address: str
    latitude: float | None
    longitude: float | None
    distance_m: int | None
    rating: float | None
    rating_count: int
    price_level: str | None
    open_now: bool | None
    business_status: str | None
    website: str | None
    photo_count: int
    review_count_sample: int
    review_rating_sample: float | None
    review_snippets: list[str]
    maps_place_url: str | None
    maps_directions_url: str | None
    maps_reviews_url: str | None
    maps_photos_url: str | None
    quality_score: float
    confidence_score: float

    def public_dict(self) -> dict[str, Any]:
        return asdict(self)


class GooglePlacesClient:
    FIELD_MASK = ",".join(
        [
            "places.id",
            "places.displayName",
            "places.formattedAddress",
            "places.location",
            "places.rating",
            "places.userRatingCount",
            "places.priceLevel",
            "places.currentOpeningHours",
            "places.businessStatus",
            "places.websiteUri",
            "places.photos",
            "places.reviews",
            "places.googleMapsLinks",
        ]
    )

    def status(self) -> dict[str, Any]:
        return {
            "configured": bool(settings.google_maps_api_key),
            "provider": "google_places_new",
            "location_required": True,
        }

    @staticmethod
    def _haversine_m(lat1: float, lon1: float, lat2: float, lon2: float) -> int:
        radius = 6_371_000.0
        p1 = math.radians(lat1)
        p2 = math.radians(lat2)
        dp = math.radians(lat2 - lat1)
        dl = math.radians(lon2 - lon1)
        a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
        return int(radius * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a)))

    @staticmethod
    def _review_text(review: dict[str, Any]) -> str:
        text = review.get("text")
        if isinstance(text, dict):
            return str(text.get("text") or "").strip()
        return str(text or "").strip()

    @staticmethod
    def _score(
        rating: float | None,
        rating_count: int,
        distance_m: int | None,
        open_now: bool | None,
        photo_count: int,
        review_count_sample: int,
        website: str | None,
    ) -> tuple[float, float]:
        """Return recommendation utility and evidence confidence.

        Sparse data lowers confidence, not assumed restaurant quality. Rating is
        Bayesian-shrunk toward a neutral-good prior so a new 5.0/3-review place
        cannot automatically outrank a well-established 4.6/1500-review place.
        """
        count = max(int(rating_count or 0), 0)
        observed = float(rating) if rating is not None else 4.2
        prior_rating = 4.2
        prior_weight = 80.0
        bayes = (count * observed + prior_weight * prior_rating) / (count + prior_weight)

        rating_component = max(0.0, min(1.0, (bayes - 3.2) / 1.8)) * 70.0
        volume_component = min(math.log10(count + 1) / 3.2, 1.0) * 10.0
        evidence_component = min(photo_count / 10.0, 1.0) * 4.0
        evidence_component += min(review_count_sample / 5.0, 1.0) * 4.0
        evidence_component += 2.0 if website else 0.0
        open_component = 4.0 if open_now is True else (-2.0 if open_now is False else 0.0)

        distance_penalty = 0.0
        if distance_m is not None:
            # Mild penalty only: quality should dominate, but a much closer place
            # can win when evidence is otherwise similar.
            distance_penalty = min(distance_m / 1000.0, 10.0) * 0.9

        quality = max(0.0, min(100.0, rating_component + volume_component + evidence_component + open_component - distance_penalty))

        review_conf = min(math.log10(count + 1) / 3.0, 1.0)
        completeness = (
            (1.0 if rating is not None else 0.0)
            + min(photo_count / 5.0, 1.0)
            + min(review_count_sample / 3.0, 1.0)
            + (1.0 if website else 0.0)
        ) / 4.0
        confidence = max(15.0, min(100.0, 30.0 + review_conf * 50.0 + completeness * 20.0))
        return round(quality, 1), round(confidence, 1)

    async def search(
        self,
        query: str,
        latitude: float,
        longitude: float,
        radius_m: int | None = None,
        max_results: int = 5,
        open_now: bool = False,
    ) -> list[LocalPlace]:
        if not settings.google_maps_api_key:
            raise LocalAssistantError(
                "Google Places ainda não está configurado no servidor. Defina GOOGLE_MAPS_API_KEY."
            )
        radius = min(max(int(radius_m or settings.places_default_radius_m), 100), 50_000)
        page_size = min(max(int(max_results), 1), 10)
        body: dict[str, Any] = {
            "textQuery": query,
            "pageSize": page_size,
            "languageCode": "pt-BR",
            "regionCode": "BR",
            "locationBias": {
                "circle": {
                    "center": {"latitude": latitude, "longitude": longitude},
                    "radius": float(radius),
                }
            },
        }
        if open_now:
            body["openNow"] = True
        headers = {
            "Content-Type": "application/json",
            "X-Goog-Api-Key": settings.google_maps_api_key,
            "X-Goog-FieldMask": self.FIELD_MASK,
        }
        async with httpx.AsyncClient(timeout=30) as client:
            response = await client.post(PLACES_TEXT_SEARCH_URL, json=body, headers=headers)
        if response.status_code >= 400:
            raise LocalAssistantError(f"Google Places HTTP {response.status_code}: {response.text[:500]}")

        places: list[LocalPlace] = []
        for row in response.json().get("places", []):
            location = row.get("location") or {}
            plat = location.get("latitude")
            plon = location.get("longitude")
            distance = None
            if isinstance(plat, (int, float)) and isinstance(plon, (int, float)):
                distance = self._haversine_m(latitude, longitude, float(plat), float(plon))

            reviews = row.get("reviews") or []
            review_ratings = [float(r["rating"]) for r in reviews if isinstance(r.get("rating"), (int, float))]
            snippets = [self._review_text(r) for r in reviews]
            snippets = [s[:500] for s in snippets if s][:5]
            sample_rating = round(sum(review_ratings) / len(review_ratings), 2) if review_ratings else None
            hours = row.get("currentOpeningHours") or {}
            open_value = hours.get("openNow") if isinstance(hours.get("openNow"), bool) else None
            links = row.get("googleMapsLinks") or {}
            display = row.get("displayName") or {}
            rating = float(row["rating"]) if isinstance(row.get("rating"), (int, float)) else None
            rating_count = int(row.get("userRatingCount") or 0)
            website = row.get("websiteUri")
            quality, confidence = self._score(
                rating,
                rating_count,
                distance,
                open_value,
                len(row.get("photos") or []),
                len(reviews),
                website,
            )
            place = LocalPlace(
                place_id=str(row.get("id") or ""),
                name=str(display.get("text") or row.get("formattedAddress") or "Local"),
                address=str(row.get("formattedAddress") or ""),
                latitude=float(plat) if isinstance(plat, (int, float)) else None,
                longitude=float(plon) if isinstance(plon, (int, float)) else None,
                distance_m=distance,
                rating=rating,
                rating_count=rating_count,
                price_level=row.get("priceLevel"),
                open_now=open_value,
                business_status=row.get("businessStatus"),
                website=website,
                photo_count=len(row.get("photos") or []),
                review_count_sample=len(reviews),
                review_rating_sample=sample_rating,
                review_snippets=snippets,
                maps_place_url=links.get("placeUri"),
                maps_directions_url=links.get("directionsUri"),
                maps_reviews_url=links.get("reviewsUri"),
                maps_photos_url=links.get("photosUri"),
                quality_score=quality,
                confidence_score=confidence,
            )
            if place.place_id:
                places.append(place)

        places.sort(key=lambda p: (p.quality_score, p.confidence_score), reverse=True)
        return places[:page_size]

    @staticmethod
    def directions_url(place: LocalPlace) -> str:
        if place.maps_directions_url:
            return place.maps_directions_url
        destination = ", ".join(x for x in [place.name, place.address] if x)
        params = {"api": "1", "destination": destination}
        if place.place_id:
            params["destination_place_id"] = place.place_id
        return "https://www.google.com/maps/dir/?" + urlencode(params)


RECOMMENDER_SYSTEM = """You are JARVIS Local Advisor.
Recommend places using ONLY the supplied Google Places evidence. Be direct and concise.
Do not confuse missing data with poor quality: sparse data means lower confidence, not a bad place.
Prefer strong rating evidence, meaningful review volume, useful recent/relevant review signals,
operating status and reasonable proximity. If the data are weak or conflicting, say that briefly.
Return ONLY JSON:
{
  "recommended_place_id":"one supplied place id",
  "message":"short pt-BR answer: mention how many places were found, show the best candidates compactly, state your recommendation and 1-3 reasons"
}
Never invent menu items, prices, reviews, photos, distance, opening status, or facts absent from the evidence."""


class LocalAssistant:
    def __init__(self, router: ModelRouter, places: GooglePlacesClient):
        self.router = router
        self.places = places

    @property
    def state_path(self) -> Path:
        return settings.secrets_file.parent / "local_assistant.json"

    def _read_state(self) -> dict[str, Any]:
        if not self.state_path.exists():
            return {}
        try:
            raw = json.loads(self.state_path.read_text(encoding="utf-8"))
            return raw if isinstance(raw, dict) else {}
        except (OSError, json.JSONDecodeError):
            return {}

    def _write_state(self, data: dict[str, Any]) -> None:
        self.state_path.parent.mkdir(parents=True, exist_ok=True)
        tmp = self.state_path.with_suffix(".tmp")
        tmp.write_text(json.dumps(data, ensure_ascii=False, indent=2), encoding="utf-8")
        try:
            os.chmod(self.state_path.parent, 0o700)
            os.chmod(tmp, 0o600)
        except OSError:
            pass
        os.replace(tmp, self.state_path)

    def remember_recommendation(self, session_id: str, place: LocalPlace) -> None:
        data = self._read_state()
        data[session_id] = {
            "recommended_place": place.public_dict(),
            "updated_at": datetime.now(timezone.utc).isoformat(),
        }
        # Single-user MVP: keep only the latest 50 session recommendations.
        items = sorted(data.items(), key=lambda kv: kv[1].get("updated_at", ""), reverse=True)[:50]
        self._write_state(dict(items))

    def last_recommendation(self, session_id: str) -> LocalPlace | None:
        raw = self._read_state().get(session_id, {}).get("recommended_place")
        if not raw:
            return None
        try:
            return LocalPlace(**raw)
        except TypeError:
            return None

    @staticmethod
    def looks_like_local_request(message: str) -> bool:
        text = message.lower().strip()
        explicit = (
            "perto de mim",
            "perto daqui",
            "próximo de mim",
            "proximo de mim",
            "em volta de mim",
            "ao meu redor",
            "onde tem",
            "aonde tem",
            "onde posso comer",
            "onde eu posso comer",
            "pra eu comer",
            "para eu comer",
        )
        categories = (
            "restaurante",
            "restaurant",
            "comida",
            "pizzaria",
            "pizza",
            "sushi",
            "cafeteria",
            "café",
            "cafe",
            "bar ",
            "hambúrguer",
            "hamburguer",
            "padaria",
            "farmácia",
            "farmacia",
            "mercado",
        )
        return any(x in text for x in explicit) or (
            any(x in text for x in categories)
            and any(x in text for x in ("onde", "aonde", "perto", "próximo", "proximo"))
        )

    @staticmethod
    def navigation_followup(message: str) -> bool:
        text = message.lower().strip()
        exact = {"sim", "pode", "quero", "ok", "vamos", "bora"}
        phrases = (
            "me guie",
            "me guia",
            "me leve",
            "quero ir",
            "abrir rota",
            "abra a rota",
            "como chegar",
            "vamos pra lá",
            "vamos para lá",
            "ir pra lá",
            "ir para lá",
        )
        return text in exact or any(x in text for x in phrases)

    async def recommend(
        self,
        session_id: str,
        message: str,
        location: dict[str, Any] | None,
    ) -> dict[str, Any]:
        if not location:
            return {
                "message": "Preciso da sua localização para procurar lugares realmente perto de você. Ative LOCALIZAÇÃO e eu faço a busca.",
                "actions": [{"type": "request_location", "label": "ATIVAR LOCALIZAÇÃO"}],
                "provider": "local",
                "model": None,
            }
        try:
            lat = float(location["latitude"])
            lon = float(location["longitude"])
        except (KeyError, TypeError, ValueError):
            raise LocalAssistantError("Localização inválida.") from None

        candidates = await self.places.search(
            message,
            lat,
            lon,
            radius_m=settings.places_default_radius_m,
            max_results=settings.places_max_candidates,
        )
        if not candidates:
            return {
                "message": "Não encontrei opções confiáveis perto de você com essa busca. Posso ampliar o raio ou tentar outra descrição.",
                "actions": [],
                "provider": "google_places",
                "model": None,
            }

        evidence = [p.public_dict() for p in candidates]
        provider = self.router.primary()
        reply = await provider.complete(RECOMMENDER_SYSTEM, json.dumps(evidence, ensure_ascii=False))
        raw = reply.text.strip()
        match = re.search(r"\{.*\}", raw, re.S)
        try:
            data = json.loads(match.group(0) if match else raw)
        except json.JSONDecodeError:
            data = {}
        ids = {p.place_id: p for p in candidates}
        chosen = ids.get(str(data.get("recommended_place_id") or "")) or candidates[0]
        self.remember_recommendation(session_id, chosen)

        message_out = str(data.get("message") or "").strip()
        if not message_out:
            distance = f" · {chosen.distance_m / 1000:.1f} km" if chosen.distance_m is not None else ""
            rating = f"{chosen.rating:.1f}/5 ({chosen.rating_count} avaliações)" if chosen.rating is not None else "avaliação insuficiente"
            message_out = f"Minha recomendação é {chosen.name}: {rating}{distance}."

        actions: list[dict[str, Any]] = []
        if chosen.maps_place_url:
            actions.append({"type": "open_url", "label": "VER NO MAPS", "url": chosen.maps_place_url, "auto": False})
        if chosen.maps_photos_url:
            actions.append({"type": "open_url", "label": "FOTOS", "url": chosen.maps_photos_url, "auto": False})
        if chosen.maps_reviews_url:
            actions.append({"type": "open_url", "label": "AVALIAÇÕES", "url": chosen.maps_reviews_url, "auto": False})
        return {
            "message": message_out + "\n\nSe quiser, diga “sim” e eu abro a rota até lá.",
            "actions": actions,
            "provider": reply.provider,
            "model": reply.model,
            "recommended": chosen.public_dict(),
        }

    def navigation(self, session_id: str) -> dict[str, Any] | None:
        place = self.last_recommendation(session_id)
        if not place:
            return None
        url = self.places.directions_url(place)
        return {
            "message": f"Abrindo a rota para {place.name} no Google Maps.",
            "actions": [{"type": "open_url", "label": "ABRIR ROTA", "url": url, "auto": True}],
            "provider": "google_maps",
            "model": None,
        }


google_places = GooglePlacesClient()
