#!/usr/bin/env python3
"""Configuration management for CourtListener MCP Server."""

import os
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import TYPE_CHECKING

import httpx
from loguru import logger
from pydantic_settings import BaseSettings

if TYPE_CHECKING:
    from fastmcp import Context


class Config(BaseSettings):
    """Configuration for CourtListener MCP Server."""

    # Server settings
    host: str = "127.0.0.1"
    mcp_port: int = 8000
    mcp_transport: str = "stdio"  # Options: stdio, http, sse
    mcp_path: str = "/mcp/"  # Path for HTTP/SSE transports

    # Logging
    courtlistener_log_level: str = "INFO"
    courtlistener_debug: bool = False

    # Environment
    environment: str = "production"

    # CourtListener API
    courtlistener_base_url: str = "https://www.courtlistener.com/api/rest/v4/"
    courtlistener_api_key: str | None = None
    courtlistener_timeout: int = 30

    model_config = {
        "env_file": ".env",
        "env_file_encoding": "utf-8",
        "case_sensitive": False,
        "extra": "ignore",  # Ignore extra environment variables
    }


# Global config instance
config = Config()


def get_api_key() -> str | None:
    """Get the server-configured CourtListener API key.

    Checks the environment variable at call time, falling back to the
    .env-loaded config. Used as the fallback when no per-request user key
    is supplied.

    Returns:
        The API key if set, None otherwise.

    """
    # Check environment variable first (allows runtime override)
    env_key = os.getenv("COURT_LISTENER_API_KEY")
    if env_key:
        return env_key
    # Fall back to config (loaded from .env at startup)
    return config.courtlistener_api_key


def _get_user_api_key_from_ctx(ctx: "Context | None") -> str | None:
    """Extract a user-supplied CourtListener token from the inbound MCP request.

    Supports two header conventions for HTTP/SSE transports:
    1. ``X-CourtListener-Token: <key>`` (preferred, no collision with MCP auth)
    2. ``Authorization: Token <key>`` (CourtListener's native scheme)

    Returns ``None`` for stdio transport or when no header is present.
    """
    if ctx is None:
        return None
    try:
        request = getattr(ctx.request_context, "request", None)
        if request is None:
            return None
        headers = getattr(request, "headers", None)
        if headers is None:
            return None
        token = headers.get("x-courtlistener-token")
        if token:
            return token.strip() or None
        auth = headers.get("authorization", "")
        if auth.lower().startswith("token "):
            return auth[6:].strip() or None
    except Exception as exc:  # pragma: no cover - defensive
        logger.debug(f"Could not read user token from request: {exc}")
    return None


def get_auth_headers(ctx: "Context | None" = None) -> dict[str, str]:
    """Get authorization headers for a CourtListener API request.

    Priority order:
    1. User-supplied key from the inbound MCP request headers (BYOK).
       This makes the hosted MCP usable by anyone with their own key
       without burning the operator's quota.
    2. Server-side ``COURT_LISTENER_API_KEY`` env var (single-tenant
       fallback for self-hosted deployments).

    Args:
        ctx: Optional FastMCP context. When provided, headers from the
            HTTP request are inspected for a user-supplied token. Pass
            ``None`` (or omit) to force the env-only path.

    Returns:
        Dictionary containing the ``Authorization`` header for CourtListener.

    Raises:
        ValueError: If neither a user header nor a server env key is set.
    """
    api_key = _get_user_api_key_from_ctx(ctx) or get_api_key()
    if not api_key:
        raise ValueError(
            "No CourtListener API key. Send 'X-CourtListener-Token: <key>' "
            "in your MCP request, or set COURT_LISTENER_API_KEY on the server."
        )
    return {"Authorization": f"Token {api_key}"}


def is_development() -> bool:
    """Check if running in development environment.

    Returns:
        True if in development mode, False otherwise.

    """
    return config.environment.lower() == "development"


def is_debug_enabled() -> bool:
    """Check if debug mode is enabled.

    Returns:
        True if debug is enabled, False otherwise.

    """
    return (
        config.courtlistener_debug or config.courtlistener_log_level.upper() == "DEBUG"
    )


@asynccontextmanager
async def get_http_client(ctx: "Context") -> AsyncIterator[httpx.AsyncClient]:
    """Get an HTTP client as an async context manager.

    If the lifespan context is available, yields the shared client (without closing it).
    Otherwise, creates a temporary client that is properly closed after use.

    Args:
        ctx: The FastMCP context containing the lifespan context.

    Yields:
        An httpx.AsyncClient instance for making API requests.

    """
    # Try to get the shared client from lifespan context
    lifespan_ctx = getattr(ctx.request_context, "lifespan_context", None)
    if lifespan_ctx is not None:
        client = getattr(lifespan_ctx, "http_client", None)
        if client is not None and not client.is_closed:
            # Yield the shared client without closing it (managed by lifespan)
            yield client
            return

    # Fallback: create a temporary client and ensure it's closed
    logger.debug("Creating fallback HTTP client (lifespan client unavailable or closed)")
    client = httpx.AsyncClient(
        timeout=config.courtlistener_timeout,
        limits=httpx.Limits(max_connections=10, max_keepalive_connections=5),
    )
    try:
        yield client
    finally:
        await client.aclose()
