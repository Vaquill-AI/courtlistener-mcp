"""eCFR (Electronic Code of Federal Regulations) tools for the MCP server.

These tools wrap the public, keyless eCFR API at https://www.ecfr.gov, giving
LLMs access to US federal regulations: point-in-time regulation text, the CFR
title/structure hierarchy, full-text regulation search + analytics, agency
listings, and correction history.

This is the differentiator over CourtListener-only MCP servers (including the
official Free Law Project server): CourtListener covers case law + dockets;
eCFR covers the regulations side.

API groups (all GET, no API key):
  - versioner  /api/versioner/v1/  -> titles, versions, structure, full text, ancestry
  - admin      /api/admin/v1/      -> agencies, corrections
  - search     /api/search/v1/     -> full-text search + counts + suggestions

Docs: https://www.ecfr.gov/developers/documentation/api/v1
"""

from typing import Annotated, Any

from fastmcp import Context, FastMCP
import httpx
from pydantic import Field

from app.config import config, get_http_client

ecfr_server: FastMCP[Any] = FastMCP(
    name="eCFR Server",
    instructions="Electronic Code of Federal Regulations (eCFR, ecfr.gov) server. "
    "Provides access to US federal regulations: full-text regulation search with analytics, "
    "the CFR title and structure hierarchy, point-in-time regulation text (JSON structure and source XML), "
    "agency listings, and correction history. No API key required. "
    "CFR has 50 titles; historical snapshots are addressed by a date (YYYY-MM-DD).",
)

# All eCFR tools are read-only and hit an external service.
_READ_ONLY = {"readOnlyHint": True, "openWorldHint": True}

# eCFR applies bot protection; identify ourselves with a descriptive UA.
_ECFR_HEADERS = {
    "User-Agent": "courtlistener-mcp/eCFR (+https://github.com/Vaquill-AI/courtlistener-mcp)",
    "Accept": "application/json",
}


async def _ecfr_get(
    ctx: Context,
    path: str,
    params: list[tuple[str, Any]] | None = None,
    *,
    as_xml: bool = False,
    timeout: float | None = None,
) -> dict[str, Any]:
    """GET a resource from the eCFR API.

    Args:
        ctx: FastMCP context (shared HTTP client + logging).
        path: Path under the eCFR base URL (must start with '/').
        params: Query params as (key, value) tuples (supports repeated keys).
        as_xml: When True, return the raw XML body under ``content_xml``
            instead of parsing JSON (the versioner ``full`` endpoint is XML).
        timeout: Optional per-request timeout override (seconds).

    Returns:
        Parsed JSON dict, or ``{"content_xml": <text>, ...}`` for XML responses.

    Raises:
        httpx.HTTPStatusError: If the eCFR API returns an error status.
    """
    url = f"{config.ecfr_base_url}{path}"
    clean_params = [(k, v) for k, v in (params or []) if v not in (None, "")]
    accept = "application/xml" if as_xml else "application/json"
    headers = {**_ECFR_HEADERS, "Accept": accept}
    try:
        async with get_http_client(ctx) as http_client:
            response = await http_client.get(
                url,
                params=clean_params,
                headers=headers,
                timeout=timeout or config.courtlistener_timeout,
            )
            response.raise_for_status()
            if as_xml:
                return {"url": str(response.url), "content_xml": response.text}
            return response.json()
    except httpx.HTTPStatusError as e:
        await ctx.error(f"eCFR HTTP error: {e}")
        raise
    except Exception as e:  # pragma: no cover - defensive
        await ctx.error(f"eCFR request error: {e}")
        raise


def _search_params(
    query: str,
    date: str | None,
    title: int | None,
    agency_slugs: list[str] | None,
    per_page: int | None = None,
    page: int | None = None,
    order: str | None = None,
) -> list[tuple[str, Any]]:
    """Build the shared query-param list for eCFR search endpoints."""
    params: list[tuple[str, Any]] = [("query", query)]
    if date:
        params.append(("date", date))
    if title:
        # The eCFR search API filters by title via hierarchy[title], not `title`.
        params.append(("hierarchy[title]", title))
    for slug in agency_slugs or []:
        params.append(("agency_slugs[]", slug))
    if per_page:
        params.append(("per_page", per_page))
    if page:
        params.append(("page", page))
    if order:
        params.append(("order", order))
    return params


# --------------------------------------------------------------------------- #
# Versioner service: titles, versions, structure, full text, ancestry
# --------------------------------------------------------------------------- #


@ecfr_server.tool(annotations=_READ_ONLY)
async def list_titles(ctx: Context) -> dict[str, Any]:
    """List all 50 CFR titles with their latest amended/issue dates and status."""
    await ctx.info("Listing eCFR titles")
    return await _ecfr_get(ctx, "/api/versioner/v1/titles.json")


@ecfr_server.tool(annotations=_READ_ONLY)
async def get_title_versions(
    title: Annotated[int, Field(description="CFR title number (1-50)", ge=1, le=50)],
    ctx: Context,
) -> dict[str, Any]:
    """List the available content versions (issue dates) for one CFR title."""
    await ctx.info(f"Getting eCFR versions for title {title}")
    return await _ecfr_get(ctx, f"/api/versioner/v1/versions/title-{title}.json")


@ecfr_server.tool(annotations=_READ_ONLY)
async def get_title_structure(
    title: Annotated[int, Field(description="CFR title number (1-50)", ge=1, le=50)],
    date: Annotated[str, Field(description="Snapshot date (YYYY-MM-DD)")],
    ctx: Context,
) -> dict[str, Any]:
    """Get the full hierarchical structure (title -> section) of a CFR title on a date."""
    await ctx.info(f"Getting eCFR structure for title {title} on {date}")
    return await _ecfr_get(
        ctx, f"/api/versioner/v1/structure/{date}/title-{title}.json"
    )


@ecfr_server.tool(annotations=_READ_ONLY)
async def get_ancestry(
    title: Annotated[int, Field(description="CFR title number (1-50)", ge=1, le=50)],
    date: Annotated[str, Field(description="Snapshot date (YYYY-MM-DD)")],
    ctx: Context,
    part: Annotated[
        str | None, Field(description="Restrict to a part, e.g. '75'")
    ] = None,
    section: Annotated[
        str | None, Field(description="Restrict to a section, e.g. '75.1'")
    ] = None,
) -> dict[str, Any]:
    """Get the ancestry chain (title -> ... -> node) for a CFR node on a date."""
    await ctx.info(f"Getting eCFR ancestry for title {title} on {date}")
    params: list[tuple[str, Any]] = [("part", part), ("section", section)]
    return await _ecfr_get(
        ctx, f"/api/versioner/v1/ancestry/{date}/title-{title}.json", params
    )


@ecfr_server.tool(annotations=_READ_ONLY)
async def get_source_xml(
    title: Annotated[int, Field(description="CFR title number (1-50)", ge=1, le=50)],
    date: Annotated[str, Field(description="Snapshot date (YYYY-MM-DD)")],
    ctx: Context,
    part: Annotated[
        str | None,
        Field(
            description="Part to fetch, e.g. '75'. STRONGLY recommended: whole-title fetches can time out."
        ),
    ] = None,
    section: Annotated[str | None, Field(description="Section, e.g. '75.1'")] = None,
    subtitle: Annotated[str | None, Field(description="Subtitle, e.g. 'A'")] = None,
    chapter: Annotated[str | None, Field(description="Chapter, e.g. 'I'")] = None,
    subchapter: Annotated[str | None, Field(description="Subchapter, e.g. 'B'")] = None,
    subpart: Annotated[str | None, Field(description="Subpart, e.g. 'C'")] = None,
    appendix: Annotated[str | None, Field(description="Appendix identifier")] = None,
) -> dict[str, Any]:
    """Fetch the source regulation TEXT (XML) for a CFR node on a snapshot date.

    Pass a part or section to scope the request. Fetching an entire large title
    at once can time out on the eCFR side, so narrowing is strongly recommended.
    Returns the raw XML under ``content_xml``.
    """
    await ctx.info(f"Getting eCFR source XML for title {title} on {date}")
    params: list[tuple[str, Any]] = [
        ("subtitle", subtitle),
        ("chapter", chapter),
        ("subchapter", subchapter),
        ("part", part),
        ("subpart", subpart),
        ("section", section),
        ("appendix", appendix),
    ]
    return await _ecfr_get(
        ctx,
        f"/api/versioner/v1/full/{date}/title-{title}.xml",
        params,
        as_xml=True,
        timeout=config.courtlistener_timeout * 3,
    )


# --------------------------------------------------------------------------- #
# Admin service: agencies, corrections
# --------------------------------------------------------------------------- #


@ecfr_server.tool(annotations=_READ_ONLY)
async def list_agencies(ctx: Context) -> dict[str, Any]:
    """List all agencies that appear in the CFR, with their title/chapter references."""
    await ctx.info("Listing eCFR agencies")
    return await _ecfr_get(ctx, "/api/admin/v1/agencies.json")


@ecfr_server.tool(annotations=_READ_ONLY)
async def list_all_corrections(
    ctx: Context,
    title: Annotated[
        int | None, Field(description="Restrict to a CFR title number", ge=1, le=50)
    ] = None,
    date: Annotated[
        str | None, Field(description="Corrections in effect on this date (YYYY-MM-DD)")
    ] = None,
) -> dict[str, Any]:
    """List CFR corrections, optionally filtered by title and/or effective date."""
    await ctx.info("Listing eCFR corrections")
    params: list[tuple[str, Any]] = [("title", title), ("date", date)]
    return await _ecfr_get(ctx, "/api/admin/v1/corrections.json", params)


@ecfr_server.tool(annotations=_READ_ONLY)
async def list_corrections_by_title(
    title: Annotated[int, Field(description="CFR title number (1-50)", ge=1, le=50)],
    ctx: Context,
) -> dict[str, Any]:
    """List all corrections for a single CFR title."""
    await ctx.info(f"Listing eCFR corrections for title {title}")
    return await _ecfr_get(ctx, f"/api/admin/v1/corrections/title/{title}.json")


# --------------------------------------------------------------------------- #
# Search service: full-text search + counts + suggestions
# --------------------------------------------------------------------------- #


@ecfr_server.tool(annotations=_READ_ONLY)
async def search_regulations(
    query: Annotated[str, Field(description="Full-text search query over the CFR")],
    ctx: Context,
    title: Annotated[
        int | None, Field(description="Restrict to a CFR title number", ge=1, le=50)
    ] = None,
    agency_slugs: Annotated[
        list[str] | None,
        Field(description="Restrict to one or more agency slugs (from list_agencies)"),
    ] = None,
    date: Annotated[
        str | None, Field(description="Search the CFR as of this date (YYYY-MM-DD)")
    ] = None,
    per_page: Annotated[
        int, Field(description="Results per page (max 20)", ge=1, le=20)
    ] = 20,
    page: Annotated[int, Field(description="Page number", ge=1)] = 1,
    order: Annotated[
        str | None,
        Field(
            description="Sort order: 'relevance', 'hierarchy', 'newest_first', 'oldest_first'"
        ),
    ] = None,
) -> dict[str, Any]:
    """Full-text search over federal regulations, returning matching sections with hierarchy."""
    await ctx.info(f"Searching eCFR regulations: {query}")
    params = _search_params(query, date, title, agency_slugs, per_page, page, order)
    return await _ecfr_get(ctx, "/api/search/v1/results", params)


@ecfr_server.tool(annotations=_READ_ONLY)
async def get_search_count(
    query: Annotated[str, Field(description="Full-text search query over the CFR")],
    ctx: Context,
    title: Annotated[
        int | None, Field(description="Restrict to a title", ge=1, le=50)
    ] = None,
    agency_slugs: Annotated[
        list[str] | None, Field(description="Restrict to agency slugs")
    ] = None,
    date: Annotated[str | None, Field(description="As-of date (YYYY-MM-DD)")] = None,
) -> dict[str, Any]:
    """Get the total number of CFR sections matching a search query."""
    await ctx.info(f"Counting eCFR results: {query}")
    params = _search_params(query, date, title, agency_slugs)
    return await _ecfr_get(ctx, "/api/search/v1/count", params)


@ecfr_server.tool(annotations=_READ_ONLY)
async def get_search_summary(
    query: Annotated[str, Field(description="Full-text search query over the CFR")],
    ctx: Context,
    title: Annotated[
        int | None, Field(description="Restrict to a title", ge=1, le=50)
    ] = None,
    agency_slugs: Annotated[
        list[str] | None, Field(description="Restrict to agency slugs")
    ] = None,
    date: Annotated[str | None, Field(description="As-of date (YYYY-MM-DD)")] = None,
) -> dict[str, Any]:
    """Get summary details (counts + metadata) for a CFR search query."""
    await ctx.info(f"Summarizing eCFR results: {query}")
    params = _search_params(query, date, title, agency_slugs)
    return await _ecfr_get(ctx, "/api/search/v1/summary", params)


@ecfr_server.tool(annotations=_READ_ONLY)
async def get_title_search_counts(
    query: Annotated[str, Field(description="Full-text search query over the CFR")],
    ctx: Context,
    date: Annotated[str | None, Field(description="As-of date (YYYY-MM-DD)")] = None,
) -> dict[str, Any]:
    """Get search result counts broken down by CFR title."""
    await ctx.info(f"Counting eCFR results by title: {query}")
    params = _search_params(query, date, None, None)
    return await _ecfr_get(ctx, "/api/search/v1/counts/titles", params)


@ecfr_server.tool(annotations=_READ_ONLY)
async def get_daily_search_counts(
    query: Annotated[str, Field(description="Full-text search query over the CFR")],
    ctx: Context,
    date: Annotated[str | None, Field(description="As-of date (YYYY-MM-DD)")] = None,
) -> dict[str, Any]:
    """Get search result counts broken down by date (daily histogram)."""
    await ctx.info(f"Counting eCFR results by date: {query}")
    params = _search_params(query, date, None, None)
    return await _ecfr_get(ctx, "/api/search/v1/counts/daily", params)


@ecfr_server.tool(annotations=_READ_ONLY)
async def get_hierarchy_search_counts(
    query: Annotated[str, Field(description="Full-text search query over the CFR")],
    ctx: Context,
    date: Annotated[str | None, Field(description="As-of date (YYYY-MM-DD)")] = None,
) -> dict[str, Any]:
    """Get search result counts distributed across the CFR hierarchy."""
    await ctx.info(f"Counting eCFR results by hierarchy: {query}")
    params = _search_params(query, date, None, None)
    return await _ecfr_get(ctx, "/api/search/v1/counts/hierarchy", params)


@ecfr_server.tool(annotations=_READ_ONLY)
async def get_search_suggestions(
    query: Annotated[str, Field(description="Partial query to get suggestions for")],
    ctx: Context,
) -> dict[str, Any]:
    """Get search-term suggestions for a partial CFR query."""
    await ctx.info(f"Getting eCFR search suggestions: {query}")
    return await _ecfr_get(ctx, "/api/search/v1/suggestions", [("query", query)])
