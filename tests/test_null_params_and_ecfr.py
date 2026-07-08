"""Regression tests for the null-param fix, cursor pagination, and eCFR tools.

All HTTP is mocked with respx; no live API calls.
"""

from typing import Any

from fastmcp import Client
import httpx
import pytest
import respx


class TestNullableOptionalParams:
    """Clients often send explicit JSON ``null`` for unset optional filters.

    Before the fix these were typed ``str``/``int`` and pydantic rejected
    ``None`` with a ValidationError (breaking search_dockets / search_recap_documents
    for real users). Optional params are now ``str | None`` / ``int | None``.
    """

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_dockets_accepts_explicit_none(
        self, client: Client[Any]
    ) -> None:
        route = respx.get("https://www.courtlistener.com/api/rest/v4/search/").mock(
            return_value=httpx.Response(
                200, json={"count": 0, "next": None, "previous": None, "results": []}
            )
        )
        async with client:
            result = await client.call_tool(
                "search_dockets",
                {
                    "q": "jury verdict",
                    "court": None,
                    "case_name": None,
                    "docket_number": None,
                    "date_filed_after": None,
                    "date_filed_before": None,
                    "party_name": None,
                },
            )
        assert not result.is_error
        # None filters must NOT be forwarded to CourtListener.
        sent = route.calls.last.request.url
        assert "case_name" not in str(sent)
        assert "None" not in str(sent)

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_recap_documents_accepts_explicit_none(
        self, client: Client[Any]
    ) -> None:
        respx.get("https://www.courtlistener.com/api/rest/v4/search/").mock(
            return_value=httpx.Response(
                200, json={"count": 0, "next": None, "previous": None, "results": []}
            )
        )
        async with client:
            result = await client.call_tool(
                "search_recap_documents",
                {
                    "q": "6:24-cv-00187",
                    "document_number": None,
                    "attachment_number": None,
                    "cursor": None,
                },
            )
        assert not result.is_error

    @pytest.mark.asyncio
    @respx.mock
    async def test_cited_gt_none_is_not_sent(self, client: Client[Any]) -> None:
        route = respx.get("https://www.courtlistener.com/api/rest/v4/search/").mock(
            return_value=httpx.Response(
                200, json={"count": 0, "next": None, "previous": None, "results": []}
            )
        )
        async with client:
            result = await client.call_tool(
                "search_opinions", {"q": "miranda", "cited_gt": None, "cited_lt": None}
            )
        assert not result.is_error
        assert "cited_gt" not in str(route.calls.last.request.url)


class TestCursorPagination:
    """The old ``hit=<limit>`` param was a no-op. We now truncate the page to
    ``limit`` client-side and surface ``next_cursor`` from the API ``next`` URL."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_limit_truncates_and_next_cursor_extracted(
        self, client: Client[Any]
    ) -> None:
        big = {
            "count": 100,
            "next": "https://www.courtlistener.com/api/rest/v4/search/?cursor=ABC123&q=x",
            "previous": None,
            "results": [{"id": i} for i in range(20)],
        }
        respx.get("https://www.courtlistener.com/api/rest/v4/search/").mock(
            return_value=httpx.Response(200, json=big)
        )
        async with client:
            result = await client.call_tool("search_opinions", {"q": "x", "limit": 5})
        data = result.data
        assert len(data["results"]) == 5  # truncated to limit
        assert data["next_cursor"] == "ABC123"  # cursor token surfaced

    @pytest.mark.asyncio
    @respx.mock
    async def test_no_hit_param_sent(self, client: Client[Any]) -> None:
        route = respx.get("https://www.courtlistener.com/api/rest/v4/search/").mock(
            return_value=httpx.Response(
                200, json={"count": 0, "next": None, "previous": None, "results": []}
            )
        )
        async with client:
            await client.call_tool("search_opinions", {"q": "x", "limit": 10})
        assert "hit=" not in str(route.calls.last.request.url)


class TestEcfrTools:
    """eCFR tools hit ecfr.gov (mocked here)."""

    @pytest.mark.asyncio
    @respx.mock
    async def test_list_titles(self, client: Client[Any]) -> None:
        respx.get("https://www.ecfr.gov/api/versioner/v1/titles.json").mock(
            return_value=httpx.Response(
                200,
                json={"titles": [{"number": 1, "name": "General Provisions"}]},
            )
        )
        async with client:
            result = await client.call_tool("ecfr_list_titles", {})
        assert not result.is_error
        assert result.data["titles"][0]["number"] == 1

    @pytest.mark.asyncio
    @respx.mock
    async def test_search_regulations_forwards_params(
        self, client: Client[Any]
    ) -> None:
        route = respx.get("https://www.ecfr.gov/api/search/v1/results").mock(
            return_value=httpx.Response(200, json={"results": [], "meta": {}})
        )
        async with client:
            result = await client.call_tool(
                "ecfr_search_regulations",
                {"query": "wetlands", "title": 40, "agency_slugs": None},
            )
        assert not result.is_error
        url = str(route.calls.last.request.url)
        assert "query=wetlands" in url
        # eCFR filters title via hierarchy[title] (URL-encoded brackets).
        assert "hierarchy" in url and "40" in url

    @pytest.mark.asyncio
    @respx.mock
    async def test_source_xml_returns_raw_xml(self, client: Client[Any]) -> None:
        xml = "<CFR><TITLE>40</TITLE></CFR>"
        respx.get(
            "https://www.ecfr.gov/api/versioner/v1/full/2025-01-01/title-40.xml"
        ).mock(return_value=httpx.Response(200, text=xml))
        async with client:
            result = await client.call_tool(
                "ecfr_get_source_xml",
                {"title": 40, "date": "2025-01-01", "part": "230"},
            )
        assert not result.is_error
        assert result.data["content_xml"] == xml

    @pytest.mark.asyncio
    @respx.mock
    async def test_ecfr_http_error_propagates(self, client: Client[Any]) -> None:
        from fastmcp.exceptions import ToolError

        respx.get("https://www.ecfr.gov/api/admin/v1/agencies.json").mock(
            return_value=httpx.Response(503)
        )
        async with client:
            with pytest.raises(ToolError):
                await client.call_tool("ecfr_list_agencies", {})
