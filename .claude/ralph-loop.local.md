---
active: true
iteration: 1
session_id: 2be93e90-3a84-468a-90d3-2e09144ad9ad
max_iterations: 15
completion_promise: "SLICE 6 DONE"
started_at: "2026-05-19T10:33:16Z"
---

You are implementing GitHub issue #7 in repo lookeswong/meta-mcp-rnd.

STEP 1: Read issue every iteration.
Run: gh issue view 7 --repo lookeswong/meta-mcp-rnd

STEP 2: Read CONTEXT.md.

STEP 3: Verify environment.
Run: grep -cE '^(OPENAI_API_KEY|META_ACCESS_TOKEN|MCP_SERVER_URL)=' .env
Should print 3.
Run: curl -s -o /dev/null -w 'MCP:%{http_code}\n' -X POST http://localhost:8080/mcp -H 'Content-Type: application/json' -H 'Accept: application/json, text/event-stream' -H "X-META-ACCESS-TOKEN: $(grep ^META_ACCESS_TOKEN= .env | cut -d= -f2-)" -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}'
Should print MCP:200. If not, restart:
Run: pkill -f 'meta_ads_mcp' 2>/dev/null; sleep 1; set -a; source .env; set +a; nohup env META_APP_ID="$META_APP_ID" META_APP_SECRET="$META_APP_SECRET" .mcp-venv/bin/python -m meta_ads_mcp --transport streamable-http --host 0.0.0.0 --port 8080 > /tmp/mcp-server.log 2>&1 &
Run: sleep 5

STEP 4: Check current state.
Run: grep -n 'OUT-OF-SCOPE\|CREATIVE' app/orchestrator.py
Run: grep -n 'creative\|generate' scripts/smoke.sh

STEP 5: Implement.

A) Modify app/orchestrator.py SYSTEM_PROMPT — REPLACE the OUT-OF-SCOPE HANDLING section with two sections:

CREATIVE GENERATION:
When user asks to generate, write, or create new ad copy / headlines / variations grounded in their data:
1. Identify scope (account / campaign / ad set) from query.
2. Fetch top performers: call get_insights ranked by CTR (or user-specified metric) at the appropriate level for the scope.
3. Fetch creatives for the top N ads via get_creatives or get_ads to retrieve actual copy bodies, titles, CTAs.
4. Analyse winners for patterns: copy length range, hook archetype, tone, CTA style, emoji density, common themes.
5. Generate N variations (default 5; respect user-specified count) following detected patterns but differing in angle.
6. Output format:
   PATTERNS DETECTED: (1-3 sentence summary of what made winners work)
   Then a numbered list. Each item prefixed exactly with 'DRAFT - NOT PUBLISHED: ' followed by the copy.
7. If no top performers can be retrieved (no spend, empty account, all zero metrics), REFUSE: say you cannot generate copy without baseline performance data to learn from.
8. NEVER call any ads_create_* tool (ads_create_ad, ads_create_creative, ads_create_campaign, ads_create_ad_set). Generation lives entirely in the chat response. No writes.

OUT-OF-SCOPE HANDLING:
Refuse and explain scope for: strategic budget recommendations, ROAS predictions, competitor analysis, market research, image/video creative production. Listing what you CAN answer: account/campaign list, performance metrics, drill-down, creative copy generation grounded in past winners.

B) Add a unit test in tests/test_creative_gen.py verifying:
- SYSTEM_PROMPT contains anchor strings: 'CREATIVE GENERATION', 'PATTERNS DETECTED', 'DRAFT - NOT PUBLISHED', 'NEVER call any ads_create_'.
- Use pytest. Simple substring asserts.

C) Add smoke check K to scripts/smoke.sh. Insert before the Summary section:

  section 'Slice 6 — creative generation'
  R=$(post_query '{"query":"based on the top 3 ads in Eva Airways last 90 days, generate 3 new copy variations targeting flight tickets"}' 240 | extract_response)
  check_contains 'copy gen mentions PATTERNS DETECTED' "$R" 'patterns detected'
  check_contains 'copy gen marks variations as DRAFT' "$R" 'draft'

STEP 6: Run tests.
Run: .venv/bin/python -m pytest tests/ -v 2>&1 | tail -25
All must pass.

STEP 7: Smoke run (full).
Run: bash scripts/smoke.sh 2>&1 | tail -50
All checks must pass (existing 16 + new 2 = 18).

STEP 8: If all pass — commit single-line + output promise.
Run: git add -A
Run: git commit -m 'feat: slice 6 grounded creative copy generation in chat (no writes). Closes #7'
Then output:
<promise>SLICE 6 DONE</promise>

CRITICAL:
- NO HEREDOC commits.
- DO NOT add any ads_create_* tool call anywhere in code.
- DO NOT output promise if any test or smoke check fails.
- Scope: chat-only generation. No publish flow, no UI changes.
