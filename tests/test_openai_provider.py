import httpx

from jarvis.providers.base import ProviderAPIError
from jarvis.providers.openai import OpenAIProvider


def _response(status: int, payload: dict) -> httpx.Response:
    return httpx.Response(
        status,
        json=payload,
        request=httpx.Request("POST", "https://api.openai.com/v1/responses"),
    )


def test_insufficient_quota_becomes_clear_api_error():
    provider = OpenAIProvider()
    exc = provider._provider_error(
        _response(
            429,
            {
                "error": {
                    "code": "insufficient_quota",
                    "type": "insufficient_quota",
                    "message": "You exceeded your current quota.",
                }
            },
        )
    )

    assert isinstance(exc, ProviderAPIError)
    assert exc.status_code == 429
    assert exc.detail["code"] == "provider_error"
    assert exc.detail["provider"] == "openai"
    assert "faturamento" in exc.detail["message"].lower()
    assert exc.detail["upstream_code"] == "insufficient_quota"


def test_credit_balance_exhausted_is_not_reported_as_rate_limit():
    provider = OpenAIProvider()
    exc = provider._provider_error(
        _response(
            429,
            {
                "error": {
                    "code": "credit_balance_exhausted",
                    "type": "insufficient_quota",
                    "message": "Credit balance exhausted.",
                }
            },
        )
    )

    assert exc.status_code == 429
    assert exc.detail["upstream_code"] == "credit_balance_exhausted"
    assert "saldo de créditos" in exc.detail["message"].lower()
    assert "temporário de uso" not in exc.detail["message"].lower()


def test_bad_request_is_sanitized_and_keeps_provider_context():
    provider = OpenAIProvider()
    exc = provider._provider_error(
        _response(
            400,
            {
                "error": {
                    "code": "invalid_request_error",
                    "message": "Example invalid request",
                }
            },
        )
    )

    assert exc.status_code == 502
    assert exc.detail["provider"] == "openai"
    assert "Example invalid request" in exc.detail["message"]
