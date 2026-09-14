"""Unit tests for bring-your-own-key (BYOK) token resolution in app/config.py."""

from types import SimpleNamespace
import pytest

from app.config import (
    _get_user_api_key_from_ctx,
    config,
    get_api_key,
    get_auth_headers,
)


def make_stub_ctx(headers: dict[str, str] | None = None) -> SimpleNamespace:
    """Build a stub context object exposing ctx.request_context.request.headers."""
    request = SimpleNamespace(headers=headers) if headers is not None else SimpleNamespace()
    return SimpleNamespace(request_context=SimpleNamespace(request=request))


def test_get_user_api_key_from_x_courtlistener_token():
    ctx = make_stub_ctx({"x-courtlistener-token": "custom-key-123"})
    assert _get_user_api_key_from_ctx(ctx) == "custom-key-123"


def test_get_user_api_key_from_authorization_header():
    ctx = make_stub_ctx({"authorization": "Token custom-token-456"})
    assert _get_user_api_key_from_ctx(ctx) == "custom-token-456"

    ctx_upper = make_stub_ctx({"authorization": "TOKEN custom-token-789"})
    assert _get_user_api_key_from_ctx(ctx_upper) == "custom-token-789"


def test_get_user_api_key_prefers_x_token_over_authorization():
    ctx = make_stub_ctx({
        "x-courtlistener-token": "preferred-key",
        "authorization": "Token secondary-key",
    })
    assert _get_user_api_key_from_ctx(ctx) == "preferred-key"


def test_get_user_api_key_strips_whitespace():
    ctx1 = make_stub_ctx({"x-courtlistener-token": "   spaced-key   "})
    assert _get_user_api_key_from_ctx(ctx1) == "spaced-key"

    ctx2 = make_stub_ctx({"authorization": "Token    spaced-auth-key   "})
    assert _get_user_api_key_from_ctx(ctx2) == "spaced-auth-key"


def test_get_user_api_key_returns_none_for_empty_values():
    assert _get_user_api_key_from_ctx(make_stub_ctx({"x-courtlistener-token": ""})) is None
    assert _get_user_api_key_from_ctx(make_stub_ctx({"x-courtlistener-token": "   "})) is None
    assert _get_user_api_key_from_ctx(make_stub_ctx({"authorization": "Token "})) is None
    assert _get_user_api_key_from_ctx(make_stub_ctx({"authorization": "Token   "})) is None
    assert _get_user_api_key_from_ctx(make_stub_ctx({"authorization": "Bearer token"})) is None


def test_get_user_api_key_handles_none_and_missing_attributes():
    assert _get_user_api_key_from_ctx(None) is None

    # Context without request_context
    assert _get_user_api_key_from_ctx(SimpleNamespace()) is None

    # Context without request
    assert _get_user_api_key_from_ctx(SimpleNamespace(request_context=SimpleNamespace())) is None

    # Context without headers
    assert (
        _get_user_api_key_from_ctx(
            SimpleNamespace(request_context=SimpleNamespace(request=SimpleNamespace(headers=None)))
        )
        is None
    )


def test_get_api_key_env_and_fallback(monkeypatch):
    monkeypatch.setenv("COURT_LISTENER_API_KEY", "env-key-999")
    assert get_api_key() == "env-key-999"

    monkeypatch.delenv("COURT_LISTENER_API_KEY", raising=False)
    monkeypatch.setattr(config, "courtlistener_api_key", "fallback-key")
    assert get_api_key() == "fallback-key"

    monkeypatch.setattr(config, "courtlistener_api_key", None)
    assert get_api_key() is None


def test_get_auth_headers_precedence(monkeypatch):
    monkeypatch.setenv("COURT_LISTENER_API_KEY", "server-env-key")
    ctx = make_stub_ctx({"x-courtlistener-token": "user-request-key"})

    # 1. Request header wins over env key
    headers = get_auth_headers(ctx)
    assert headers == {"Authorization": "Token user-request-key"}

    # 2. No header falls back to env key
    headers_fallback = get_auth_headers(None)
    assert headers_fallback == {"Authorization": "Token server-env-key"}

    empty_ctx = make_stub_ctx({})
    headers_empty_ctx = get_auth_headers(empty_ctx)
    assert headers_empty_ctx == {"Authorization": "Token server-env-key"}


def test_get_auth_headers_format_is_token_not_bearer():
    ctx = make_stub_ctx({"x-courtlistener-token": "my-secret-token"})
    headers = get_auth_headers(ctx)
    assert headers["Authorization"] == "Token my-secret-token"
    assert not headers["Authorization"].startswith("Bearer")


def test_get_auth_headers_raises_valueerror_when_no_key(monkeypatch):
    monkeypatch.delenv("COURT_LISTENER_API_KEY", raising=False)
    monkeypatch.setattr(config, "courtlistener_api_key", None)

    with pytest.raises(ValueError) as exc_info:
        get_auth_headers(None)

    assert "X-CourtListener-Token" in str(exc_info.value)
    assert "COURT_LISTENER_API_KEY" in str(exc_info.value)
