# CourtListener MCP Server

A [Model Context Protocol](https://modelcontextprotocol.io) server that gives
AI assistants access to the [CourtListener](https://www.courtlistener.com)
legal database (US federal + state court opinions, dockets, RECAP filings,
PACER data, oral arguments, judges) and the
[Electronic Code of Federal Regulations](https://www.ecfr.gov) via the
official CourtListener API v4.

Use it with Claude Desktop, Claude Code, Cursor, VS Code, Windsurf, ChatGPT
Desktop, or any MCP-compatible client.

> **Forked from** [Travis-Prall/court-listener-mcp](https://github.com/Travis-Prall/court-listener-mcp). This fork adds a hosted endpoint, bring-your-own-key (BYOK) auth, a `/health` route, and Dockerfile hardening for production hosting. Tools and search semantics are unchanged.

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

| Group | Tools |
|---|---|
| Search | `search_opinions`, `search_dockets`, `search_dockets_with_documents`, `search_recap_documents`, `search_audio`, `search_people` |
| Get | `get_opinion`, `get_docket`, `get_audio`, `get_court`, `get_person`, `get_cluster` |
| Citation | `lookup_citation`, `batch_lookup_citations`, `verify_citation_format`, `parse_citation_with_citeurl`, `extract_citations_from_text`, `enhanced_citation_lookup` |
| eCFR | `list_titles`, `list_agencies`, `search_regulations`, `list_all_corrections`, `list_corrections_by_title`, `get_search_suggestions`, `get_search_summary`, `get_title_search_counts`, `get_daily_search_counts`, `get_ancestry`, `get_title_structure`, `get_source_xml`, `get_source_json` |
| System | `status`, `get_api_status`, `health_check` |

See [app/README.md](app/README.md) for parameter details.

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

## Credits & License

- Original implementation: [Travis-Prall/court-listener-mcp](https://github.com/Travis-Prall/court-listener-mcp)
- Hosted by: [Vaquill](https://vaquill.ai) — courtlistener-mcp.vaquill.ai
- License: MIT (see [LICENSE](LICENSE))

CourtListener data is provided by the [Free Law Project](https://free.law/)
under their respective terms.
