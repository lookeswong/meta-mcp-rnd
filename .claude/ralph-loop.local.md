---
active: true
iteration: 1
session_id: 2be93e90-3a84-468a-90d3-2e09144ad9ad
max_iterations: 15
completion_promise: "SLICE 4 DONE"
started_at: "2026-05-19T07:06:56Z"
---

You are implementing GitHub issue #5 in repo lookeswong/meta-mcp-rnd.

STEP 1: Read the issue every iteration.
Run: gh issue view 5 --repo lookeswong/meta-mcp-rnd

STEP 2: Read CONTEXT.md.

STEP 3: Verify environment.
Run: grep -cE '^(OPENAI_API_KEY|META_ACCESS_TOKEN|MCP_SERVER_URL)=' .env
Should print 3. If less, STOP.

STEP 4: Check current state.
Run: ls -la app/ tests/
Run: cat main.py
Run: cat app/orchestrator.py | head -30

STEP 5: Implement error handling.

Modify main.py:
- Distinguish exception types in /api/query handler.
- If httpx.ConnectError or httpx.RequestError from mcp_client (MCP down): return response 'The ad data service is currently unavailable. Please try again shortly.'
- If httpx.ReadTimeout: return 'The request timed out. Please retry.'
- Any other unexpected exception: return 'An unexpected error occurred. Please rephrase your question or try again.'
- Never expose raw exception messages, stack traces, or JSON to the user. Log the real exception server-side via print() for debugging but return clean text only.
- FastAPI already returns 422 for malformed body via Pydantic — no extra work needed there.

Modify app/orchestrator.py SYSTEM_PROMPT — add OUT-OF-SCOPE section:
- If user asks for something the available tools cannot answer (e.g. 'what should my budget be?', 'predict next quarter performance', 'write me ad copy'), respond clearly that this prototype only retrieves and summarises existing Meta Ads data, and suggest what they CAN ask (campaign list, performance metrics, ad set / ad drill-down, not-found feedback).
- Do not invent advice or speculation.

STEP 6: Add tests in tests/test_api_errors.py covering:
- MCP unreachable: mock mcp_client.call_tool to raise httpx.ConnectError, verify /api/query response contains 'ad data service' (no traceback)
- Orchestrator generic exception: mock orchestrator.run_query to raise RuntimeError, verify response is friendly
- Malformed body: POST {} (no query field) returns HTTP 422
- Use FastAPI TestClient (from fastapi.testclient import TestClient). Mock at module level via monkeypatch.

Run: .venv/bin/python -m pytest tests/ -v 2>&1 | tail -25
ALL tests including new ones must pass.

STEP 7: Smoke tests. Keep responses small to avoid transcript bloat.

Run: pkill -f 'uvicorn main:app' 2>/dev/null; sleep 1; .venv/bin/uvicorn main:app --port 8765 > /tmp/u.log 2>&1 &
Run: sleep 5

Smoke E — MALFORMED BODY:
Run: curl -s -o /dev/null -w 'STATUS:%{http_code}\n' -X POST http://localhost:8765/api/query -H 'Content-Type: application/json' -d '{}'
MUST print STATUS:422.

Smoke F — OUT-OF-SCOPE:
Run: curl -s -m 60 -X POST http://localhost:8765/api/query -H 'Content-Type: application/json' -d '{"query":"write me a tweet thread about my campaigns"}' | python3 -c 'import sys,json; r=json.load(sys.stdin)["response"]; print(r[:300])'
Response MUST mention scope / what the app can answer, no traceback, no JSON. Print only first 300 chars to limit transcript size.

Smoke G — MCP DOWN:
Run: pkill -f 'meta_ads_mcp' 2>/dev/null; sleep 2
Run: curl -s -m 30 -X POST http://localhost:8765/api/query -H 'Content-Type: application/json' -d '{"query":"list my ad accounts"}' | python3 -c 'import sys,json; r=json.load(sys.stdin)["response"]; print(r[:300])'
Response MUST be the friendly unavailability message (or a clean handled error), NOT a traceback, NOT raw JSON, NOT empty.
Restart MCP for next iterations:
Run: set -a; source .env; set +a; nohup env META_APP_ID="$META_APP_ID" META_APP_SECRET="$META_APP_SECRET" .mcp-venv/bin/python -m meta_ads_mcp --transport streamable-http --host 0.0.0.0 --port 8080 > /tmp/mcp-server.log 2>&1 &
Run: sleep 4

Run: pkill -f 'uvicorn main:app' 2>/dev/null

STEP 8: If ALL pass — tests green AND 3 smoke tests genuinely correct — commit single-line and output promise.
Run: git add -A
Run: git commit -m 'feat: slice 4 friendly error handling + scope guard. Closes #5'
Then output:
<promise>SLICE 4 DONE</promise>

CRITICAL: NO HEREDOC commits. Single -m only. Keep smoke output trimmed via python3 [:300]. DO NOT output promise if any smoke fails.

Scope guard: slice #5 only. No multi-turn conversation.
