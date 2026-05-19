---
active: true
iteration: 1
session_id: 2be93e90-3a84-468a-90d3-2e09144ad9ad
max_iterations: 15
completion_promise: "SLICE 3 DONE"
started_at: "2026-05-19T06:54:49Z"
---

You are implementing GitHub issue #4 in repo lookeswong/meta-mcp-rnd.

STEP 1: Read the issue every iteration.
Run: gh issue view 4 --repo lookeswong/meta-mcp-rnd

STEP 2: Read CONTEXT.md for glossary.

STEP 3: Verify environment.
Run: grep -cE '^(OPENAI_API_KEY|META_ACCESS_TOKEN|MCP_SERVER_URL)=' .env
Should print 3. If less, STOP.
Run: curl -s -o /dev/null -w 'MCP:%{http_code}\n' -X POST http://localhost:8080/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -H "X-META-ACCESS-TOKEN: $(grep ^META_ACCESS_TOKEN= .env | cut -d= -f2-)" -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
Should print MCP:200. If not, STOP.

STEP 4: Check current state.
Run: ls -la app/ tests/
Run: cat app/orchestrator.py

STEP 5: Strategy.
The slice 2 orchestrator already calls arbitrary MCP tools via GPT-4o. Most acceptance criteria may already work since GPT-4o can pick get_insights, get_adsets, get_ads tools and pass natural-language dates that the Meta API accepts as date_preset (last_7d, last_30d, last_90d, etc).

So FIRST run the smoke tests with current code. Only modify if smoke fails.

Improvements likely needed in app/orchestrator.py SYSTEM_PROMPT:
- Tell GPT-4o how to map natural language date phrases to date_preset values: 'last 2 months'→last_90d, 'last week'→last_7d, 'yesterday'→yesterday, 'last month'→last_30d.
- Tell GPT-4o that when user names a campaign, first find its ID via get_campaigns(account_id), then call get_insights(level='campaign', object_id=ID).
- For not-found UX: if a named campaign is not found in any account, respond clearly that it wasn't found and list available campaign names.

STEP 6: Run unit tests (existing should still pass).
Run: .venv/bin/python -m pytest tests/ -v 2>&1 | tail -15
All must remain green.

STEP 7: Smoke tests. Use real campaign from earlier verification: [KD] Eva Airways account has real spend. Account ID is act_461625307955114. Campaign name is 14293_eva-airways_my-ao-boost-social-media-retainer.
Run: pkill -f 'uvicorn main:app' 2>/dev/null; sleep 1; .venv/bin/uvicorn main:app --port 8765 > /tmp/u.log 2>&1 &
Run: sleep 5

Smoke A — INSIGHTS WITH DATE RANGE:
Run: curl -s -m 120 -X POST http://localhost:8765/api/query -H 'Content-Type: application/json' -d '{"query":"show performance of campaigns in the [KD] Eva Airways account over the last 90 days, include impressions, clicks, CTR, spend, reach"}'
Response MUST contain numeric values for impressions, clicks, CTR, spend (e.g. MYR amounts). If empty metrics or error, iterate.

Smoke B — AD SET DRILL-DOWN:
Run: curl -s -m 120 -X POST http://localhost:8765/api/query -H 'Content-Type: application/json' -d '{"query":"show ad sets in the campaign 14293_eva-airways_my-ao-boost-social-media-retainer in account 461625307955114"}'
Response MUST list at least one ad set name. If error, iterate.

Smoke C — AD RANKING:
Run: curl -s -m 120 -X POST http://localhost:8765/api/query -H 'Content-Type: application/json' -d '{"query":"which ad in campaign 14293_eva-airways_my-ao-boost-social-media-retainer in account 461625307955114 has the best CTR"}'
Response MUST name a specific ad with a CTR value. If error, iterate.

Smoke D — NOT-FOUND HANDLING:
Run: curl -s -m 60 -X POST http://localhost:8765/api/query -H 'Content-Type: application/json' -d '{"query":"show performance of the Nonexistent Campaign XYZ123 over the last week"}'
Response MUST be a coherent message saying the campaign was not found (NOT a raw Python exception, NOT a stack trace).

Run: pkill -f 'uvicorn main:app' 2>/dev/null

STEP 8: If ALL pass — tests green AND all 4 smoke tests genuinely correct — commit with single-line message and output the promise.
Run: git add -A
Run: git commit -m 'feat: slice 3 insights + drill-down via orchestrator prompt tuning. Closes #4'
Then output:
<promise>SLICE 3 DONE</promise>

CRITICAL: DO NOT use HEREDOC commit messages (no cat<<EOF, no embedded newlines). Single -m only. DO NOT output promise if any smoke fails.

Scope guard: slice #4 only. No error-handling framework. No multi-turn conversation. Just insights + drill-down + not-found UX.
