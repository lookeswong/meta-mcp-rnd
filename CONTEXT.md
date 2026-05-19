# Meta MCP Web App — Context

## What This Is

Internal prototype validating feasibility of: user types natural language query → app uses Meta Ads MCP → returns ad performance data.

## Glossary

**Ad Account** — the Meta Ads account owned by the team. Single account, internal use only. Not multi-tenant.

**Query** — a natural language string entered by the user (e.g. "show me performance of New Traffic Campaign over last 2 months").

**MCP Server** — self-hosted instance of `pipeboard-co/meta-ads-mcp` running in streamable HTTP mode on the same machine as the backend. Not Pipeboard's cloud service.

**Tool Call** — a structured API call the LLM decides to make against the MCP server based on the user's Query. The backend executes it, feeds result back to the LLM.

**Insight** — Meta Marketing API term for performance metrics (impressions, clicks, CTR, spend, etc.) over a date range. Primary data type for this prototype.

**Access Token** — a long-lived Meta user access token stored in `.env`. Scopes: `ads_read`, `ads_management`. Generated via Meta Graph API Explorer against an existing Meta Developer App.

## Architecture

```
[Browser — HTML + vanilla JS]
    ↓ Query (POST /api/query)
[FastAPI backend]
    ↓ Query + tool definitions
[GPT-4o — OpenAI API]
    ↓ Tool call decision
[FastAPI executes tool call]
    ↓ POST /mcp (X-META-ACCESS-TOKEN header)
[meta-ads-mcp HTTP server]
    ↓ Meta Marketing API
[FastAPI feeds result back to GPT-4o]
    ↓ Natural language response
[Browser renders markdown/text]
```

## Constraints

- Read-only: no writes to Meta ad account in prototype scope
- Single user: no auth, no sessions, no multi-tenancy
- Output: raw text/markdown only, no charts
- Frontend migration path: all logic in `/api/*` routes so React/Next.js can replace HTML later without backend changes
