# CourtListener MCP Server Application
"""CourtListener MCP Server - Model Context Protocol server for Legal Case Data.

This package provides LLM-friendly access to legal cases, opinions, court data,
and citation tools through the official CourtListener API v4, plus US federal
regulations via the eCFR API.
"""

from importlib.metadata import version, PackageNotFoundError

try:
    __version__ = version("court-listener-mcp-server")
except PackageNotFoundError:
    # Package is not installed (e.g., running from source)
    __version__ = "0.2.0"
