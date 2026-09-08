from jarvis.local_assistant import GooglePlacesClient, LocalAssistant, LocalPlace
from jarvis.router import ModelRouter
from jarvis.schemas import ChatRequest
from jarvis.tools.registry import ToolRegistry


def make_place(**overrides):
    data = {
        "place_id": "place-1",
        "name": "Trattoria Teste",
        "address": "Rua Teste, 10",
        "latitude": -22.9,
        "longitude": -43.2,
        "distance_m": 900,
        "rating": 4.6,
        "rating_count": 450,
        "price_level": "PRICE_LEVEL_MODERATE",
        "open_now": True,
        "business_status": "OPERATIONAL",
        "website": "https://example.com",
        "photo_count": 10,
        "review_count_sample": 5,
        "review_rating_sample": 4.8,
        "review_snippets": ["Muito bom"],
        "maps_place_url": None,
        "maps_directions_url": None,
        "maps_reviews_url": None,
        "maps_photos_url": None,
        "quality_score": 80.0,
        "confidence_score": 90.0,
    }
    data.update(overrides)
    return LocalPlace(**data)


def test_sparse_data_reduces_confidence_not_assumed_bad_quality():
    established_quality, established_conf = GooglePlacesClient._score(
        4.6, 800, 1000, True, 10, 5, "https://example.com"
    )
    sparse_quality, sparse_conf = GooglePlacesClient._score(
        4.6, 8, 1000, True, 1, 1, None
    )
    assert sparse_conf < established_conf
    assert sparse_quality > 40
    assert established_quality > sparse_quality


def test_google_maps_fallback_directions_uses_place_id():
    place = make_place()
    url = GooglePlacesClient.directions_url(place)
    assert "google.com/maps/dir" in url
    assert "destination_place_id=place-1" in url


def test_local_intent_and_navigation_followup_detection():
    assistant = LocalAssistant(ModelRouter(), GooglePlacesClient())
    assert assistant.looks_like_local_request("Onde tem comida italiana perto de mim?")
    assert assistant.navigation_followup("sim")
    assert assistant.navigation_followup("me guie até lá")
    assert not assistant.looks_like_local_request("Explique a história da culinária italiana")


def test_chat_request_accepts_ephemeral_location():
    req = ChatRequest(
        message="Onde tem restaurante perto de mim?",
        location={"latitude": -22.9, "longitude": -43.2, "accuracy_m": 15},
    )
    assert req.location is not None
    assert req.location.latitude == -22.9


def test_places_tools_are_registered_and_read_only():
    registry = ToolRegistry()
    assert "places.status" in registry.tools
    assert "places.search" in registry.tools
    autonomous = {x["name"] for x in registry.autonomous_specs()}
    assert "places.search" in autonomous
