# CourtListener MCP Server - tool reference

A Model Context Protocol (MCP) server exposing the CourtListener API v4 (US case
law, dockets/RECAP, judges, oral arguments, citations) plus the eCFR API (US
federal regulations), optimized for LLM use.

For install, hosting, and auth, see the [top-level README](../README.md). This
file is the per-tool parameter reference.

## Architecture

- **`app/server.py`** - FastMCP entrypoint. Mounts the four tool sub-servers
  under their namespaces (`search`, `get`, `citation`, `ecfr`), registers the
  rate-limiting middleware, exposes a `/health` HTTP route and a `status` tool.
- **`app/config.py`** - settings (env + `.env`), BYOK/env auth resolution, and
  the shared `httpx` client accessor.
- **`app/tools/search.py`** - CourtListener search tools (`search_*`).
- **`app/tools/get.py`** - CourtListener by-ID retrieval tools (`get_*`).
- **`app/tools/citation.py`** - citation lookup/parse/verify tools (`citation_*`),
  combining the CourtListener citation-lookup API with the local `citeurl` library.
- **`app/tools/ecfr.py`** - eCFR federal-regulations tools (`ecfr_*`).

All tools are read-only (`readOnlyHint: true`). Tool names are namespaced, so a
tool defined as `opinions` in the search sub-server is exposed as `search_opinions`.

## Transport

Default transport is `stdio` (best for local CLI clients like Claude Desktop).
Run `--transport http` for a network-accessible Streamable HTTP server at
`http://<host>:<port>/mcp/`. `sse` is supported for legacy clients.

```python
from fastmcp import Client

async with Client("http://localhost:8000/mcp/") as client:
    result = await client.call_tool("status", {})
```

## CourtListener search tools

Each returns the raw CourtListener page plus a `next_cursor` token. Pass `cursor`
to fetch the next page. `limit` (1-100, default 20) is an upper bound on the
returned page. `q` is required; all filters are optional.

| Tool | Key parameters |
|---|---|
| `search_opinions` | `q`, court, case_name, judge, filed_after, filed_before, cited_gt, cited_lt, order_by, limit, cursor |
| `search_dockets` | `q`, court, case_name, docket_number, date_filed_after, date_filed_before, party_name, order_by, limit, cursor |
| `search_dockets_with_documents` | `q`, court, case_name, docket_number, date_filed_after, date_filed_before, party_name, order_by, limit, cursor |
| `search_recap_documents` | `q`, court, case_name, docket_number, document_number, attachment_number, filed_after, filed_before, party_name, order_by, limit, cursor |
| `search_audio` | `q`, court, case_name, judge, argued_after, argued_before, order_by, limit, cursor |
| `search_people` | `q`, name, position_type, political_affiliation, school, appointed_by, selection_method, order_by, limit, cursor |

## CourtListener get tools

| Tool | Parameters |
|---|---|
| `get_opinion` | `opinion_id` (required) |
| `get_docket` | `docket_id` (required) |
| `get_audio` | `audio_id` (required) |
| `get_court` | `court_id` (required, e.g. `scotus`) |
| `get_person` | `person_id` (required) |
| `get_cluster` | `cluster_id` (required) |

## Citation tools

| Tool | Parameters | Notes |
|---|---|---|
| `citation_lookup_citation` | `citation` (required) | CourtListener citation-lookup API |
| `citation_batch_lookup_citations` | `citations` (list, 1-100) | one batched request |
| `citation_verify_citation_format` | `citation` (required) | local `citeurl`, no API call |
| `citation_parse_citation_with_citeurl` | `citation` (required), `broad` (bool) | local `citeurl` |
| `citation_extract_citations_from_text` | `text` (required) | local `citeurl` |
| `citation_enhanced_citation_lookup` | `citation` (required), `include_courtlistener` (bool) | `citeurl` + CourtListener |

## eCFR tools (federal regulations, ecfr.gov, no key required)

| Tool | Parameters | eCFR endpoint |
|---|---|---|
| `ecfr_list_titles` | (none) | versioner `titles` |
| `ecfr_get_title_versions` | `title` | versioner `versions` |
| `ecfr_get_title_structure` | `title`, `date` | versioner `structure` |
| `ecfr_get_ancestry` | `title`, `date`, part, section | versioner `ancestry` |
| `ecfr_get_source_xml` | `title`, `date`, part, section, subtitle, chapter, subchapter, subpart, appendix | versioner `full` (XML) |
| `ecfr_list_agencies` | (none) | admin `agencies` |
| `ecfr_list_all_corrections` | title, date | admin `corrections` |
| `ecfr_list_corrections_by_title` | `title` | admin `corrections/title` |
| `ecfr_search_regulations` | `query`, title, agency_slugs, date, per_page, page, order | search `results` |
| `ecfr_get_search_count` | `query`, title, agency_slugs, date | search `count` |
| `ecfr_get_search_summary` | `query`, title, agency_slugs, date | search `summary` |
| `ecfr_get_title_search_counts` | `query`, date | search `counts/titles` |
| `ecfr_get_daily_search_counts` | `query`, date | search `counts/daily` |
| `ecfr_get_hierarchy_search_counts` | `query`, date | search `counts/hierarchy` |
| `ecfr_get_search_suggestions` | `query` | search `suggestions` |

Dates are `YYYY-MM-DD` snapshot dates; CFR titles are numbered 1-50. For
`ecfr_get_source_xml`, pass a `part` or `section` to scope the request -
fetching a whole large title at once can time out upstream.

## System

| Tool | Parameters | Description |
|---|---|---|
| `status` | (none) | Server status, version, transport, uptime, and system metrics. |

A plain HTTP `GET /health` liveness route is also exposed (used by Docker/Dokploy),
separate from the MCP tools.

## See also

- [../README.md](../README.md) - install, hosting, auth, configuration
- [tests/README.md](../tests/README.md) - test suite
