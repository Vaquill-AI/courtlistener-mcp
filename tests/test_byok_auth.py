"""Locks down BYOK token resolution for the hosted server.

A user's own CourtListener key arrives in X-CourtListener-Token (or the
Authorization header) and has to win over the server's env key. It also has
to go back out to CourtListener with the Token scheme, not Bearer.
"""

from types import SimpleNamespace
from typing import Any

import pytest

from app.config import _get_user_api_key_from_ctx, config, get_auth_headers


class StubCtx:
    def __init__(self, headers: dict[str, str]) -> None:
        self.request_context = SimpleNamespace(
            request=SimpleNamespace(headers=headers)
        )


def test_reads_x_courtlistener_token() -> None:
    ctx = StubCtx({"x-courtlistener-token": "user-key"})
    assert _get_user_api_key_from_ctx(ctx) == "user-key"


def test_reads_authorization_token_scheme() -> None:
    ctx = StubCtx({"authorization": "Token abc123"})
    assert _get_user_api_key_from_ctx(ctx) == "abc123"


def test_x_header_wins_when_both_present() -> None:
    ctx = StubCtx(
        {
            "x-courtlistener-token": "from-x",
            "authorization": "Token from-auth",
        }
    )
    assert _get_user_api_key_from_ctx(ctx) == "from-x"


def test_header_values_are_stripped() -> None:
    ctx = StubCtx({"x-courtlistener-token": "  padded-key \n"})
    assert _get_user_api_key_from_ctx(ctx) == "padded-key"

    ctx = StubCtx({"authorization": "Token   spaced-key  "})
    assert _get_user_api_key_from_ctx(ctx) == "spaced-key"


def test_blank_header_values_return_none() -> None:
    assert _get_user_api_key_from_ctx(StubCtx({"x-courtlistener-token": ""})) is None
    assert (
        _get_user_api_key_from_ctx(StubCtx({"x-courtlistener-token": "   "})) is None
    )
    assert _get_user_api_key_from_ctx(StubCtx({"authorization": "Token   "})) is None


def test_none_ctx_is_stdio_path() -> None:
    assert _get_user_api_key_from_ctx(None) is None


def test_ctx_without_request_returns_none() -> None:
    assert _get_user_api_key_from_ctx(SimpleNamespace()) is None
    assert (
        _get_user_api_key_from_ctx(SimpleNamespace(request_context=SimpleNamespace()))
        is None
    )


def test_request_header_beats_env(monkeypatch: Any) -> None:
    monkeypatch.setenv("COURT_LISTENER_API_KEY", "server-key")
    ctx = StubCtx({"x-courtlistener-token": "user-key"})
    assert get_auth_headers(ctx) == {"Authorization": "Token user-key"}


def test_falls_back_to_env_without_header(monkeypatch: Any) -> None:
    monkeypatch.setenv("COURT_LISTENER_API_KEY", "server-key")
    assert get_auth_headers(StubCtx({})) == {"Authorization": "Token server-key"}
    assert get_auth_headers(None) == {"Authorization": "Token server-key"}


def test_bearer_header_is_not_used(monkeypatch: Any) -> None:
    monkeypatch.setenv("COURT_LISTENER_API_KEY", "server-key")
    ctx = StubCtx({"authorization": "Bearer user-key"})
    assert _get_user_api_key_from_ctx(ctx) is None
    assert get_auth_headers(ctx) == {"Authorization": "Token server-key"}


def test_no_key_anywhere_raises(monkeypatch: Any) -> None:
    # conftest puts COURT_LISTENER_API_KEY in the env before importing the app,
    # so config also holds it; delenv alone would still hit the config fallback.
    monkeypatch.delenv("COURT_LISTENER_API_KEY", raising=False)
    monkeypatch.setattr(config, "courtlistener_api_key", None)
    with pytest.raises(ValueError, match="X-CourtListener-Token"):
        get_auth_headers(StubCtx({}))
    with pytest.raises(ValueError, match="X-CourtListener-Token"):
        get_auth_headers(None)
