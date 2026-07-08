"""Regression tests for FastMCP 3 HTTP host/origin validation.

FastMCP 3 returns 421 "Misdirected Request" for any Host that isn't localhost
(DNS-rebinding protection). This server runs publicly behind a reverse proxy,
so it must allow the public host or every real request 421s. These tests lock
that behavior in.
"""

from typing import Any

import fastmcp
import httpx
import pytest


async def _get_health(host: str) -> httpx.Response:
    from app.server import ensure_setup_async, mcp

    await ensure_setup_async()
    app = mcp.http_app()
    async with app.router.lifespan_context(app):
        async with httpx.AsyncClient(
            transport=httpx.ASGITransport(app=app), base_url="http://testserver"
        ) as client:
            return await client.get("/health", headers={"host": host})


@pytest.mark.asyncio
async def test_foreign_host_rejected_by_default(monkeypatch: Any) -> None:
    """With no allow-list, a non-localhost Host is rejected with 421."""
    monkeypatch.setattr(fastmcp.settings, "http_allowed_hosts", None, raising=False)
    monkeypatch.setattr(fastmcp.settings, "http_allowed_origins", None, raising=False)
    resp = await _get_health("courtlistener-mcp.vaquill.ai")
    assert resp.status_code == 421


@pytest.mark.asyncio
async def test_wildcard_allows_public_host(monkeypatch: Any) -> None:
    """With the wildcard allow-list (our default), the public host works."""
    monkeypatch.setattr(fastmcp.settings, "http_allowed_hosts", ["*"], raising=False)
    monkeypatch.setattr(fastmcp.settings, "http_allowed_origins", ["*"], raising=False)
    resp = await _get_health("courtlistener-mcp.vaquill.ai")
    assert resp.status_code == 200
    assert resp.json()["status"] == "healthy"
