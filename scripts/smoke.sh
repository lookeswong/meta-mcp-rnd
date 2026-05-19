#!/usr/bin/env bash
# Smoke test harness for meta-mcp prototype.
# Runs pytest + end-to-end curl checks against the live MCP + Meta API.

set -uo pipefail

cd "$(dirname "$0")/.."

PORT=8765
APP_URL="http://localhost:${PORT}"
MCP_URL="http://localhost:8080/mcp"

PASS=0
FAIL=0
FAILED_TESTS=()

GREEN='\033[0;32m'
RED='\033[0;31m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m'

log()  { printf "${BLUE}[%s]${NC} %s\n" "$(date +%H:%M:%S)" "$*"; }
pass() { printf "  ${GREEN}PASS${NC}  %s\n" "$1"; PASS=$((PASS+1)); }
fail() { printf "  ${RED}FAIL${NC}  %s\n  reason: %s\n" "$1" "$2"; FAIL=$((FAIL+1)); FAILED_TESTS+=("$1"); }
section() { printf "\n${YELLOW}=== %s ===${NC}\n" "$*"; }

# Assert response payload (curl output) contains a substring (case-insensitive).
check_contains() {
  local name="$1" haystack="$2" needle="$3"
  if printf '%s' "$haystack" | grep -qi -- "$needle"; then
    pass "$name"
  else
    fail "$name" "expected to contain: $needle | got (first 200): ${haystack:0:200}"
  fi
}

# Assert response payload does NOT contain a substring (case-insensitive).
check_not_contains() {
  local name="$1" haystack="$2" needle="$3"
  if printf '%s' "$haystack" | grep -qi -- "$needle"; then
    fail "$name" "expected NOT to contain: $needle | got (first 200): ${haystack:0:200}"
  else
    pass "$name"
  fi
}

# Extract the .response field from a JSON body.
extract_response() {
  python3 -c 'import sys,json
try:
    print(json.load(sys.stdin).get("response",""))
except Exception as e:
    print(f"<parse-error: {e}>", file=sys.stderr)
    sys.exit(1)'
}

post_query() {
  local body="$1" timeout="${2:-120}"
  curl -s -m "$timeout" -X POST "${APP_URL}/api/query" \
    -H 'Content-Type: application/json' \
    -d "$body"
}

# ---------- Preflight ----------
section "Preflight"

if ! command -v python3 >/dev/null; then
  echo "python3 required"; exit 2
fi

if [[ ! -f .venv/bin/uvicorn ]]; then
  echo "venv missing — run: python3 -m venv .venv && .venv/bin/pip install -r requirements.txt"
  exit 2
fi

if [[ ! -f .env ]]; then
  echo ".env missing"; exit 2
fi

MCP_TOKEN=$(grep ^META_ACCESS_TOKEN= .env | cut -d= -f2-)
MCP_CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$MCP_URL" \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -H "X-META-ACCESS-TOKEN: $MCP_TOKEN" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}')
if [[ "$MCP_CODE" != "200" ]]; then
  echo "MCP server not reachable at $MCP_URL (got $MCP_CODE). Start it first."
  exit 2
fi
log "MCP reachable (HTTP $MCP_CODE)"

# ---------- Pytest ----------
section "Unit tests (pytest)"
if .venv/bin/python -m pytest tests/ -q > /tmp/smoke_pytest.log 2>&1; then
  PYTEST_LINE=$(tail -1 /tmp/smoke_pytest.log)
  pass "pytest: $PYTEST_LINE"
else
  fail "pytest" "see /tmp/smoke_pytest.log"
  tail -20 /tmp/smoke_pytest.log
fi

# ---------- Start app ----------
section "Start app"
pkill -f "uvicorn main:app" 2>/dev/null || true
sleep 1
.venv/bin/uvicorn main:app --port "$PORT" > /tmp/smoke_uvicorn.log 2>&1 &
UVI_PID=$!
trap 'pkill -f "uvicorn main:app" 2>/dev/null; exit' EXIT INT TERM
sleep 6
if ! curl -s -o /dev/null -w '%{http_code}' "$APP_URL/" | grep -q 200; then
  fail "app startup" "GET / did not return 200 — see /tmp/smoke_uvicorn.log"
  exit 1
fi
log "App up on $APP_URL (pid $UVI_PID)"

# ---------- Smoke A: malformed body → 422 ----------
section "API contract"
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$APP_URL/api/query" \
  -H 'Content-Type: application/json' -d '{}')
[[ "$STATUS" == "422" ]] && pass "malformed body → 422" || fail "malformed body" "got $STATUS"

# ---------- Backwards compat: {query} alone → 200 ----------
STATUS=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$APP_URL/api/query" \
  -H 'Content-Type: application/json' -d '{"query":"hello"}')
[[ "$STATUS" == "200" ]] && pass "{query} alone (no history) → 200" || fail "no-history compat" "got $STATUS"

# ---------- Slice 2: campaign list ----------
section "Slice 2 — campaign list"
R=$(post_query '{"query":"list my ad accounts"}' 120 | extract_response)
check_contains "list ad accounts → mentions Eva Airways" "$R" "eva airways"

# ---------- Slice 3: insights + drill-down ----------
section "Slice 3 — insights + drill-down"
R=$(post_query '{"query":"show performance of campaigns in the [KD] Eva Airways account over the last 90 days, include impressions, clicks, CTR, spend, reach"}' 180 | extract_response)
check_contains "insights returns impressions" "$R" "impressions"
check_contains "insights returns CTR"          "$R" "ctr"
check_contains "insights returns spend MYR"    "$R" "myr"

R=$(post_query '{"query":"show ad sets in the campaign 14293_eva-airways_my-ao-boost-social-media-retainer in account 461625307955114"}' 180 | extract_response)
check_contains "ad set drill-down lists ad set" "$R" "ad set"

R=$(post_query '{"query":"which ad in campaign 14293_eva-airways_my-ao-boost-social-media-retainer in account 461625307955114 has the best CTR"}' 240 | extract_response)
check_contains "best CTR ad has CTR value" "$R" "ctr"

R=$(post_query '{"query":"show performance of the Nonexistent Campaign XYZ123 over the last week"}' 120 | extract_response)
if printf '%s' "$R" | grep -qiE "not found|could ?n.t find|no campaign|cannot find|did n.t find|unable to find"; then
  pass "not-found message"
else
  fail "not-found message" "no recognised not-found phrasing | got (first 200): ${R:0:200}"
fi
check_not_contains "not-found has no traceback" "$R" "traceback"

# ---------- Slice 4: error handling ----------
section "Slice 4 — error handling"
R=$(post_query '{"query":"write me a tweet thread about my campaigns"}' 60 | extract_response)
check_contains "out-of-scope mentions scope" "$R" "list"
check_not_contains "out-of-scope no traceback" "$R" "traceback"

log "Killing MCP for unavailability test..."
pkill -f 'meta_ads_mcp' 2>/dev/null || true
sleep 3
R=$(post_query '{"query":"list my ad accounts"}' 30 | extract_response)
check_contains "MCP down → friendly message" "$R" "ad data service"
check_not_contains "MCP down no traceback" "$R" "traceback"

log "Restarting MCP..."
set -a; source .env; set +a
nohup env META_APP_ID="$META_APP_ID" META_APP_SECRET="$META_APP_SECRET" \
  .mcp-venv/bin/python -m meta_ads_mcp --transport streamable-http --host 0.0.0.0 --port 8080 \
  > /tmp/mcp-server.log 2>&1 &
sleep 5
MCP_CODE=$(curl -s -o /dev/null -w '%{http_code}' -X POST "$MCP_URL" \
  -H 'Content-Type: application/json' \
  -H 'Accept: application/json, text/event-stream' \
  -H "X-META-ACCESS-TOKEN: $MCP_TOKEN" \
  -d '{"jsonrpc":"2.0","id":1,"method":"tools/list"}')
[[ "$MCP_CODE" == "200" ]] && log "MCP back" || log "WARN: MCP did not come back ($MCP_CODE)"

# Reload tools in the running app — restart it so the registry picks up MCP again.
log "Restart app so registry reloads from MCP..."
pkill -f "uvicorn main:app" 2>/dev/null || true
sleep 1
.venv/bin/uvicorn main:app --port "$PORT" > /tmp/smoke_uvicorn.log 2>&1 &
sleep 6

# ---------- Slice 5: multi-turn conversation ----------
section "Slice 5 — multi-turn conversation"
R=$(post_query '{"query":"how many campaigns does the first one have?","history":[{"role":"user","content":"list my ad accounts"},{"role":"assistant","content":"Your ad accounts are: 1) [KD] Eva Airways (id 461625307955114), 2) [KD] Kingdom Digital MYSG (id 370090957436230), 3) Ryan Ong (id 1046725683201442)"}]}' 180 | extract_response)
check_contains "follow-up resolves 'the first one' → Eva Airways" "$R" "eva airways"

# ---------- Slice 6: creative generation ----------
section "Slice 6 — creative generation"
R=$(post_query '{"query":"based on the top 3 ads in Eva Airways last 90 days, generate 3 new copy variations targeting flight tickets"}' 300 | extract_response)
check_contains "copy gen mentions PATTERNS DETECTED" "$R" "patterns detected"
check_contains "copy gen marks variations as DRAFT" "$R" "draft"

# ---------- Summary ----------
section "Summary"
TOTAL=$((PASS+FAIL))
printf "Total: %d   ${GREEN}Pass: %d${NC}   ${RED}Fail: %d${NC}\n" "$TOTAL" "$PASS" "$FAIL"
if [[ $FAIL -gt 0 ]]; then
  echo "Failed:"
  for t in "${FAILED_TESTS[@]}"; do echo "  - $t"; done
  exit 1
fi
echo "All smoke checks passed."
exit 0
