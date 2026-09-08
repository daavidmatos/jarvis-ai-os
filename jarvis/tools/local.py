from jarvis.local_assistant import google_places
from jarvis.schemas import RiskLevel
from jarvis.tools.base import Tool


class PlacesStatusTool(Tool):
    name = "places.status"
    description = "Check whether Google Places is configured for evidence-based nearby place recommendations."
    risk = RiskLevel.LOW

    async def run(self):
        return google_places.status()


class PlacesSearchTool(Tool):
    name = "places.search"
    description = (
        "Search nearby restaurants, cafes, bars, shops or other real-world places using the user's "
        "current coordinates. Returns evidence-ranked candidates with ratings, review volume, review "
        "samples, photo availability, distance, opening state and Google Maps links. Missing data lowers "
        "confidence and must not be treated as proof of poor quality."
    )
    risk = RiskLevel.LOW

    async def run(
        self,
        query: str,
        latitude: float,
        longitude: float,
        radius_m: int = 5000,
        max_results: int = 5,
        open_now: bool = False,
    ):
        places = await google_places.search(
            query,
            latitude,
            longitude,
            radius_m=radius_m,
            max_results=max_results,
            open_now=open_now,
        )
        return {"places": [p.public_dict() for p in places]}
