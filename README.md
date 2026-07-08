# CourtListener MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io) server that gives
AI assistants access to the [CourtListener](https://www.courtlistener.com)
legal database (US federal + state court opinions, dockets, RECAP filings,
PACER data, oral arguments, judges) and the
[Electronic Code of Federal Regulations](https://www.ecfr.gov) via the
official CourtListener API v4.

Use it with Claude Desktop, Claude Code, Cursor, VS Code, Windsurf, ChatGPT
Desktop, or any MCP-compatible client.

> **Forked from** [Travis-Prall/court-listener-mcp](https://github.com/Travis-Prall/court-listener-mcp). This fork adds a hosted endpoint, bring-your-own-key (BYOK) auth, a `/health` route, Dockerfile hardening, a full **eCFR** (federal regulations) tool suite, cursor pagination, per-client rate limiting, and read-only tool annotations. See the [changelog](#changelog) for details.

### When to use this vs. the official server

Free Law Project (who run CourtListener) host an official MCP at
`https://mcp.courtlistener.com/` (OAuth, free with any CourtListener account) -
see [their announcement](https://free.law/2026/05/12/courtlistener-is-now-available-inside-claude/).
Prefer it if you want OAuth and the broadest CourtListener coverage. Use **this**
server if you want: **eCFR federal-regulations tools** (the official server has
none), simple **BYOK header** auth (no OAuth dance), or a self-hosted/embeddable
Python server. The two are complementary.

## Use the hosted endpoint (no install)

The Vaquill team runs a public instance for the community:

```
https://courtlistener-mcp.vaquill.ai/mcp/
```

You bring your own free CourtListener token from
[courtlistener.com/help/api/rest/](https://www.courtlistener.com/help/api/rest/),
the server forwards it. We never see or store your key.

### Claude Desktop / Claude Code

`~/Library/Application Support/Claude/claude_desktop_config.json` (macOS) or
`%APPDATA%\Claude\claude_desktop_config.json` (Windows):

```json
{
  "mcpServers": {
    "courtlistener": {
      "url": "https://courtlistener-mcp.vaquill.ai/mcp/",
      "headers": {
        "X-CourtListener-Token": "YOUR_COURTLISTENER_TOKEN"
      }
    }
  }
}
```

### Cursor

`.cursor/mcp.json`:

```json
{
  "mcpServers": {
    "courtlistener": {
      "url": "https://courtlistener-mcp.vaquill.ai/mcp/",
      "headers": { "X-CourtListener-Token": "YOUR_COURTLISTENER_TOKEN" }
    }
  }
}
```

### VS Code (GitHub Copilot Chat)

`.vscode/mcp.json`:

```json
{
  "servers": {
    "courtlistener": {
      "type": "http",
      "url": "https://courtlistener-mcp.vaquill.ai/mcp/",
      "headers": { "X-CourtListener-Token": "YOUR_COURTLISTENER_TOKEN" }
    }
  }
}
```

### Claude Web (custom connector)

Settings → Connectors → Add custom connector → paste the URL and add
`X-CourtListener-Token` as a header. Workspace owners only.

### Windsurf, Continue, etc.

Any client that supports MCP streamable HTTP with custom headers works.
For stdio-only clients, run the server locally (see below) or proxy with
[`mcp-remote`](https://www.npmjs.com/package/mcp-remote).

## Tools

34 tools across 4 groups (each group is namespaced). All are read-only.

| Group | Tools |
|---|---|
| Search (CourtListener) | `search_opinions`, `search_dockets`, `search_dockets_with_documents`, `search_recap_documents`, `search_audio`, `search_people` |
| Get (CourtListener) | `get_opinion`, `get_docket`, `get_audio`, `get_court`, `get_person`, `get_cluster` |
| Citation | `citation_lookup_citation`, `citation_batch_lookup_citations`, `citation_verify_citation_format`, `citation_parse_citation_with_citeurl`, `citation_extract_citations_from_text`, `citation_enhanced_citation_lookup` |
| eCFR (federal regulations) | `ecfr_list_titles`, `ecfr_get_title_versions`, `ecfr_get_title_structure`, `ecfr_get_ancestry`, `ecfr_get_source_xml`, `ecfr_list_agencies`, `ecfr_list_all_corrections`, `ecfr_list_corrections_by_title`, `ecfr_search_regulations`, `ecfr_get_search_count`, `ecfr_get_search_summary`, `ecfr_get_title_search_counts`, `ecfr_get_daily_search_counts`, `ecfr_get_hierarchy_search_counts`, `ecfr_get_search_suggestions` |
| System | `status` |

Search tools accept a `cursor` param and return a `next_cursor` for pagination.
See [app/README.md](app/README.md) for full parameter details.

## Authentication

Two modes, in priority order:

1. **Per-request header (BYOK)** — preferred for hosted / shared deployments.
   Send the user's CourtListener key on every MCP request:
   - `X-CourtListener-Token: <key>` (preferred), or
   - `Authorization: Token <key>` (CourtListener's native scheme — only works
     if the MCP server itself isn't already gated by `Authorization`).
2. **Server env fallback** — set `COURT_LISTENER_API_KEY` on the server.
   Used when no per-request header is supplied. Leave **unset** on public
   instances to force BYOK and avoid burning the operator's quota.

If neither is provided, tools return a `ValueError` with a clear message.

## Self-host

### Docker

```bash
git clone https://github.com/Vaquill-AI/courtlistener-mcp.git
cd courtlistener-mcp
cp .env.example .env  # optionally set COURT_LISTENER_API_KEY for single-tenant
docker compose up -d
# server at http://localhost:8000/mcp/
```

### Python (uv)

```bash
uv sync
uv run python -m app --transport http
```

### Stdio (local CLI integration)

```bash
uv run python -m app --transport stdio
```

Add to Claude Desktop:

```json
{
  "mcpServers": {
    "courtlistener-local": {
      "command": "uv",
      "args": ["run", "--directory", "/abs/path/to/courtlistener-mcp", "python", "-m", "app", "--transport", "stdio"],
      "env": { "COURT_LISTENER_API_KEY": "your_token" }
    }
  }
}
```

## Configuration

| Var | Required | Default | Notes |
|---|---|---|---|
| `COURT_LISTENER_API_KEY` | Optional* | — | Fallback when no per-request header. Leave unset on public servers. |
| `COURTLISTENER_BASE_URL` | No | `https://www.courtlistener.com/api/rest/v4/` | |
| `COURTLISTENER_TIMEOUT` | No | `30` | seconds |
| `MCP_TRANSPORT` | No | `stdio` | `stdio` \| `http` \| `sse` |
| `MCP_PORT` | No | `8000` | http/sse only |
| `HOST` | No | `0.0.0.0` | http/sse only |
| `ECFR_BASE_URL` | No | `https://www.ecfr.gov` | eCFR API base (no key required) |
| `RATE_LIMIT_ENABLED` | No | `true` | Per-client MCP rate limiting |
| `RATE_LIMIT_RPS` | No | `15` | Max requests/sec per client |
| `RATE_LIMIT_BURST` | No | `40` | Burst capacity per client |

\* Required only if running in single-tenant mode without BYOK.

## Health check

```bash
curl https://courtlistener-mcp.vaquill.ai/health
# {"status":"healthy","service":"courtlistener-mcp","version":"..."}
```

## Development

```bash
uv sync --dev
uv run pytest
uv run ruff format . && uv run ruff check .
uv run mypy app/
```

## Changelog

### 0.2.0

- **Added a full eCFR (federal regulations) tool suite** (15 tools): titles,
  structure, versions, ancestry, source XML, agencies, corrections, and
  full-text regulation search + analytics. This is the differentiator over
  CourtListener-only servers.
- **Fixed a validation crash**: optional search filters are now nullable
  (`str | None`), so clients that send explicit JSON `null` no longer get a
  `ValidationError` (previously broke `search_dockets` / `search_recap_documents`).
- **Real pagination**: removed the no-op `hit` param; search tools now honor
  `limit` and expose a `next_cursor` token plus an input `cursor`.
- **Read-only tool annotations** on all tools (better client UX, no write prompts).
- **Per-client rate limiting** middleware (configurable, on by default).
- Migrated `import_server` → `mount` (FastMCP 3), fixed the API-key env-var
  alias, refreshed project metadata, and got the test suite green
  (unit tests mocked; live-API tests gated behind `RUN_INTEGRATION=1`).

## Credits & License

- Original implementation: [Travis-Prall/court-listener-mcp](https://github.com/Travis-Prall/court-listener-mcp)
- Hosted by: [Vaquill](https://vaquill.ai) — courtlistener-mcp.vaquill.ai
- License: MIT (see [LICENSE](LICENSE))

CourtListener data is provided by the [Free Law Project](https://free.law/)
under their respective terms. eCFR data is from [ecfr.gov](https://www.ecfr.gov).
