import httpx

from jarvis.providers.base import ProviderAPIError
from jarvis.providers.google import GoogleProvider


def _response(status: int, payload: dict) -> httpx.Response:
    return httpx.Response(
        status,
        json=payload,
        request=httpx.Request(
            "POST",
            "https://generativelanguage.googleapis.com/v1beta/models/test:generateContent",
        ),
    )


def test_resource_exhausted_becomes_clear_api_error():
    provider = GoogleProvider()
    exc = provider._provider_error(
        _response(
            429,
            {
                "error": {
                    "code": 429,
                    "status": "RESOURCE_EXHAUSTED",
                    "message": "Quota exceeded for quota metric",
                }
            },
        )
    )

    assert isinstance(exc, ProviderAPIError)
    assert exc.status_code == 429
    assert exc.detail["provider"] == "google"
    assert "limite" in exc.detail["message"].lower()
    assert "Flash-Lite" in exc.detail["message"]
    assert exc.detail["upstream_code"] == "RESOURCE_EXHAUSTED"


def test_bad_request_is_sanitized_and_keeps_provider_context():
    provider = GoogleProvider()
    exc = provider._provider_error(
        _response(
            400,
            {
                "error": {
                    "code": 400,
                    "status": "INVALID_ARGUMENT",
                    "message": "Example invalid request",
                }
            },
        )
    )

    assert exc.status_code == 502
    assert exc.detail["provider"] == "google"
    assert "Example invalid request" in exc.detail["message"]
