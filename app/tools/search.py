"""Search tools for CourtListener MCP server."""

from typing import Annotated, Any
from urllib.parse import parse_qs, urlparse

from fastmcp import Context, FastMCP
import httpx
from pydantic import Field

from app.config import config, get_auth_headers, get_http_client

# Create the search server
search_server: FastMCP[Any] = FastMCP(
    name="CourtListener Search Server",
    instructions="Search server for CourtListener legal database providing comprehensive search capabilities. "
    "This server enables searching across different types of legal content including: "
    "court opinions and cases, oral argument audio recordings, federal dockets from PACER, "
    "RECAP filing documents, and judges/legal professionals. "
    "Search parameters include date ranges, court filters, case names, judge names, and full-text queries. "
    "Results are returned with detailed metadata and can be sorted by relevance or date.",
)

# Read-only, open-world hints applied to every search tool. These let MCP
# clients skip write-confirmation prompts and treat results as external data.
_READ_ONLY = {"readOnlyHint": True, "openWorldHint": True}


def _extract_cursor(next_url: str | None) -> str | None:
    """Pull the opaque ``cursor`` token out of CourtListener's ``next`` URL.

    CourtListener v4 search is cursor-paginated: each response carries a full
    ``next`` URL whose ``cursor`` query param can be replayed to fetch the
    following page. We surface just the token so clients don't have to parse
    the URL themselves.

    Args:
        next_url: The ``next`` field from a CourtListener response, or None.

    Returns:
        The cursor token, or None when there is no next page.
    """
    if not next_url:
        return None
    try:
        values = parse_qs(urlparse(next_url).query).get("cursor")
        return values[0] if values else None
    except Exception:  # pragma: no cover - defensive
        return None


async def _search_courtlistener(
    ctx: Context,
    resource_type: str,
    search_type: str,
    q: str,
    order_by: str,
    limit: int,
    filters: dict[str, Any],
    cursor: str | None = None,
) -> dict[str, Any]:
    """Execute a search against the CourtListener API.

    Args:
        ctx: The FastMCP context for logging and accessing shared resources.
        resource_type: Human-readable name of the resource type (for logging).
        search_type: The CourtListener V4 API type parameter (e.g., 'o', 'd', 'p').
        q: The search query string.
        order_by: Sort order for results.
        limit: Maximum number of results to return from the page (upper bound).
        filters: Dictionary of optional filter parameters.
        cursor: Opaque pagination cursor from a previous response's ``next_cursor``.

    Returns:
        dict: The search results as returned by the CourtListener API, with an
        added ``next_cursor`` field for pagination.

    Raises:
        ValueError: If no CourtListener API key is available.
        httpx.HTTPStatusError: If the API request fails.

    """
    await ctx.info(f"Searching {resource_type} with query: {q}")

    headers = get_auth_headers(ctx)

    # NOTE: CourtListener v4 search does NOT accept a per-request result-count
    # param (the old `hit=<limit>` was a no-op). It returns a fixed-size page
    # (~20) plus a cursor. We honor `limit` by truncating the page client-side
    # and expose `next_cursor` for callers that want more.
    params: dict[str, str | int] = {
        "q": q,
        "order_by": order_by,
        "type": search_type,
    }
    if cursor:
        params["cursor"] = cursor

    # Add optional filters (only non-empty/non-zero/non-None values)
    for key, value in filters.items():
        if value:
            params[key] = value

    try:
        async with get_http_client(ctx) as http_client:
            response = await http_client.get(
                f"{config.courtlistener_base_url}search/",
                params=params,
                headers=headers,
            )
            response.raise_for_status()
            data = response.json()

        results = data.get("results")
        if isinstance(results, list) and limit and len(results) > limit:
            data["results"] = results[:limit]

        # Surface the pagination cursor token for follow-up pages.
        data["next_cursor"] = _extract_cursor(data.get("next"))

        await ctx.info(f"Found {data.get('count', 0)} {resource_type}")
        return data

    except httpx.HTTPStatusError as e:
        await ctx.error(f"HTTP error: {e}")
        raise
    except Exception as e:
        await ctx.error(f"Search error: {e}")
        raise


@search_server.tool(annotations=_READ_ONLY)
async def opinions(
    q: Annotated[str, Field(description="Search query for full text of opinions")],
    ctx: Context,
    court: Annotated[
        str | None, Field(description="Court ID filter (e.g., 'scotus', 'ca9')")
    ] = None,
    case_name: Annotated[str | None, Field(description="Filter by case name")] = None,
    judge: Annotated[str | None, Field(description="Filter by judge name")] = None,
    filed_after: Annotated[
        str | None,
        Field(description="Only show opinions filed after this date (YYYY-MM-DD)"),
    ] = None,
    filed_before: Annotated[
        str | None,
        Field(description="Only show opinions filed before this date (YYYY-MM-DD)"),
    ] = None,
    cited_gt: Annotated[
        int | None,
        Field(description="Minimum number of times opinion has been cited", ge=0),
    ] = None,
    cited_lt: Annotated[
        int | None,
        Field(description="Maximum number of times opinion has been cited", ge=0),
    ] = None,
    order_by: Annotated[
        str,
        Field(description="Sort by 'score desc', 'dateFiled desc', or 'dateFiled asc'"),
    ] = "score desc",
    limit: Annotated[
        int,
        Field(
            description="Max results from this page (upper bound; CL pages ~20)",
            ge=1,
            le=100,
        ),
    ] = 20,
    cursor: Annotated[
        str | None,
        Field(description="Pagination cursor from a prior response's next_cursor"),
    ] = None,
) -> dict[str, Any]:
    """Search case law opinion clusters with nested Opinion documents in CourtListener."""
    return await _search_courtlistener(
        ctx=ctx,
        resource_type="opinions",
        search_type="o",
        q=q,
        order_by=order_by,
        limit=limit,
        cursor=cursor,
        filters={
            "court": court,
            "case_name": case_name,
            "judge": judge,
            "filed_after": filed_after,
            "filed_before": filed_before,
            "cited_gt": cited_gt,
            "cited_lt": cited_lt,
        },
    )


@search_server.tool(annotations=_READ_ONLY)
async def dockets(
    q: Annotated[str, Field(description="Search query for docket text")],
    ctx: Context,
    court: Annotated[
        str | None, Field(description="Court ID filter (e.g., 'scotus', 'ca9')")
    ] = None,
    case_name: Annotated[str | None, Field(description="Filter by case name")] = None,
    docket_number: Annotated[
        str | None, Field(description="Specific docket number to search for")
    ] = None,
    date_filed_after: Annotated[
        str | None,
        Field(description="Filter dockets filed after this date (YYYY-MM-DD)"),
    ] = None,
    date_filed_before: Annotated[
        str | None,
        Field(description="Filter dockets filed before this date (YYYY-MM-DD)"),
    ] = None,
    party_name: Annotated[str | None, Field(description="Filter by party name")] = None,
    order_by: Annotated[
        str,
        Field(description="Sort by 'score desc', 'dateFiled desc', or 'dateFiled asc'"),
    ] = "score desc",
    limit: Annotated[
        int,
        Field(
            description="Max results from this page (upper bound; CL pages ~20)",
            ge=1,
            le=100,
        ),
    ] = 20,
    cursor: Annotated[
        str | None,
        Field(description="Pagination cursor from a prior response's next_cursor"),
    ] = None,
) -> dict[str, Any]:
    """Search federal cases (dockets) from PACER in CourtListener."""
    return await _search_courtlistener(
        ctx=ctx,
        resource_type="dockets",
        search_type="d",
        q=q,
        order_by=order_by,
        limit=limit,
        cursor=cursor,
        filters={
            "court": court,
            "case_name": case_name,
            "docket_number": docket_number,
            "date_filed_after": date_filed_after,
            "date_filed_before": date_filed_before,
            "party_name": party_name,
        },
    )


@search_server.tool(annotations=_READ_ONLY)
async def dockets_with_documents(
    q: Annotated[str, Field(description="Search query for federal cases")],
    ctx: Context,
    court: Annotated[
        str | None, Field(description="Court ID filter (e.g., 'scotus', 'ca9')")
    ] = None,
    case_name: Annotated[str | None, Field(description="Filter by case name")] = None,
    docket_number: Annotated[
        str | None, Field(description="Specific docket number to search for")
    ] = None,
    date_filed_after: Annotated[
        str | None,
        Field(description="Filter dockets filed after this date (YYYY-MM-DD)"),
    ] = None,
    date_filed_before: Annotated[
        str | None,
        Field(description="Filter dockets filed before this date (YYYY-MM-DD)"),
    ] = None,
    party_name: Annotated[str | None, Field(description="Filter by party name")] = None,
    order_by: Annotated[
        str,
        Field(description="Sort by 'score desc', 'dateFiled desc', or 'dateFiled asc'"),
    ] = "score desc",
    limit: Annotated[
        int,
        Field(
            description="Max results from this page (upper bound; CL pages ~20)",
            ge=1,
            le=100,
        ),
    ] = 20,
    cursor: Annotated[
        str | None,
        Field(description="Pagination cursor from a prior response's next_cursor"),
    ] = None,
) -> dict[str, Any]:
    """Search federal cases (dockets) with up to three nested documents.

    If there are more than three matching documents, the more_docs field will be true.
    """
    return await _search_courtlistener(
        ctx=ctx,
        resource_type="dockets with documents",
        search_type="r",
        q=q,
        order_by=order_by,
        limit=limit,
        cursor=cursor,
        filters={
            "court": court,
            "case_name": case_name,
            "docket_number": docket_number,
            "date_filed_after": date_filed_after,
            "date_filed_before": date_filed_before,
            "party_name": party_name,
        },
    )


@search_server.tool(annotations=_READ_ONLY)
async def recap_documents(
    q: Annotated[str, Field(description="Search query for RECAP filing documents")],
    ctx: Context,
    court: Annotated[
        str | None, Field(description="Court ID filter (e.g., 'scotus', 'ca9')")
    ] = None,
    case_name: Annotated[str | None, Field(description="Filter by case name")] = None,
    docket_number: Annotated[
        str | None, Field(description="Specific docket number to search for")
    ] = None,
    document_number: Annotated[
        str | None, Field(description="Specific document number to search for")
    ] = None,
    attachment_number: Annotated[
        str | None, Field(description="Specific attachment number to search for")
    ] = None,
    filed_after: Annotated[
        str | None,
        Field(description="Filter documents filed after this date (YYYY-MM-DD)"),
    ] = None,
    filed_before: Annotated[
        str | None,
        Field(description="Filter documents filed before this date (YYYY-MM-DD)"),
    ] = None,
    party_name: Annotated[str | None, Field(description="Filter by party name")] = None,
    order_by: Annotated[
        str,
        Field(description="Sort by 'score desc', 'dateFiled desc', or 'dateFiled asc'"),
    ] = "score desc",
    limit: Annotated[
        int,
        Field(
            description="Max results from this page (upper bound; CL pages ~20)",
            ge=1,
            le=100,
        ),
    ] = 20,
    cursor: Annotated[
        str | None,
        Field(description="Pagination cursor from a prior response's next_cursor"),
    ] = None,
) -> dict[str, Any]:
    """Search federal filing documents from PACER in the RECAP archive."""
    return await _search_courtlistener(
        ctx=ctx,
        resource_type="RECAP documents",
        search_type="rd",
        q=q,
        order_by=order_by,
        limit=limit,
        cursor=cursor,
        filters={
            "court": court,
            "case_name": case_name,
            "docket_number": docket_number,
            "document_number": document_number,
            "attachment_number": attachment_number,
            "filed_after": filed_after,
            "filed_before": filed_before,
            "party_name": party_name,
        },
    )


@search_server.tool(annotations=_READ_ONLY)
async def audio(
    q: Annotated[str, Field(description="Search query for oral argument audio")],
    ctx: Context,
    court: Annotated[
        str | None, Field(description="Court ID filter (e.g., 'scotus', 'ca9')")
    ] = None,
    case_name: Annotated[str | None, Field(description="Filter by case name")] = None,
    judge: Annotated[str | None, Field(description="Filter by judge name")] = None,
    argued_after: Annotated[
        str | None, Field(description="Filter arguments after this date (YYYY-MM-DD)")
    ] = None,
    argued_before: Annotated[
        str | None, Field(description="Filter arguments before this date (YYYY-MM-DD)")
    ] = None,
    order_by: Annotated[
        str,
        Field(
            description="Sort by 'score desc', 'dateArgued desc', or 'dateArgued asc'"
        ),
    ] = "score desc",
    limit: Annotated[
        int,
        Field(
            description="Max results from this page (upper bound; CL pages ~20)",
            ge=1,
            le=100,
        ),
    ] = 20,
    cursor: Annotated[
        str | None,
        Field(description="Pagination cursor from a prior response's next_cursor"),
    ] = None,
) -> dict[str, Any]:
    """Search oral argument audio recordings in CourtListener."""
    return await _search_courtlistener(
        ctx=ctx,
        resource_type="audio recordings",
        search_type="oa",
        q=q,
        order_by=order_by,
        limit=limit,
        cursor=cursor,
        filters={
            "court": court,
            "case_name": case_name,
            "judge": judge,
            "dateArgued_after": argued_after,
            "dateArgued_before": argued_before,
        },
    )


@search_server.tool(annotations=_READ_ONLY)
async def people(
    q: Annotated[
        str, Field(description="Search query for judges and legal professionals")
    ],
    ctx: Context,
    name: Annotated[str | None, Field(description="Filter by person's name")] = None,
    position_type: Annotated[
        str | None, Field(description="Filter by position type (e.g., 'jud' for judge)")
    ] = None,
    political_affiliation: Annotated[
        str | None, Field(description="Filter by political affiliation")
    ] = None,
    school: Annotated[
        str | None, Field(description="Filter by school attended")
    ] = None,
    appointed_by: Annotated[
        str | None, Field(description="Filter by appointing authority")
    ] = None,
    selection_method: Annotated[
        str | None, Field(description="Filter by selection method")
    ] = None,
    order_by: Annotated[
        str, Field(description="Sort by 'score desc' or 'name asc'")
    ] = "score desc",
    limit: Annotated[
        int,
        Field(
            description="Max results from this page (upper bound; CL pages ~20)",
            ge=1,
            le=100,
        ),
    ] = 20,
    cursor: Annotated[
        str | None,
        Field(description="Pagination cursor from a prior response's next_cursor"),
    ] = None,
) -> dict[str, Any]:
    """Search judges and legal professionals in the CourtListener database."""
    return await _search_courtlistener(
        ctx=ctx,
        resource_type="people",
        search_type="p",
        q=q,
        order_by=order_by,
        limit=limit,
        cursor=cursor,
        filters={
            "name": name,
            "position_type": position_type,
            "political_affiliation": political_affiliation,
            "school": school,
            "appointed_by": appointed_by,
            "selection_method": selection_method,
        },
    )
